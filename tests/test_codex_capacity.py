"""Run the actual watch/status entry points; no Codex, network, or real state writes."""
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
ERROR = "ERROR: Selected model is at capacity. Please try a different model."


def run_cli(folder, cli, log, report="マージ可\n途中結果\n", alive=False):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "run.log"
    path.write_text(log)
    (folder / "run.report").write_text(report)
    (folder / "run.state").write_text(
        f"run_id=run\npid={os.getpid() if alive else 2147483647}\n"
        f"log={path}\nworkdir={folder}\nstarted_at=0\n"
    )
    result = subprocess.run(
        [str(ROOT / "bin" / cli), "run", *(["9999999999", "0"] if cli == "codex-watch" else [])],
        env={**os.environ, "CODEX_WATCH_DIR": str(folder)},
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


@pytest.mark.parametrize("cli", ["codex-watch", "codex-status"])
@pytest.mark.parametrize("report", ["", "マージ可\n途中結果\n"])
@pytest.mark.parametrize("ending", [
    ERROR + "\n" + ERROR + "\ntokens used\n46,333\n",
    "ERROR: The selected MODEL is overloaded; retry later.\ntokens used\n1\n",
    "ERROR: No free slots for this model.\n",
    "\x1b[31mERROR: Model AT\tCAPACITY\x1b[0m\r\n\r\ntokens used\r\n42\r\n",
])
def test_terminal_capacity_is_unfinished(tmp_path, cli, report, ending):
    output = run_cli(tmp_path, cli, "codex\n途中経過\nhook: done\n" + ending, report)
    assert "容量不足" in output
    assert "モデルの空き" in output
    assert "作業未完了" in output
    assert "VERDICT:" not in output
    assert "報告あり" not in output
    assert "完了（判定行あり）" not in output
    assert "受領可:" not in output
    assert "--- 判定:" not in output
    if cli == "codex-watch":
        assert "CAPACITY:" in output
        assert "EXIT: run モデルの空きがなくて停止" in output


@pytest.mark.parametrize("cli", ["codex-watch", "codex-status"])
@pytest.mark.parametrize("log", [
    "codex\nマージ可\n本文\ntokens used\n42\n",
    "user\n" + ERROR + "\n依頼本文\ncodex\nマージ可\ntokens used\n42\n",
    ERROR + "\n" + "x" * 200000 + "\ncodex\nマージ可\ntokens used\n42\n",
    "codex\nモデルが at capacity となる例を説明しました\ntokens used\n42\n",
    "ERROR: Permission denied\ntokens used\n42\n",
    "ERROR: Request timed out\ntokens used\n42\n",
    "codex\nマージ可\ntokens used\n42\n引用: " + ERROR + "\n",
])
def test_normal_or_noncapacity_is_not_capacity(tmp_path, cli, log):
    output = run_cli(tmp_path, cli, log)
    assert "容量不足" not in output
    assert "CAPACITY:" not in output
    if cli == "codex-watch":
        assert "VERDICT:" in output
        assert "報告あり" in output
    else:
        assert "完了（判定行あり）" in output


@pytest.mark.parametrize("cli", ["codex-watch", "codex-status"])
def test_live_capacity_suppresses_verdict(tmp_path, cli):
    output = run_cli(tmp_path, cli, ERROR + "\ntokens used\n42\n", alive=True)
    assert "容量不足" in output
    assert "VERDICT:" not in output
    assert "完了（判定行あり）" not in output


@pytest.mark.parametrize("cli", ["codex-watch", "codex-status"])
def test_capacity_without_tokens_or_report(tmp_path, cli):
    output = run_cli(tmp_path, cli, ERROR + "\n", report="")
    assert "容量不足" in output
    assert "作業未完了" in output


def test_existing_filter_notification(tmp_path):
    output = run_cli(tmp_path, "codex-watch",
        "This content was flagged for possible cybersecurity risk\ntokens used\n42\n")
    assert "FILTERED:" in output
    assert "VERDICT:" not in output
    assert "報告あり" not in output


@pytest.mark.parametrize("cli", ["codex-watch", "codex-status"])
def test_capacity_after_large_tool_output(tmp_path, cli):
    output = run_cli(tmp_path, cli, "tool output\n" * 20000 + ERROR + "\ntokens used\n42\n")
    assert "容量不足" in output
    assert "作業未完了" in output
    assert "報告あり" not in output
    assert "完了（判定行あり）" not in output
