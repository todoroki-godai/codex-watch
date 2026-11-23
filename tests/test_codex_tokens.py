"""Run the report against an isolated watch directory and session store."""
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
# Projected from lines 12–16 and 64 of this public Codex rollout. Arguments
# retain only the command name. Tool output text is replaced at the same UTF-8
# byte length, and the outputs are reordered to check joining by call ID.
# https://huggingface.co/datasets/cfahlgren1/codex-sessions/blob/main/rollout-2026-03-27T09-46-38-019d2fc2-f328-73d3-ba2e-f3ea3dc838c3.jsonl
RECORDED = Path(__file__).parent / "fixtures/codex-tokens-rollout.jsonl"
JST = dt.timezone(dt.timedelta(hours=9))


@pytest.fixture
def report(tmp_path):
    state_dir = tmp_path / "watch"
    state_dir.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    sessions = tmp_path / "codex/sessions"
    (sessions / "2026" / "11" / "22").mkdir(parents=True)
    start = int(time.time()) - 60
    local = dt.datetime.fromtimestamp(start, JST).date()
    week = str(local - dt.timedelta(days=local.weekday()))
    env = {**os.environ, "HOME": str(home), "CODEX_HOME": str(sessions.parent),
           "CODEX_WATCH_DIR": str(state_dir)}

    def run_file(number, *, started=start, pid=0, historical=False, review=False,
                 compressed=False, present=True):
        session = f"019a0000-0000-7000-8000-{number:012}"
        log = state_dir / f"{number}.log"
        log.write_text("OpenAI Codex v0.171.1\n--------\nmodel: gpt-6.2-sol\n"
                       f"session id: {session}\n--------\nmodel: prompt-content\n")
        fields = [f"started_at={started}", f"pid={pid}", f"log={log}"]
        if review:
            fields.append("skills_suppressed=yes")
        if not historical:
            fields.extend(["cli_version=0.171.1", "launch_skills_filter=on:autoverified"])
        log.with_suffix(".state").write_text("\n".join(fields))
        path = sessions / "2026/11/22" / f"rollout-2026-11-22T23-59-00-{session}.jsonl"
        if present:
            shutil.copyfile(RECORDED, path)
        if compressed:
            subprocess.run(["zstd", "-q", "--rm", str(path)], env=env, check=True, timeout=10)
            path = path.with_suffix(".jsonl.zst")
        return path

    def run(*args, path=None):
        result = subprocess.run(
            [sys.executable, str(ROOT / "bin/codex-tokens"), *args],
            env={**env, **({"PATH": str(path)} if path is not None else {})},
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout

    return run_file, run, week, start


def test_report_rollout_tokens_and_tool_bytes(report):
    run_file, run, week, start = report
    rollout = run_file(1)
    # Add a custom call, its output before the call, and a duplicate token
    # snapshot. The public rollout's two request snapshots stay unchanged.
    extras = [
        {"type": "custom_tool_call_output", "call_id": "test", "output": "成功\n"},
        {"type": "custom_tool_call", "call_id": "test", "name": "exec_command",
         "input": "python3 -m pytest -q tests/fixture.py"},
        {"type": "token_count", "info": None},
    ]
    last = rollout.read_text().splitlines()[-1]
    with rollout.open("a") as stream:
        for payload in extras:
            stream.write(json.dumps({"type": "response_item", "payload": payload}) + "\n")
        stream.write(last + "\n")
    run_file(2, historical=True, review=True)
    run_file(3, pid=os.getpid(), present=False)
    run_file(4, present=False)
    run_file(5, started=start - 8 * 86400)
    # Two complete runs share the same group, but only one has test output.
    run_file(6)

    output = run()
    assert "読みバイト（推定）" in output
    assert "試験バイト（推定）" in output
    assert "入力合計トークン" in output
    assert f"{week}\tgpt-6.2-sol\timpl\t0.171.1\ton:autoverified\t2\t" in output
    assert (f"{week}\tgpt-6.2-sol\timpl\t0.171.1\ton:autoverified\t2\t"
            "2/4\t35629/71258\t30125/60250\t159318/318636\t117846/235692\t13219/26438\t"
            "241/482\t3.5/7\t375/750") in output
    assert (f"{week}\tgpt-6.2-sol\treview\t不明\t不明\t1\t"
            "2/2\t35629/35629\t30125/30125\t159318/159318\t117846/117846\t13219/13219\t"
            "241/241\t0/0\t375/375") in output
    assert "走行中\t1\n記録なし\t1\n状態欄なし\t1\n" in output
    assert sum("gpt-6.2-sol" in line for line in run("--days", "10").splitlines()) == 3


def test_compressed_record_without_zstd_is_missing(report, tmp_path):
    run_file, run, _, _ = report
    path = run_file(1, present=False)
    path.with_suffix(".jsonl.zst").write_bytes(b"no decoder available")
    assert "記録なし\t1\n" in run(path=tmp_path)


@pytest.mark.skipif(shutil.which("zstd") is None, reason="zstd is not installed")
def test_compressed_rollout_read_without_cache(report):
    run_file, run, week, _ = report
    path = run_file(1, compressed=True)
    before = sorted(path.parent.iterdir())
    assert f"{week}\tgpt-6.2-sol\timpl\t0.171.1\ton:autoverified\t1\t2/2" in run()
    assert sorted(path.parent.iterdir()) == before
