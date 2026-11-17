"""Real .state/.report files through bin/codex-watch, without codex-status."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
REJECTED = "判定行の受領不可:"


@pytest.fixture
def watch(tmp_path):
    def run(body, *, mode=None, tokens=False, log=None, tree=ROOT):
        report = tmp_path / "probe.report"
        report.write_bytes(body.encode())
        logfile = tmp_path / "probe.log"
        logfile.write_text(log if log is not None else ("tokens used\n123\n" if tokens else "finished\n"))
        state = tmp_path / "probe.state"
        state.write_text(f"run_id=probe\npid=2147483647\nlog={logfile}\nstarted_at=0\n"
                         + (f"mode={mode}\n" if mode else ""))
        result = subprocess.run(
            ["bash", str(tree / "bin/codex-watch"), "probe"],
            env={**os.environ, "CODEX_WATCH_DIR": str(tmp_path)},
            capture_output=True, timeout=10,
        )
        result.stdout = result.stdout.decode()
        result.stderr = result.stderr.decode()
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stderr == ""
        assert sum(line.startswith("EXIT:") for line in result.stdout.splitlines()) == 1
        assert len(result.stdout.rstrip("\n").split("\n")) == (2 if tokens else 1), result.stdout
        # The report remains directly readable; validation never discards it.
        assert report.read_bytes()
        return result.stdout, report
    return run


@pytest.mark.parametrize("first", [
    "マージ可", "判定保留", "判定保留:", "判定保留 :", "判定保留：",
    "マージ可（前の回の [Must] は解消。新規 [Should] 1件）",
    "判定保留: \t\u3000\u00a0",  # whitespace-only reason
    "判定保留: \n理由は次行",  # move reason across LF
    "**実装着手可**",  # Markdown decoration
    "\ufeff実装着手可",  # BOM prefix
    "説明\n実装着手可",  # move verdict away from first line
])
@pytest.mark.parametrize("tokens", [False, True])
def test_negative(watch, first, tokens):
    output, report = watch(first + "\n本文\n", tokens=tokens)
    assert REJECTED in output
    assert "1行目を「実装着手可」「設計修正要」「判定保留: <理由>」" in output
    assert "出し直してください" in output
    assert report.read_bytes() == (first + "\n本文\n").encode()


@pytest.mark.parametrize("first,mode", [
    ("実装着手可", None), ("設計修正要", None),
    ("判定保留: 対象の版が読めない", None),
    ("実装しました", "workspace-write"),
])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_positive(watch, first, mode, newline):
    text = first + newline + "本文" + newline
    output, report = watch(text, mode=mode)
    assert REJECTED not in output
    assert report.read_bytes() == text.encode()


@pytest.mark.parametrize("control", ["\r", "\v", "\x1b", "\u2028"])
def test_control_bytes(watch, control):
    output, _ = watch("判定保留: 理由" + control + "補足\n本文\n")
    assert REJECTED in output
    assert "制御文字を除いて出し直してください" in output


def test_rebuilt_report_is_checked(watch):
    output, report = watch("末尾だけ", log="codex\nマージ可\n本文\nhook: done\n")
    assert REJECTED in output
    assert report.read_text().startswith("マージ可\n")
    assert Path(str(report) + ".raw").read_text() == "末尾だけ"


@pytest.mark.parametrize("failure", ["inside-validator", "validator-call", "import"])
def test_exception_fail_open(watch, tmp_path, failure):
    tree = tmp_path / "tree"
    for sub in ("bin", "lib"):
        shutil.copytree(ROOT / sub, tree / sub, ignore=shutil.ignore_patterns("__pycache__"))
    gate = tree / "lib/round_gate.py"
    source = gate.read_text()
    if failure == "inside-validator":
        old = "        lines = split_receipt_lines(report_text)"
        assert source.count(old) == 1
        gate.write_text(source.replace(old, '        raise RuntimeError("injected inside validator")'))
    elif failure == "validator-call":
        gate.write_text(source + '\ndef check_verdict_line(text):\n    raise RuntimeError("injected call failure")\n')
    else:
        gate.write_text('raise RuntimeError("injected import failure")\n')
    text = "判定保留\n本文\n"
    output, report = watch(text, tree=tree)
    assert "EXIT:" in output and "報告あり" in output
    assert REJECTED not in output
    assert report.read_bytes() == text.encode()
