"""Launcher regressions for model selection and Astra preflight."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

import pytest

from test_codex_review_cli import (
    BIN_DIR, VALID_GOAL_CUT, _init_git_repo, _write_executable, fake_bin,
)

ASTRA = "gpt-6.2-astra"
SOL = "gpt-6.2-sol"
TERRA = "gpt-6.1-terra"
REASON = "③ 永続データ移行の復元手順に波及する"
FIRST_DESIGN = "① データ復元設計の境界を検討する"
LOCAL_TEST_LINE = (
    "手元で回す試験は、変えたファイルとその近くの試験・依存先込みの lint/typecheck だけ。"
    "パッケージ全体・リポジトリ全体の試験は頭が AWS で回すので回さない（依頼文が明示的に求めた場合を除く）。"
)


@pytest.fixture()
def dispatch(tmp_path, fake_bin):
    original = tmp_path / "original"
    original.mkdir()
    (original / "auth.json").write_text("synthetic token")
    (original / "config.toml").write_text('[mcp_servers.secret]\ncommand="synthetic token"\n')
    work = tmp_path / "work"
    work.mkdir()
    _init_git_repo(work)
    prompt = tmp_path / "prompt with spaces.md"
    prompt.write_text("直しの出所: なし\n点検:\n- 突き合わせ: 済\n- 出所の付記: 済\n"
                      "- 直し残しの検索: 済\n- Must: 済\n")
    body = tmp_path / "body"
    body.write_text("gh fixture body\n")

    _write_executable(fake_bin / "aws",
                      f"#!/bin/sh\ntouch {shlex.quote(str(tmp_path / 'aws-called'))}\nexit 1\n")
    _write_executable(fake_bin / "codex", f"""#!{sys.executable}
import json, os, sys
from pathlib import Path
root = Path({str(tmp_path)!r})
if sys.argv[1] == "app-server":
    (root / "probe").touch()
    raise AssertionError(sys.argv)
elif sys.argv[1] == "exec":
    (root / "stdin").write_bytes(sys.stdin.buffer.read())
    seen = root / "exec.tmp"
    seen.write_text(json.dumps([sys.argv[1:], sorted(os.environ)]))
    seen.rename(root / "exec")
else:
    raise AssertionError(sys.argv)
""")

    env = {key: value for key, value in os.environ.items() if not key.startswith(("CODEX_", "REVIEW_"))}
    env.update(PATH=f"{fake_bin}:{os.environ['PATH']}", HOME=str(tmp_path),
               CODEX_HOME=str(original), CODEX_SUMMARY="#1", CODEX_WATCH_DIR=str(tmp_path / "state"),
               OPENAI_API_KEY="synthetic token", GH_TOKEN="synthetic token",
               CODEX_IMPL_ALLOW_MAIN="1", CODEX_IMPL_ALLOW_MISSING_NODE_MODULES="1",
               CODEX_SKILLS_FILTER="off", FAKE_GH_BODY=str(body),
               CODEX_REVIEW_ADAPTER=str(tmp_path / "no-adapter"),
               CODEX_REVIEW_KIND_LABEL="設計", REVIEW_TARGET="issue:example-org/example-repo#1",
               REVIEW_GOAL_CUT=VALID_GOAL_CUT)

    def run(launcher, *, prompt_bytes=None, **settings):
        if prompt_bytes is not None:
            prompt.write_bytes(prompt_bytes)
        return subprocess.run([str(BIN_DIR / f"codex-{launcher}"), str(work), str(prompt)],
                              env=dict(env, **settings), capture_output=True, text=True, timeout=12)

    return run


def check_dispatch(result, path, launcher, model, reason=None):
    assert result.returncode == 0, result.stderr
    deadline = time.monotonic() + 2
    while not (path / "exec").exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    argv, env_keys = json.loads((path / "exec").read_text())
    assert argv.count("-m") == 1 and argv[argv.index("-m") + 1] == model
    assert "CODEX_ASTRA_REASON" not in env_keys and "ASTRA_REASON" not in env_keys
    run_id = result.stdout.strip()
    state = dict(line.split("=", 1) for line in
                 (path / "state" / f"{run_id}.state").read_text().splitlines())
    assert state["run_id"] == run_id
    assert state["requested_model"] == model and state.get("astra_reason") == reason
    model_lines = [line for line in result.stderr.splitlines() if line.startswith("モデル: ")]
    option = f"CODEX_{launcher.upper()}_MODEL"
    guidance = ("通常は sol、全体の設計・レビューの繰り返し・設計し直しは "
                if launcher == "review" else
                "通常は terra、大事な場面・難しい作業は sol、全体の設計・設計し直しは ")
    guidance += f"astra（理由の指定が必要）を {option} で指定"
    assert model_lines == [f"モデル: {model}（{guidance}）"]
    return state


def check_rejected(result, path, prior=()):
    assert result.returncode == 2, result.stderr
    assert not (path / "exec").exists()
    assert not (path / "aws-called").exists()
    assert tuple((path / "state").glob("*")) == prior


@pytest.mark.parametrize("launcher", ["impl", "review"])
@pytest.mark.parametrize("model", [None, "", " \t　"], ids=["unset", "empty", "whitespace"])
def test_missing_model_rejected_without_codex(dispatch, tmp_path, launcher, model):
    option = f"CODEX_{launcher.upper()}_MODEL"
    settings = {} if model is None else {option: model}
    result = dispatch(launcher, **settings)
    check_rejected(result, tmp_path)
    assert "拒否: モデルの指定がありません" in result.stderr
    assert option in result.stderr
    guidance = ("通常は gpt-6.2-sol、全体の設計・レビューの繰り返し・設計し直しは "
                "astra（理由の指定が必要）を使用してください。" if launcher == "review" else
                "通常は gpt-6.1-terra、大事な場面・難しい作業は gpt-6.2-sol、\n"
                "全体の設計・設計し直しは astra（理由の指定が必要）を使用してください。")
    assert guidance in result.stderr
    assert not (tmp_path / "probe").exists()


def test_missing_model_preflight_exit_code(tmp_path):
    result = subprocess.run(["python3", str(BIN_DIR.parent / "lib/codex_dispatch_model.py"),
                             str(tmp_path), "", "CODEX_IMPL_MODEL"],
                            capture_output=True, text=True, timeout=12)
    assert result.returncode == 2
    assert "拒否: モデルの指定がありません" in result.stderr


@pytest.mark.parametrize("body", [
    "直しの出所: なし\n　日本語と `$(exit 99)`\n\n",
    "直しの出所: なし\r\n依頼文はパッケージ全体の試験を明示的に求める",
    f"直しの出所: なし\n{LOCAL_TEST_LINE}\n" + "詳細 " * 24_000 + "\n",
], ids=["utf8-with-trailing-newlines", "crlf-without-final-newline", "large-with-existing-line"])
def test_impl_prepends_local_test_line_to_child_stdin(dispatch, tmp_path, body):
    original = body.encode("utf-8")
    result = dispatch("impl", prompt_bytes=original, CODEX_IMPL_MODEL=SOL)
    state = check_dispatch(result, tmp_path, "impl", SOL)
    assert (tmp_path / "stdin").read_bytes() == (LOCAL_TEST_LINE + "\n").encode("utf-8") + original
    assert Path(state["prompt"]).read_bytes() == original


@pytest.mark.parametrize("launcher", ["impl", "review"])
@pytest.mark.parametrize("model", [SOL, ASTRA, TERRA, ASTRA.upper(), "unknown-model"])
def test_explicit_model_is_preserved(dispatch, tmp_path, launcher, model):
    reason = REASON if model.lower() == ASTRA else None
    result = dispatch(launcher, CODEX_ASTRA_REASON=reason or "",
                      **{f"CODEX_{launcher.upper()}_MODEL": model})
    check_dispatch(result, tmp_path, launcher, model, reason)
    assert not (tmp_path / "probe").exists()


def test_explicit_model_skips_rpc_and_design_first_round_is_proven(dispatch, tmp_path):
    result = dispatch("review", CODEX_REVIEW_MODEL=ASTRA, CODEX_ASTRA_REASON=FIRST_DESIGN)
    state = check_dispatch(result, tmp_path, "review", ASTRA, FIRST_DESIGN)
    assert state["round"] == "1"
    assert not (tmp_path / "probe").exists()


@pytest.mark.parametrize("launcher", ["impl", "review"])
@pytest.mark.parametrize("reason", ["", "③", "③　", "③ 要件\u2028injected=1"])
def test_astra_family_rejects_missing_or_non_line_reason(dispatch, tmp_path, launcher, reason):
    result = dispatch(launcher, CODEX_ASTRA_REASON=reason,
                      **{f"CODEX_{launcher.upper()}_MODEL": "GPT-6.2-ASTRA-2026-11-21"})
    check_rejected(result, tmp_path)
    assert "CODEX_ASTRA_REASON" in result.stderr
    assert not (tmp_path / "probe").exists()


@pytest.mark.parametrize(("launcher", "context"), [
    ("impl", {}), ("review", {"CODEX_REVIEW_KIND_LABEL": "コード"}),
    ("review", {"REVIEW_TARGET": "none:fixture"}), ("review", {"CODEX_REVIEW_NO_GATE": "fixture"}),
])
def test_first_design_reason_requires_actual_design_round(dispatch, tmp_path, launcher, context):
    result = dispatch(launcher, CODEX_ASTRA_REASON=FIRST_DESIGN,
                      **{f"CODEX_{launcher.upper()}_MODEL": ASTRA}, **context)
    check_rejected(result, tmp_path)
    assert "設計巡1" in result.stderr


def test_existing_must_only_round_blocks_astra_even_with_reason(dispatch, tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    earlier = state_dir / "earlier.state"
    snapshot = "review_target=issue:example-org/example-repo#1\nkind_label=設計\nhead_sha=old-head\n"
    earlier.write_text(snapshot)
    result = dispatch("review", CODEX_REVIEW_MODEL=ASTRA, CODEX_ASTRA_REASON=REASON)
    check_rejected(result, tmp_path, prior=(earlier,))
    assert earlier.read_text() == snapshot
    assert "Must 解消だけ" in result.stderr


def test_review_dry_run_skips_resolution_and_dispatch(dispatch, tmp_path):
    result = dispatch("review", CODEX_REVIEW_GATE_CHECK="1")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["total_round"] == 1
    assert "モデル: " not in result.stderr
    assert not (tmp_path / "probe").exists()
    assert not (tmp_path / "exec").exists()
    assert not list((tmp_path / "state").glob("*"))
