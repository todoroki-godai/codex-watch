"""bin/_codex_common.sh + codex-review/codex-impl の model/effort 配線を試験する。

経緯（2026-09-08 codex レビュー [Must]1+2 差し戻し）: 当初 config.toml を自前 awk で
パースしていたが TOML の字句規則を実装しておらず食い違いが構成された。撤去して
「要求値は env のみ state に requested_* として書く」「実効値は codex 起動ログの
ヘッダーから読む」の2本立てへ変更した。ここではその配線を試験する:
  ① env 未指定時、codex へ渡る引数列に -m/-c が付かないこと（従来と同一）
  ② env 指定時、-m が1つだけ付くこと
  ③ ヘッダーを含む合成ログから実効値を取り出せること（extract_codex_log_header 単体）
  ④ ヘッダー不在のログで unresolved になること（extract_codex_log_header 単体）

実際の `codex` CLI は一切呼ばない（fake スタブに差し替える。fake は argv を側路ファイルへ
書き出し、標準出力へ合成ヘッダーを吐くだけ）。
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"
CODEX_REVIEW = BIN_DIR / "codex-review"
CODEX_IMPL = BIN_DIR / "codex-impl"
COMMON_SH = BIN_DIR / "_codex_common.sh"

VALID_GOAL_CUT = "30.04分/周 | 根拠: pitfall #588 の実測（2026-08-26 cider-power-lp） | 取得日: 2026-08-26"

SYNTHETIC_HEADER = """\
OpenAI Codex v0.153.4
--------
workdir: /tmp/x
model: gpt-5.6-sol
provider: openai
approval: never
sandbox: read-only
reasoning effort: medium
reasoning summaries: none
session id: test-session
--------
user
dummy
"""


def _write_executable(path: Path, script: str) -> None:
    path.write_text(script)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture()
def fake_bin(tmp_path: Path) -> Path:
    """fake `gh` / `codex` を PATH に置く。

    `codex` は標準入力を読み捨て、自分の argv を `$ARGV_CAPTURE_FILE` へ1行1引数で書き出し、
    合成ヘッダー（SYNTHETIC_HEADER 相当。呼び出し側が > "$LOG_FILE" でリダイレクトするので
    ここでの標準出力がそのままログになる）を出力する。`gh` は codex-review の巡数ゲート発注
    経路が呼ぶ最小限だけ相手をする（test_codex_review_cli.py の fake_bin と同じ形）。
    """
    d = tmp_path / "fakebin"
    d.mkdir()
    _write_executable(
        d / "gh",
        "#!/bin/sh\n"
        "BODY_FILE=\"${FAKE_GH_BODY:-/dev/null}\"\n"
        "case \"$1\" in\n"
        "  issue|pr)\n"
        "    if [ \"$2\" = view ]; then\n"
        "      cat >/dev/null 2>&1\n"
        "      if [ -f \"$BODY_FILE\" ]; then cat \"$BODY_FILE\"; fi\n"
        "      exit 0\n"
        "    fi\n"
        "    ;;\n"
        "  api)\n"
        "    python3 -c \"import json,sys; d=json.load(sys.stdin); sys.stdout.write(d.get('body',''))\" > \"$BODY_FILE\"\n"
        "    exit 0\n"
        "    ;;\n"
        "esac\n"
        "exit 0\n",
    )
    _write_executable(
        d / "codex",
        "#!/bin/sh\n"
        "cat >/dev/null\n"  # 標準入力（プロンプト）を読み捨てる
        "if [ -n \"$ARGV_CAPTURE_FILE\" ]; then\n"
        "  : > \"$ARGV_CAPTURE_FILE\"\n"
        "  for a in \"$@\"; do printf '%s\\n' \"$a\" >> \"$ARGV_CAPTURE_FILE\"; done\n"
        "fi\n"
        "if [ -n \"$FAKE_CODEX_HEADER_FILE\" ] && [ -f \"$FAKE_CODEX_HEADER_FILE\" ]; then\n"
        "  cat \"$FAKE_CODEX_HEADER_FILE\"\n"
        "fi\n"
        "exit 0\n",
    )
    return d


def _run_impl(
    fake_bin: Path,
    tmp_path: Path,
    *,
    argv_capture: Path,
    header_file: Path | None,
    model_env: str = "",
    effort_env: str = "",
) -> subprocess.CompletedProcess:
    workdir = tmp_path / "workdir"
    workdir.mkdir(exist_ok=True)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("dummy prompt\n")
    state_dir = tmp_path / "state"
    state_dir.mkdir(exist_ok=True)

    env = dict(os.environ)
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
    env["CODEX_WATCH_DIR"] = str(state_dir)
    env["CODEX_IMPL_ALLOW_MAIN"] = "1"  # tmp_path は git repo ではないため
    env["ARGV_CAPTURE_FILE"] = str(argv_capture)
    env["CODEX_LOG_HEADER_TIMEOUT_S"] = "1"
    if header_file is not None:
        env["FAKE_CODEX_HEADER_FILE"] = str(header_file)
    else:
        env.pop("FAKE_CODEX_HEADER_FILE", None)
    if model_env:
        env["CODEX_IMPL_MODEL"] = model_env
    else:
        env.pop("CODEX_IMPL_MODEL", None)
    if effort_env:
        env["CODEX_IMPL_EFFORT"] = effort_env
    else:
        env.pop("CODEX_IMPL_EFFORT", None)

    return subprocess.run(
        [str(CODEX_IMPL), str(workdir), str(prompt), "clitest"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


# ---------------------------------------------------------------------------
# ① env 未指定時、codex へ渡る引数列に -m/-c が付かない（従来と同一）
# ---------------------------------------------------------------------------


def test_impl_no_model_env_produces_no_extra_flags(fake_bin: Path, tmp_path: Path):
    header_file = tmp_path / "header.txt"
    header_file.write_text(SYNTHETIC_HEADER)
    argv_capture = tmp_path / "argv.txt"

    result = _run_impl(fake_bin, tmp_path, argv_capture=argv_capture, header_file=header_file)
    assert result.returncode == 0, result.stdout + result.stderr

    argv_lines = argv_capture.read_text().splitlines()
    assert "-m" not in argv_lines, argv_lines
    assert not any(a.startswith("model_reasoning_effort=") for a in argv_lines), argv_lines


# ---------------------------------------------------------------------------
# ② env 指定時、-m が1つだけ付く
# ---------------------------------------------------------------------------


def test_impl_model_env_adds_exactly_one_dash_m(fake_bin: Path, tmp_path: Path):
    header_file = tmp_path / "header.txt"
    header_file.write_text(SYNTHETIC_HEADER)
    argv_capture = tmp_path / "argv.txt"

    result = _run_impl(
        fake_bin, tmp_path, argv_capture=argv_capture, header_file=header_file, model_env="gpt-test-model"
    )
    assert result.returncode == 0, result.stdout + result.stderr

    argv_lines = argv_capture.read_text().splitlines()
    assert argv_lines.count("-m") == 1, argv_lines
    idx = argv_lines.index("-m")
    assert argv_lines[idx + 1] == "gpt-test-model", argv_lines


# ---------------------------------------------------------------------------
# state には requested_* と env で渡した値が一致し、config.toml を経由していないこと
# ---------------------------------------------------------------------------


def test_impl_state_records_requested_and_effective_from_log(fake_bin: Path, tmp_path: Path):
    header_file = tmp_path / "header.txt"
    header_file.write_text(SYNTHETIC_HEADER)
    argv_capture = tmp_path / "argv.txt"

    result = _run_impl(
        fake_bin,
        tmp_path,
        argv_capture=argv_capture,
        header_file=header_file,
        model_env="gpt-test-model",
        effort_env="high",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    run_id = result.stdout.strip().splitlines()[-1]
    state_file = tmp_path / "state" / f"{run_id}.state"
    assert state_file.is_file()
    lines = dict(
        ln.split("=", 1) for ln in state_file.read_text().splitlines() if "=" in ln
    )
    assert lines["requested_model"] == "gpt-test-model"
    assert lines["requested_effort"] == "high"
    # ヘッダーは常に gpt-5.6-sol/medium を返す fake なので、実効値はそれと一致する
    # （要求値と実効値が別物であることを示す＝実際の起動が要求どおりとは限らない）
    assert lines["model"] == "gpt-5.6-sol"
    assert lines["model_source"] == "cli_log"
    assert lines["effort"] == "medium"
    assert lines["effort_source"] == "cli_log"


# ---------------------------------------------------------------------------
# ④ ヘッダー不在のログで unresolved になる（state 経由の統合試験）
# ---------------------------------------------------------------------------


def test_impl_state_unresolved_when_no_header(fake_bin: Path, tmp_path: Path):
    argv_capture = tmp_path / "argv.txt"
    result = _run_impl(fake_bin, tmp_path, argv_capture=argv_capture, header_file=None)
    assert result.returncode == 0, result.stdout + result.stderr
    run_id = result.stdout.strip().splitlines()[-1]
    state_file = tmp_path / "state" / f"{run_id}.state"
    lines = dict(
        ln.split("=", 1) for ln in state_file.read_text().splitlines() if "=" in ln
    )
    assert lines["model_source"] == "unresolved"
    assert lines["effort_source"] == "unresolved"
    assert "model" not in lines
    assert "effort" not in lines


# ---------------------------------------------------------------------------
# ③④ extract_codex_log_header 単体（bin/_codex_common.sh 直接試験）
# ---------------------------------------------------------------------------


def _run_extract(log_text: str | None, tmp_path: Path, timeout_s: int = 1) -> str:
    log_file = tmp_path / "extract.log"
    if log_text is not None:
        log_file.write_text(log_text)
    script = (
        f'source "{COMMON_SH}"\n'
        f'extract_codex_log_header "{log_file}" {timeout_s}\n'
    )
    result = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


def test_extract_log_header_reads_effective_values(tmp_path: Path):
    out = _run_extract(SYNTHETIC_HEADER, tmp_path)
    model, model_source, effort, effort_source = out.split("\t")
    assert model == "gpt-5.6-sol"
    assert model_source == "cli_log"
    assert effort == "medium"
    assert effort_source == "cli_log"


def test_extract_log_header_unresolved_when_absent(tmp_path: Path):
    out = _run_extract("no header at all\njust some text\n", tmp_path)
    model, model_source, effort, effort_source = out.split("\t")
    assert model == "unresolved"
    assert model_source == "unresolved"
    assert effort == "unresolved"
    assert effort_source == "unresolved"


# ---------------------------------------------------------------------------
# 陰性試験（回帰防止）: 行頭固定を外すと埋め込み文字列を誤って拾う
# ---------------------------------------------------------------------------


def test_extract_log_header_line_anchor_prevents_embedded_match(tmp_path: Path):
    poisoned = (
        "OpenAI Codex v0.153.4\n"
        "--------\n"
        "note: see model: not-the-real-model in this comment line\n"
        "model: gpt-5.6-sol\n"
        "reasoning effort: medium\n"
        "--------\n"
    )
    out = _run_extract(poisoned, tmp_path)
    model, model_source, _effort, _effort_source = out.split("\t")
    assert model == "gpt-5.6-sol", "行頭固定が外れて埋め込み文字列を拾った可能性がある"
    assert model_source == "cli_log"
