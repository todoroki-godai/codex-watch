"""bin/codex-review の実発注口（シェル配線・state 保存）を直接叩くテスト。

方針（design-gate-v3.md / 2026-09-03 codex レビュー Should1）:
- lib/round_gate.py の純粋関数は test_round_gate.py で試験済み。ここで試すのは
  「シェルの配線」自体（--goal-cut の受け渡し・GATE_JSON の展開・state への goal_cut= 書き込み）。
  round_gate.py の LF 単体試験だけでは state 破壊まで検出できなかった、というのが実際に
  起きた欠陥の経路（Must1）だったため、発注口から固定する。
- 実際の `codex` CLI / `gh` CLI は一切呼ばない（fake スタブに差し替える）。fake 化するのは、
  発注が実際に外部（OpenAI / GitHub）へ副作用を及ぼすのを避けるため（read-only の `gate`
  判定だけなら実在する公開 issue を読むのは無害だが、`record`（gh api PATCH）は書き込みを
  伴うため必ず fake gh を使う）。
"""
from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"
CODEX_REVIEW = BIN_DIR / "codex-review"

VALID_GOAL_CUT = "30.04分/周 | 根拠: pitfall #588 の実測（2026-08-26 cider-power-lp） | 取得日: 2026-08-26"


def _write_executable(path: Path, script: str) -> None:
    path.write_text(script)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture()
def fake_bin(tmp_path: Path) -> Path:
    """fake `gh` / `codex` を PATH に置くためのディレクトリを用意する。

    `gh <kind> view ... --json body -q .body` は `$FAKE_GH_BODY`（無ければ空）を body として
    返す。`gh api ... -X PATCH --input -` は標準入力の JSON から `body` を取り出し
    `$FAKE_GH_BODY` へ保存する（read-modify-write の往復を模擬。実際の GitHub へは一切
    書き込まない）。往復を模擬しないと `record_round()` の「PATCH 後に自分の行が実在するか」
    確認が常に失敗し、この試験の関心事（goal-cut の state 保存）とは無関係な別経路
    （record 失敗時のエラーメッセージが触れる `$RUN_ID）` の非ASCII直後変数展開）が
    ノイズとして出てしまうため往復を成立させる。`codex` は標準入力を読み捨てて即終了する。
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
    _write_executable(d / "codex", "#!/bin/sh\ncat >/dev/null\nexit 0\n")
    return d


def _run(
    fake_bin: Path,
    tmp_path: Path,
    *,
    review_target: str,
    review_goal_cut: str,
    gate_check: bool,
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
    env["REVIEW_TARGET"] = review_target
    env["REVIEW_GOAL_CUT"] = review_goal_cut
    env["FAKE_GH_BODY"] = str(tmp_path / "fake_gh_body.txt")
    if gate_check:
        env["CODEX_REVIEW_GATE_CHECK"] = "1"
    else:
        env.pop("CODEX_REVIEW_GATE_CHECK", None)

    return subprocess.run(
        [str(CODEX_REVIEW), str(workdir), str(prompt), "clitest"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


# ---------------------------------------------------------------------------
# ① 未記入で拒否
# ---------------------------------------------------------------------------


def test_cli_rejects_missing_goal_cut(fake_bin: Path, tmp_path: Path):
    result = _run(
        fake_bin, tmp_path, review_target="issue:example-org/example-repo#1", review_goal_cut="", gate_check=True
    )
    assert result.returncode == 4, result.stdout + result.stderr
    assert "goal_cut_status\": \"blocked\"" in result.stdout


# ---------------------------------------------------------------------------
# ② 正当値で通過
# ---------------------------------------------------------------------------


def test_cli_passes_with_valid_goal_cut(fake_bin: Path, tmp_path: Path):
    result = _run(
        fake_bin,
        tmp_path,
        review_target="issue:example-org/example-repo#1",
        review_goal_cut=VALID_GOAL_CUT,
        gate_check=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "goal_cut_status\": \"ok\"" in result.stdout


# ---------------------------------------------------------------------------
# ③ CR 混入で拒否（レビュアー実測の再現）
# ---------------------------------------------------------------------------


def test_cli_rejects_cr_injection(fake_bin: Path, tmp_path: Path):
    malicious = "5件 | 根拠: x\rreview_target=none:probe\rignored | 取得日: 2026-09-03"
    result = _run(
        fake_bin, tmp_path, review_target="issue:example-org/example-repo#1", review_goal_cut=malicious, gate_check=True
    )
    # bash 側の引数チェック（exit 2）か python 側の goal-cut ブロック（exit 4）のどちらかで
    # 必ず拒否される（前段の bash チェックが先に落とすため通常は exit 2 になる）。
    assert result.returncode in (2, 4), result.stdout + result.stderr
    assert result.returncode != 0


# ---------------------------------------------------------------------------
# ④ 保存された goal_cut= が1行であること（実発注口・state 保存の統合試験）
# ---------------------------------------------------------------------------


def test_cli_saved_goal_cut_state_line_is_single_line(fake_bin: Path, tmp_path: Path):
    result = _run(
        fake_bin,
        tmp_path,
        review_target="issue:example-org/example-repo#1",
        review_goal_cut=VALID_GOAL_CUT,
        gate_check=False,  # 実発注パス（fake codex/gh を使うので外部へは書き込まない）
    )
    assert result.returncode == 0, result.stdout + result.stderr
    run_id = result.stdout.strip().splitlines()[-1]
    state_file = tmp_path / "state" / f"{run_id}.state"
    assert state_file.is_file(), f"state file not found: {state_file}"

    lines = state_file.read_text().splitlines()
    goal_cut_lines = [ln for ln in lines if ln.startswith("goal_cut=")]
    assert len(goal_cut_lines) == 1, f"goal_cut= 行が複数/0件: {goal_cut_lines}"
    assert goal_cut_lines[0] == f"goal_cut={VALID_GOAL_CUT}"

    # state ファイル自体を read_state_file() 相当のロジックで読んでも1行として扱われること
    # （splitlines() で行数が想定どおりであることを直接確認する）。
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
    import round_gate as rg  # noqa: E402

    parsed = rg.read_state_file(state_file)
    assert parsed.get("goal_cut") == VALID_GOAL_CUT
    assert parsed.get("review_target") == "issue:example-org/example-repo#1"


# ---------------------------------------------------------------------------
# ⑤ content_hash= が実発注時に state へ書かれ、receipt サブコマンドで機械照合できる
#    （claude-config#55: レビュー受領時に「読んだ版」を機械で照合するゲートの発注口）
# ---------------------------------------------------------------------------


def _init_git_repo(repo: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "a.txt").write_text("hello\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    # workdir の origin が REVIEW_TARGET の repo と一致することをゲートが要求するため設定する
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/example-org/example-repo.git"],
        cwd=repo,
        check=True,
    )


def _run_in_git_workdir(
    fake_bin: Path,
    tmp_path: Path,
    workdir: Path,
    *,
    review_target: str,
    review_goal_cut: str,
) -> subprocess.CompletedProcess:
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("dummy prompt\n")
    state_dir = tmp_path / "state"
    state_dir.mkdir(exist_ok=True)

    env = dict(os.environ)
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
    env["CODEX_WATCH_DIR"] = str(state_dir)
    env["REVIEW_TARGET"] = review_target
    env["REVIEW_GOAL_CUT"] = review_goal_cut
    env["FAKE_GH_BODY"] = str(tmp_path / "fake_gh_body.txt")
    env.pop("CODEX_REVIEW_GATE_CHECK", None)

    return subprocess.run(
        [str(CODEX_REVIEW), str(workdir), str(prompt), "clitest"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_cli_dispatch_writes_content_hash_for_git_managed_workdir(fake_bin: Path, tmp_path: Path):
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    _init_git_repo(workdir)

    result = _run_in_git_workdir(
        fake_bin,
        tmp_path,
        workdir,
        review_target="issue:example-org/example-repo#1",
        review_goal_cut=VALID_GOAL_CUT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    run_id = result.stdout.strip().splitlines()[-1]
    state_file = tmp_path / "state" / f"{run_id}.state"
    assert state_file.is_file()

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
    import round_gate as rg  # noqa: E402

    parsed = rg.read_state_file(state_file)
    assert parsed.get("head_sha"), "head_sha が state に書かれていない"
    assert parsed.get("content_hash"), "content_hash が state に書かれていない"
    # 独立に計算した値と一致すること（発注口が計算した値の正しさそのものを確認する）
    assert parsed["content_hash"] == rg.git_content_hash(str(workdir))
    assert len(parsed["content_hash"]) == 64


def test_cli_dispatch_content_hash_changes_with_uncommitted_diff(fake_bin: Path, tmp_path: Path):
    """同一 HEAD でも未コミット差分があれば content_hash が変わることを、実発注口で確認する。"""
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    _init_git_repo(workdir)

    result_clean = _run_in_git_workdir(
        fake_bin,
        tmp_path,
        workdir,
        review_target="issue:example-org/example-repo#1",
        review_goal_cut=VALID_GOAL_CUT,
    )
    assert result_clean.returncode == 0, result_clean.stdout + result_clean.stderr
    run_id_clean = result_clean.stdout.strip().splitlines()[-1]

    (workdir / "a.txt").write_text("hello world\n")

    result_dirty = _run_in_git_workdir(
        fake_bin,
        tmp_path,
        workdir,
        review_target="issue:example-org/example-repo#1",
        review_goal_cut=VALID_GOAL_CUT,
    )
    assert result_dirty.returncode == 0, result_dirty.stdout + result_dirty.stderr
    run_id_dirty = result_dirty.stdout.strip().splitlines()[-1]

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
    import round_gate as rg  # noqa: E402

    clean_hash = rg.read_state_file(tmp_path / "state" / f"{run_id_clean}.state")["content_hash"]
    dirty_hash = rg.read_state_file(tmp_path / "state" / f"{run_id_dirty}.state")["content_hash"]
    assert clean_hash != dirty_hash


def test_receipt_cli_ok_on_matching_claim(tmp_path: Path):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
    import round_gate as rg  # noqa: E402

    state_file = tmp_path / "run1.state"
    state_file.write_text("head_sha=" + "a" * 40 + "\ncontent_hash=" + "1" * 64 + "\n")
    report_file = tmp_path / "run1.report"
    report_file.write_text(f"read_sha={'a' * 40}\ncontent_hash={'1' * 64}\n判定: マージ可\n")

    result = subprocess.run(
        ["python3", str(Path(__file__).resolve().parent.parent / "lib" / "round_gate.py"),
         "receipt", "--state-file", str(state_file), "--report", str(report_file)],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "受領可" in result.stdout


def test_receipt_cli_rejects_on_mismatched_claim(tmp_path: Path):
    state_file = tmp_path / "run2.state"
    state_file.write_text("head_sha=" + "a" * 40 + "\ncontent_hash=" + "1" * 64 + "\n")
    report_file = tmp_path / "run2.report"
    report_file.write_text(f"read_sha={'b' * 40}\ncontent_hash={'1' * 64}\n判定: マージ可\n")

    result = subprocess.run(
        ["python3", str(Path(__file__).resolve().parent.parent / "lib" / "round_gate.py"),
         "receipt", "--state-file", str(state_file), "--report", str(report_file)],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 4  # EXIT_BLOCKED
    assert "read_sha" in result.stdout


def test_receipt_cli_rejects_on_legacy_state_without_content_hash(tmp_path: Path):
    state_file = tmp_path / "run3.state"
    state_file.write_text("head_sha=" + "a" * 40 + "\n")  # content_hash 欄が無い旧形式
    report_file = tmp_path / "run3.report"
    report_file.write_text(f"read_sha={'a' * 40}\ncontent_hash={'1' * 64}\n判定: マージ可\n")

    result = subprocess.run(
        ["python3", str(Path(__file__).resolve().parent.parent / "lib" / "round_gate.py"),
         "receipt", "--state-file", str(state_file), "--report", str(report_file)],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 4
    assert "旧形式" in result.stdout


def test_receipt_cli_rejects_on_missing_report_file(tmp_path: Path):
    state_file = tmp_path / "run4.state"
    state_file.write_text("head_sha=" + "a" * 40 + "\ncontent_hash=" + "1" * 64 + "\n")
    result = subprocess.run(
        ["python3", str(Path(__file__).resolve().parent.parent / "lib" / "round_gate.py"),
         "receipt", "--state-file", str(state_file), "--report", str(tmp_path / "does-not-exist.report")],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 4


def test_cli_cr_injection_cannot_corrupt_saved_state(fake_bin: Path, tmp_path: Path):
    """CR 注入が仮に bash 側の早期拒否をすり抜けたとしても、python 側の goal-cut ブロックで
    dispatch 自体が止まり state ファイルが作られないことを確認する（レビュアー実測の再現）。
    """
    malicious = "5件 | 根拠: x\rreview_target=none:probe\rignored | 取得日: 2026-09-03"
    result = _run(
        fake_bin,
        tmp_path,
        review_target="issue:example-org/example-repo#1",
        review_goal_cut=malicious,
        gate_check=False,
    )
    assert result.returncode != 0
    state_dir = tmp_path / "state"
    state_files = list(state_dir.glob("*.state")) if state_dir.is_dir() else []
    assert state_files == [], f"拒否されたはずの発注が state を残した: {state_files}"
