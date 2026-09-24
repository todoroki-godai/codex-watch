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

import pytest
import os
import subprocess
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"
CODEX_STATUS = BIN_DIR / "codex-status"

SHA = "a" * 40
HASH = "1" * 64

# `kill -0 $PID` で「終了」と判定させるための到達不能 PID。
# 終了済みの子プロセスの PID を使う実装は、並行実行時に OS が同じ PID を別プロセスへ
# 再利用すると `kill -0` が「生存」と誤判定し、完了分岐（受領行を出す分岐）に
# 入らないまま赤くなる（2026-09-21 頭の対照実験で確定: pid を `os.getpid()` に
# 差し替えたところ同じ2件が赤くなり、原因と一致した）。`0` はプロセスグループ全体を指すため
# 使えない（`kill -0 0` は常に「生存」と判定される）。PID の実用上限（32bit 環境の
# `/proc/sys/kernel/pid_max` 既定値・`PID_MAX_LIMIT`）を超える値を使い、実プロセスとの
# 衝突を構造的に排除する。
UNREACHABLE_PID = 2147483647


def _write_finished_run(state_dir: Path, run_id: str, *, head_sha: str, content_hash: str, report_body: str) -> None:
    """終了済み（判定行あり）の run 一式（.state/.log/.report）を用意する。"""
    log = state_dir / f"{run_id}.log"
    report = state_dir / f"{run_id}.report"
    state = state_dir / f"{run_id}.state"

    log.write_text("some log\ntokens used\n")
    report.write_text(report_body)

    state.write_text(
        "\n".join(
            [
                f"run_id={run_id}",
                f"pid={UNREACHABLE_PID}",
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
    assert "model=(config既定) effort=(config既定)" in result.stdout
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
    assert "read_sha が発注時の値と不一致です" in result.stdout
    assert "受領不可" in result.stdout
    assert "受領可" not in result.stdout, "read_sha が不一致なのに受領可と表示された"


@pytest.mark.parametrize("report_kind", ["valid", "empty", "missing"])
@pytest.mark.parametrize("log_kind", ["no_tokens", "missing"])
def test_finished_receipt_without_tokens(tmp_path, report_kind, log_kind):
    _write_finished_run(tmp_path, "run", head_sha=SHA, content_hash=HASH,
                        report_body=f"マージ可\nread_sha={SHA}\ncontent_hash={HASH}\n")
    log = tmp_path / "run.log"
    if log_kind == "missing":
        log.unlink()
    else:
        log.write_text("interrupted after report\n")
    report = tmp_path / "run.report"
    if report_kind == "empty":
        report.write_text("")
    elif report_kind == "missing":
        report.unlink()
    result = _run_status(tmp_path, "run")
    assert result.returncode == 0, result.stderr
    if report_kind == "valid":
        assert "受領可:" in result.stdout
    else:
        assert "受領不可" in result.stdout
        assert "申告がありません" in result.stdout


@pytest.mark.parametrize("claimed_sha,expected_label", [
    (SHA, "受領可:"),
    ("b" * 40, "受領不可"),
])
def test_status_rebuilds_preamble_and_displays_receipt(tmp_path, claimed_sha, expected_label):
    _write_finished_run(tmp_path, "preamble", head_sha=SHA, content_hash=HASH,
                        report_body="判定はレビュー後に出します。")
    (tmp_path / "preamble.log").write_text(
        "codex\n判定はレビュー後に出します。\nhook: done\ncodex\n"
        f"マージ可\nread_sha={claimed_sha}\ncontent_hash={HASH}\n本文\n"
        "tokens used\n"
    )
    result = _run_status(tmp_path, "preamble")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "受領" in result.stdout
    assert expected_label in result.stdout
    assert "判定行を特定できず" not in result.stdout
    assert (tmp_path / "preamble.report").read_text().splitlines()[:3] == [
        "マージ可", f"read_sha={claimed_sha}", f"content_hash={HASH}",
    ]
