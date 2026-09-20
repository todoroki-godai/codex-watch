"""bin/codex-status の「受領」表示（claude-config#55 の出口）を直接叩くテスト。

方針:
- lib/round_gate.py の `receipt` サブコマンド自体は test_round_gate.py / test_codex_review_cli.py
  で試験済み。ここで試すのは「codex-status がその結果を人間に見える出力へ実際に表示するか」
  （出口の配線）。頭のレビューで、CLI 呼び出しだけのテストでは `bin/codex-status` から
  「受領」行を削除しても検出できないことが実測された（2026-09-21 レビュー指摘 [Must]2）。
- `codex-status` は `gh` / `codex` を呼ばない（state / log / report ファイルを読むだけ）ので、
  fake バイナリは不要。state・log・report を直接 tmp_path に用意して起動する。
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"
CODEX_STATUS = BIN_DIR / "codex-status"

SHA = "a" * 40
HASH = "1" * 64


def _write_finished_run(state_dir: Path, run_id: str, *, head_sha: str, content_hash: str, report_body: str) -> None:
    """終了済み（判定行あり）の run 一式（.state/.log/.report）を用意する。"""
    log = state_dir / f"{run_id}.log"
    report = state_dir / f"{run_id}.report"
    state = state_dir / f"{run_id}.state"

    log.write_text("some log\ntokens used\n")
    report.write_text(report_body)

    # 確実に「終了」判定になるよう、既に終了済みの子プロセスの PID を使う。
    p = subprocess.Popen(["true"])
    p.wait()

    state.write_text(
        "\n".join(
            [
                f"run_id={run_id}",
                f"pid={p.pid}",
                f"log={log}",
                f"workdir=/tmp",
                f"started_at={0}",
                "requested_model=",
                "requested_effort=",
                f"head_sha={head_sha}",
                f"content_hash={content_hash}",
            ]
        )
        + "\n"
    )


def _run_status(state_dir: Path, run_id: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["CODEX_WATCH_DIR"] = str(state_dir)
    return subprocess.run(
        [str(CODEX_STATUS), run_id],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )


def test_status_shows_receipt_ok_line_on_matching_claim(tmp_path: Path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    _write_finished_run(
        state_dir,
        "run-ok",
        head_sha=SHA,
        content_hash=HASH,
        report_body=f"マージ可\nread_sha={SHA}\ncontent_hash={HASH}\n本文...\n",
    )
    result = _run_status(state_dir, "run-ok")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "受領" in result.stdout, "codex-status の出力に受領判定が表示されていない"
    assert "受領可" in result.stdout


def test_status_shows_receipt_rejected_line_on_mismatched_claim(tmp_path: Path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    other_sha = "b" * 40
    _write_finished_run(
        state_dir,
        "run-bad",
        head_sha=SHA,
        content_hash=HASH,
        report_body=f"マージ可\nread_sha={other_sha}\ncontent_hash={HASH}\n本文...\n",
    )
    result = _run_status(state_dir, "run-bad")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "受領" in result.stdout
    assert "受領可" not in result.stdout, "read_sha が不一致なのに受領可と表示された"
