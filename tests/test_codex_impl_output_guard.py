"""bin/codex-impl の出力節約前置き（output_guard）を試験する。

経緯（2026-09-24 ユーザー承認・実測は updater-index の
_work/notes/codex-token-usage-20260924.md）: 実装依頼1回あたりの token 消費の
主因が、型チェック・テストの全量出力や無制限の検索結果をそのまま会話へ読み込み、
以後の全ターンで再送されることだった（直近14日平均 2,024,796 token/回）。
codex-impl の発注プロンプトの先頭に、出力の「読み方」を固定する前置きを常時
付与し（codex-review の SKILLS_SUPPRESSED と同じ流儀）、無効化の口
（CODEX_IMPL_ALLOW_BIG_OUTPUT=1）を1つだけ用意する。効き目を後で測れるよう
state ファイルへ output_guard=yes|no を記録する。

ここで試すのは:
  ① 既定で前置きが EFFECTIVE_PROMPT に入り、state に output_guard=yes が出ること
  ② 元のプロンプト本文が EFFECTIVE_PROMPT 内に保存されていること（前置きが
     本文を破壊/置換していないこと）
  ③ CODEX_IMPL_ALLOW_BIG_OUTPUT=1 で前置きが外れ、state が output_guard=no に
     なること
  ④ 実際の codex CLI は呼ばない（fake スタブに標準入力を渡し、その内容を
     side file に保存させて EFFECTIVE_PROMPT の中身を検証する）
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"
CODEX_IMPL = BIN_DIR / "codex-impl"

GUARD_MARKER = "長くなりうるコマンド"


def _write_executable(path: Path, script: str) -> None:
    path.write_text(script)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture()
def fake_bin(tmp_path: Path) -> Path:
    """fake `codex` を PATH に置く。標準入力（= EFFECTIVE_PROMPT の中身）をまるごと
    `$FAKE_CODEX_STDIN_CAPTURE` へ保存してから即終了する。
    """
    d = tmp_path / "fakebin"
    d.mkdir()
    _write_executable(
        d / "codex",
        "#!/bin/sh\n"
        "if [ -n \"$FAKE_CODEX_STDIN_CAPTURE\" ]; then\n"
        "  cat > \"$FAKE_CODEX_STDIN_CAPTURE\"\n"
        "else\n"
        "  cat >/dev/null\n"
        "fi\n"
        "exit 0\n",
    )
    return d


def _run_impl(
    fake_bin: Path,
    tmp_path: Path,
    *,
    stdin_capture: Path,
    allow_big_output: str | None = None,
    prompt_text: str = "これはテスト用の依頼本文です。\n",
) -> tuple[subprocess.CompletedProcess, Path]:
    workdir = tmp_path / "workdir"
    workdir.mkdir(exist_ok=True)
    # node_modules 下準備ゲート（本題と無関係）を通すためだけにダミーを1件置く。
    node_modules = workdir / "node_modules"
    node_modules.mkdir(exist_ok=True)
    (node_modules / ".keep").write_text("")

    prompt = tmp_path / "prompt.txt"
    prompt.write_text(prompt_text)
    state_dir = tmp_path / "state"
    state_dir.mkdir(exist_ok=True)

    env = dict(os.environ)
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
    env["CODEX_WATCH_DIR"] = str(state_dir)
    env["CODEX_IMPL_ALLOW_MAIN"] = "1"  # tmp_path は git repo ではないため
    env["FAKE_CODEX_STDIN_CAPTURE"] = str(stdin_capture)
    if allow_big_output is not None:
        env["CODEX_IMPL_ALLOW_BIG_OUTPUT"] = allow_big_output
    else:
        env.pop("CODEX_IMPL_ALLOW_BIG_OUTPUT", None)

    result = subprocess.run(
        [str(CODEX_IMPL), str(workdir), str(prompt), "clitest"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result, state_dir


def _state_dict(state_file: Path) -> dict[str, str]:
    return dict(ln.split("=", 1) for ln in state_file.read_text().splitlines() if "=" in ln)


def _wait_for_file(path: Path, timeout_s: float = 2.0) -> None:
    import time

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if path.exists() and path.stat().st_size > 0:
            return
        time.sleep(0.02)


# ---------------------------------------------------------------------------
# ① 既定で前置きが付き、state に output_guard=yes が出る
# ---------------------------------------------------------------------------


def test_default_adds_guard_prefix_and_records_yes(fake_bin: Path, tmp_path: Path):
    stdin_capture = tmp_path / "stdin.txt"
    result, state_dir = _run_impl(fake_bin, tmp_path, stdin_capture=stdin_capture)
    assert result.returncode == 0, result.stdout + result.stderr

    run_id = result.stdout.strip().splitlines()[-1]
    state_file = state_dir / f"{run_id}.state"
    assert state_file.is_file(), f"state file not found: {state_file}"
    state = _state_dict(state_file)
    assert state.get("output_guard") == "yes"

    effective_prompt = Path(state["effective_prompt"])
    assert effective_prompt.is_file()
    effective_text = effective_prompt.read_text()
    assert GUARD_MARKER in effective_text

    _wait_for_file(stdin_capture)
    assert GUARD_MARKER in stdin_capture.read_text()


# ---------------------------------------------------------------------------
# ② 元のプロンプト本文が EFFECTIVE_PROMPT に残っている（前置きが本文を破壊しない）
# ---------------------------------------------------------------------------


def test_original_prompt_body_is_preserved(fake_bin: Path, tmp_path: Path):
    marker = "元本文マーカーXYZ123"
    stdin_capture = tmp_path / "stdin.txt"
    result, state_dir = _run_impl(
        fake_bin, tmp_path, stdin_capture=stdin_capture, prompt_text=f"{marker}\n本文の続き\n"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    run_id = result.stdout.strip().splitlines()[-1]
    state = _state_dict(state_dir / f"{run_id}.state")
    effective_text = Path(state["effective_prompt"]).read_text()
    assert marker in effective_text
    assert "本文の続き" in effective_text


# ---------------------------------------------------------------------------
# ③ CODEX_IMPL_ALLOW_BIG_OUTPUT=1 で前置きが外れ、state が output_guard=no になる
# ---------------------------------------------------------------------------


def test_allow_big_output_disables_guard(fake_bin: Path, tmp_path: Path):
    stdin_capture = tmp_path / "stdin.txt"
    result, state_dir = _run_impl(
        fake_bin, tmp_path, stdin_capture=stdin_capture, allow_big_output="1"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    run_id = result.stdout.strip().splitlines()[-1]
    state = _state_dict(state_dir / f"{run_id}.state")
    assert state.get("output_guard") == "no"

    effective_prompt = Path(state["effective_prompt"])
    effective_text = effective_prompt.read_text()
    assert GUARD_MARKER not in effective_text

    _wait_for_file(stdin_capture)
    assert GUARD_MARKER not in stdin_capture.read_text()
