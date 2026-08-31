"""巡数ゲート（lib/round_gate.py）のテスト。

方針:
- codex CLI / LLM / gh は一切呼ばない。gh 相当の I/O は fetch_body / patch_body を差し替えて模擬する。
- 本文フィクスチャは実 PR（#537 #559 #560 #563, todoroki-godai/evolve-anything）から取得した
  実データ（tests/fixtures/*.body.txt）。2026-08-25 取得。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

LIB_DIR = Path(__file__).resolve().parent.parent / "lib"
sys.path.insert(0, str(LIB_DIR))

import round_gate as rg  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text()


BODY_563 = load("pr563.body.txt")
BODY_559 = load("pr559.body.txt")
BODY_560 = load("pr560.body.txt")
BODY_537 = load("pr537.body.txt")


# ---------------------------------------------------------------------------
# 実データでの正規表現 parse（design-gate-v3.md §3 の evidence 表の再現）
# ---------------------------------------------------------------------------


def test_parse_inherited_pr_numbers_real_data():
    assert rg.parse_inherited_pr_numbers(BODY_563) == [559]
    assert rg.parse_inherited_pr_numbers(BODY_560) == [537]
    assert rg.parse_inherited_pr_numbers(BODY_559) == []
    assert rg.parse_inherited_pr_numbers(BODY_537) == []


def test_parse_approval_rounds_real_data():
    # #563 は「巡3 の人間承認」を1件持つ
    assert rg.parse_approval_rounds(BODY_563) == [3]
    assert rg.parse_approval_rounds(BODY_559) == []
    assert rg.parse_approval_rounds(BODY_560) == []
    assert rg.parse_approval_rounds(BODY_537) == []


def test_parse_total_cap_real_data():
    assert rg.parse_total_cap(BODY_563) == 5
    assert rg.parse_total_cap(BODY_559) is None


def test_has_verdict_real_data():
    assert rg.has_verdict(BODY_563) is True  # "### 裁定: ①縮小してマージ"
    # #559 は「巡2 後の裁定（人間）: 縮小してマージ」という**巡ごとの裁定メモ**を含む。
    # regex は固定3種のみ（design §3）で文脈を判定しないため、ここも True になる
    # （族2巡打ち切りの最終裁定と、巡単位の裁定メモを区別できないのは既知の限界。残課題に明記）。
    assert rg.has_verdict(BODY_559) is True
    assert rg.has_verdict(BODY_537) is False


# ---------------------------------------------------------------------------
# target / none 解析
# ---------------------------------------------------------------------------


def test_parse_target_pr():
    t = rg.parse_target("pr:todoroki-godai/evolve-anything#563")
    assert t.kind == "pr" and t.owner == "todoroki-godai" and t.repo == "evolve-anything" and t.number == 563
    assert t.key() == "pr:todoroki-godai/evolve-anything#563"


def test_parse_target_issue():
    t = rg.parse_target("issue:owner/repo#7")
    assert t.kind == "issue" and t.number == 7


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "pr:owner/repo",  # 番号なし
        "pr#5",  # スキーム区切りなし
        "prowner/repo#5",
        "pr:owner/repo#5\nsneaky=1",  # 改行注入
    ],
)
def test_parse_target_rejects_malformed(raw):
    with pytest.raises(rg.Indeterminate):
        rg.parse_target(raw)


def test_is_none_target():
    assert rg.is_none_target("none:probe") == "probe"
    assert rg.is_none_target("pr:owner/repo#1") is None


def test_is_none_target_rejects_empty_reason():
    with pytest.raises(rg.Indeterminate):
        rg.is_none_target("none:")


def test_is_none_target_rejects_newline_injection():
    with pytest.raises(rg.Indeterminate):
        rg.is_none_target("none:ok\nreview_target=pr:owner/repo#1")


# ---------------------------------------------------------------------------
# decide() の閾値（design §2 の判定表そのもの）
# ---------------------------------------------------------------------------


def test_decide_pass_1_and_2():
    assert rg.decide(1, "").status == "pass"
    assert rg.decide(2, "").status == "pass"


def test_decide_3_to_5_needs_approval_and_cap():
    # 承認なし → block
    assert rg.decide(3, "本文になにもなし").status == "blocked"
    # 承認はあるが総上限が無い → block
    assert rg.decide(3, "巡3の人間承認をする").status == "blocked"
    # 承認 + 十分な総上限 → pass
    assert rg.decide(3, "巡3の人間承認\n総上限: 5巡").status == "pass"
    # 承認はあるが総上限を超過 → block
    assert rg.decide(6, "巡3の人間承認\n総上限: 5巡").status == "blocked"


def test_decide_6_plus_needs_verdict_even_with_approval():
    body_with_approval_only = "巡6の人間承認\n総上限: 10巡"
    assert rg.decide(6, body_with_approval_only).status == "blocked"
    body_with_verdict = body_with_approval_only + "\n### 裁定: 縮小してマージ"
    assert rg.decide(6, body_with_verdict).status == "pass"


def test_decide_real_pr563_at_round3_passes():
    # #563 は総上限5・承認済みの巡3。実データでそのまま pass すること。
    d = rg.decide(3, BODY_563)
    assert d.status == "pass"


# ---------------------------------------------------------------------------
# 台帳（state dir）由来の巡束ね
# ---------------------------------------------------------------------------


def write_state(state_dir: Path, run_id: str, target: str, head: str, started_at: float):
    (state_dir / f"{run_id}.state").write_text(
        f"run_id={run_id}\nreview_target={target}\nhead_sha={head}\nstarted_at={started_at}\n"
    )


def test_ledger_bundles_same_target_same_head(tmp_path: Path):
    write_state(tmp_path, "r1", "pr:o/r#1", "aaa111", 100)
    write_state(tmp_path, "r2", "pr:o/r#1", "aaa111", 200)  # 同一 HEAD の並行/追加発注
    # 同一 HEAD なら同じ巡（1巡目のまま）
    assert rg.ledger_own_round(tmp_path, "pr:o/r#1", "aaa111") == 1


def test_ledger_advances_on_new_head(tmp_path: Path):
    write_state(tmp_path, "r1", "pr:o/r#1", "aaa111", 100)
    # 新しい HEAD は次の巡になる
    assert rg.ledger_own_round(tmp_path, "pr:o/r#1", "bbb222") == 2


def test_ledger_ignores_other_targets(tmp_path: Path):
    write_state(tmp_path, "r1", "pr:o/r#2", "aaa111", 100)
    assert rg.ledger_own_round(tmp_path, "pr:o/r#1", "aaa111") == 1


def test_none_dispatch_count(tmp_path: Path):
    write_state(tmp_path, "n1", "none:probe", "unmanaged", 1)
    write_state(tmp_path, "n2", "none:probe2", "unmanaged", 2)
    assert rg.none_dispatch_count(tmp_path, "/some/workdir") == 0  # workdir 未記録なので0
    (tmp_path / "n1.state").write_text("review_target=none:probe\nworkdir=/w\n")
    (tmp_path / "n2.state").write_text("review_target=none:probe2\nworkdir=/w\n")
    assert rg.none_dispatch_count(tmp_path, "/w") == 2


# ---------------------------------------------------------------------------
# target_total_rounds: 前身合算・循環・過深・本文優先（大きい方）
# ---------------------------------------------------------------------------


def make_fetcher(bodies: dict[str, str]):
    def fetch(target: rg.Target) -> str:
        return bodies[target.key()]

    return fetch


def test_target_total_rounds_new_target_no_predecessor(tmp_path: Path):
    t = rg.Target("pr", "o", "r", 1)
    fetch = make_fetcher({t.key(): "本文になにもなし"})
    total = rg.target_total_rounds(t, tmp_path, fetch, [], pending_new_head="sha1")
    assert total == 1  # 新規 HEAD の初回発注


def test_target_total_rounds_bundles_same_head_across_calls(tmp_path: Path):
    t = rg.Target("pr", "o", "r", 1)
    fetch = make_fetcher({t.key(): ""})
    write_state(tmp_path, "r1", t.key(), "sha1", 100)
    total = rg.target_total_rounds(t, tmp_path, fetch, [], pending_new_head="sha1")
    assert total == 1  # 既存の同一 HEAD に束ねられる（新規巡を追加しない）


def test_target_total_rounds_sums_predecessor_via_body_inherit(tmp_path: Path):
    # #563 スタイル: own body 側の承認行が総合計3を宣言、前身 #559 は台帳もbodyの承認行も無い
    # （#559 のフィクスチャは approval regex に一致しない旧形式）ので predecessor own_round=0。
    t563 = rg.Target("pr", "todoroki-godai", "evolve-anything", 563)
    t559 = rg.Target("pr", "todoroki-godai", "evolve-anything", 559)
    fetch = make_fetcher({t563.key(): BODY_563, t559.key(): BODY_559})
    total = rg.target_total_rounds(t563, tmp_path, fetch, [], pending_new_head=None)
    # body_own_round(#563) = 3 (「巡3の人間承認」) が ledger(0)+predecessor(0) より大きいので採用される
    assert total == 3


def test_target_total_rounds_predecessor_chain_via_env(tmp_path: Path):
    a = rg.Target("pr", "o", "r", 1)
    b = rg.Target("pr", "o", "r", 2)
    # a の台帳に2巡分の実績を積む → predecessor 側の寄与は2
    write_state(tmp_path, "a1", a.key(), "shaA1", 100)
    write_state(tmp_path, "a2", a.key(), "shaA2", 200)
    fetch = make_fetcher({a.key(): "", b.key(): ""})
    total = rg.target_total_rounds(b, tmp_path, fetch, [a], pending_new_head="shaB1")
    assert total == 1 + 2  # b 自身の新規1巡 + a の2巡


def test_target_total_rounds_body_wins_when_ledger_lost(tmp_path: Path):
    # state dir が消失（空）していても、本文の承認行「巡5の人間承認」が5を示せばそちらを採る
    t = rg.Target("pr", "o", "r", 1)
    fetch = make_fetcher({t.key(): "巡5の人間承認\n総上限: 8巡"})
    total = rg.target_total_rounds(t, tmp_path, fetch, [], pending_new_head="shaX")
    assert total == 5  # ledger は1（新規1巡）だが body の5が大きいので5


def test_target_total_rounds_circular_chain_is_indeterminate(tmp_path: Path):
    a = rg.Target("pr", "o", "r", 1)
    b = rg.Target("pr", "o", "r", 2)
    fetch = make_fetcher(
        {
            a.key(): "前身 PR #2 で 設計0巡・コード1巡 消化済み（継承）。",
            b.key(): "前身 PR #1 で 設計0巡・コード1巡 消化済み（継承）。",
        }
    )
    with pytest.raises(rg.Indeterminate):
        rg.target_total_rounds(a, tmp_path, fetch, [], pending_new_head="shaA")


def test_target_total_rounds_too_deep_chain_is_indeterminate(tmp_path: Path):
    n = 8
    targets = [rg.Target("pr", "o", "r", i) for i in range(n)]
    bodies = {}
    for i in range(n - 1):
        bodies[targets[i].key()] = f"前身 PR #{i + 1} で 設計0巡・コード1巡 消化済み（継承）。"
    bodies[targets[n - 1].key()] = ""
    fetch = make_fetcher(bodies)
    with pytest.raises(rg.Indeterminate):
        rg.target_total_rounds(targets[0], tmp_path, fetch, [], pending_new_head="sha0")


# ---------------------------------------------------------------------------
# 本文への行追記 / backfill（純粋関数）
# ---------------------------------------------------------------------------


def test_append_round_row_creates_section_when_absent():
    body = "本文\n\nrefs #1"
    row = rg.render_round_row(1, "コード", "2026-08-25 10:00", "abc1234", "codex")
    new_body = rg.append_round_row(body, row)
    assert rg.ROUND_SECTION_TITLE in new_body
    assert row in new_body
    assert rg.row_present(new_body, row)


def test_append_round_row_appends_to_existing_table():
    body = (
        "## 巡の履歴\n\n"
        + rg.ROUND_ROW_HEADER
        + "\n"
        + rg.ROUND_ROW_SEP
        + "\n"
        + "| 1 | 設計 | 2026-08-20 | - | tacchi | 1000 | - |\n\n"
        "## 次のセクション\n本文\n"
    )
    row = rg.render_round_row(2, "コード", "2026-08-25", "def5678", "codex")
    new_body = rg.append_round_row(body, row)
    assert row in new_body
    # 元の巡1の行も残っている
    assert "| 1 | 設計 |" in new_body
    # 次セクションより前に挿入されている
    assert new_body.index(row) < new_body.index("## 次のセクション")


def test_append_round_row_real_pr563_body():
    row = rg.render_round_row(4, "コード", "2026-08-25 18:00", "abcdef1", "codex")
    new_body = rg.append_round_row(BODY_563, row)
    assert rg.row_present(new_body, row)
    # 既存の巡3の行が消えていない
    assert "| 3 | コード | 2026-08-25 12:44 JST | 672ab435 | codex | 133,840" in new_body


def test_backfill_measuring_row_replaces_placeholder():
    body = "## 巡の履歴\n\n" + rg.ROUND_ROW_HEADER + "\n" + rg.ROUND_ROW_SEP + "\n"
    row = rg.render_round_row(1, "コード", "2026-08-25", "abc1234", "codex")
    body = rg.append_round_row(body, row)
    new_body, found = rg.backfill_measuring_row(body, 1, "65880")
    assert found
    assert "65880" in new_body
    assert rg.MEASURING_PLACEHOLDER not in new_body


def test_backfill_measuring_row_no_match_returns_false():
    body = "## 巡の履歴\n\n" + rg.ROUND_ROW_HEADER + "\n" + rg.ROUND_ROW_SEP + "\n"
    new_body, found = rg.backfill_measuring_row(body, 99, "123")
    assert not found
    assert new_body == body


# ---------------------------------------------------------------------------
# トークン backfill 突合（session id ↔ jsonl）
# ---------------------------------------------------------------------------


def test_extract_session_id():
    log = "hook: Stop Completed\nsession id: 01a037fe-925b-7020-ab45-c1d6c19dfade\nmore\n"
    assert rg.extract_session_id(log) == "01a037fe-925b-7020-ab45-c1d6c19dfade"


def test_extract_session_id_missing():
    assert rg.extract_session_id("no session id here") is None


def test_find_rollout_jsonl(tmp_path: Path):
    day_dir = tmp_path / "2026" / "08" / "25"
    day_dir.mkdir(parents=True)
    target = day_dir / "rollout-2026-08-25T17-26-42-01a03807-60a7-7e72-ac26-e30898e9e3e6.jsonl"
    target.write_text("{}")
    found = rg.find_rollout_jsonl(tmp_path, "01a03807-60a7-7e72-ac26-e30898e9e3e6")
    assert found == target


def test_extract_total_tokens_from_jsonl_takes_last():
    text = (
        '{"a":1,"total_token_usage":{"input_tokens":1,"total_tokens":100}}\n'
        '{"b":2,"total_token_usage":{"input_tokens":2,"total_tokens":9999}}\n'
    )
    assert rg.extract_total_tokens_from_jsonl(text) == 9999


def test_compute_backfill_value_ok(tmp_path: Path):
    day_dir = tmp_path / "2026" / "08" / "25"
    day_dir.mkdir(parents=True)
    (day_dir / "rollout-xxx-uuid1234.jsonl").write_text(
        '{"total_token_usage":{"total_tokens":42}}\n'
    )
    log = "session id: uuid1234\n"
    value, note = rg.compute_backfill_value(log, tmp_path)
    assert note == "ok"
    assert value == "42"


def test_compute_backfill_value_no_session_id(tmp_path: Path):
    value, note = rg.compute_backfill_value("no id", tmp_path)
    assert note == "no_session_id"
    assert value.startswith("計測不能")


def test_compute_backfill_value_no_jsonl(tmp_path: Path):
    log = "session id: does-not-exist\n"
    value, note = rg.compute_backfill_value(log, tmp_path)
    assert note == "no_jsonl"
    assert value.startswith("計測不能")


# ---------------------------------------------------------------------------
# run_gate: usage error / none 上限 / bypass / repo 不一致 / 判定不能
# ---------------------------------------------------------------------------


def test_run_gate_usage_error_on_missing_target(tmp_path: Path):
    result = rg.run_gate("", "/tmp", tmp_path, "", "")
    assert result["exit_code"] == rg.EXIT_USAGE


def test_run_gate_bypass(tmp_path: Path):
    result = rg.run_gate("pr:o/r#1", "/tmp", tmp_path, "", "手動確認済み")
    assert result["exit_code"] == rg.EXIT_PASS
    assert result["status"] == "bypass"


def test_run_gate_bypass_ignores_target_entirely(tmp_path: Path):
    # target が壊れていても bypass が最優先される
    result = rg.run_gate("not-a-valid-target", "/tmp", tmp_path, "", "probe")
    assert result["exit_code"] == rg.EXIT_PASS


def test_run_gate_bypass_rejects_whitespace_only_reason(tmp_path: Path):
    # CODEX_REVIEW_NO_GATE=" " のような空白のみの「理由」は「理由必須」の実質的な回避になる。
    # bypass を成立させず、通常ゲート（REVIEW_TARGET 必須）へ進むこと。
    result = rg.run_gate("", "/tmp", tmp_path, "", "   ")
    assert result["status"] != "bypass"
    assert result["exit_code"] == rg.EXIT_USAGE


def test_none_dispatch_count_normalizes_trailing_slash(tmp_path: Path):
    # workdir の末尾スラッシュ違いで別 workdir 扱いになり none: 上限を回避できてはならない。
    (tmp_path / "n1.state").write_text("review_target=none:a\nworkdir=/w/dir\n")
    (tmp_path / "n2.state").write_text("review_target=none:b\nworkdir=/w/dir/\n")
    assert rg.none_dispatch_count(tmp_path, "/w/dir") == 2
    assert rg.none_dispatch_count(tmp_path, "/w/dir/") == 2


def test_run_gate_none_cap_not_evaded_by_trailing_slash_variants(tmp_path: Path):
    variants = ["/w", "/w/", "/w/.", "/w/sub/.."]
    for i, wd in enumerate(variants[:-1]):
        r = rg.run_gate(f"none:probe{i}", wd, tmp_path, "", "")
        assert r["exit_code"] == rg.EXIT_PASS
        (tmp_path / f"n{i}.state").write_text(f"review_target={r['record_target']}\nworkdir={wd}\n")
    blocked = rg.run_gate("none:one-more", variants[-1], tmp_path, "", "")
    assert blocked["exit_code"] == rg.EXIT_BLOCKED


def test_none_dispatch_count_normalizes_symlink(tmp_path: Path):
    # symlink 経由の workdir を実体と別物として数えると none: 上限を無限に回避できてしまう。
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    link_dir = tmp_path / "real-link"
    link_dir.symlink_to(real_dir)

    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "n1.state").write_text(f"review_target=none:a\nworkdir={real_dir}\n")
    (state_dir / "n2.state").write_text(f"review_target=none:b\nworkdir={link_dir}\n")

    assert rg.normalize_workdir(str(real_dir)) == rg.normalize_workdir(str(link_dir))
    assert rg.none_dispatch_count(state_dir, str(real_dir)) == 2
    assert rg.none_dispatch_count(state_dir, str(link_dir)) == 2


def test_run_gate_none_cap_not_evaded_by_symlink(tmp_path: Path):
    real_dir = tmp_path / "real2"
    real_dir.mkdir()
    link_dir = tmp_path / "real2-link"
    link_dir.symlink_to(real_dir)

    state_dir = tmp_path / "state2"
    state_dir.mkdir()
    workdirs = [str(real_dir), str(link_dir), str(real_dir)]
    for i, wd in enumerate(workdirs):
        r = rg.run_gate(f"none:probe{i}", wd, state_dir, "", "")
        assert r["exit_code"] == rg.EXIT_PASS
        (state_dir / f"n{i}.state").write_text(f"review_target={r['record_target']}\nworkdir={wd}\n")
    # symlink 経由でも4件目（実体からもリンクからも）は拒否される
    blocked_via_link = rg.run_gate("none:one-more", str(link_dir), state_dir, "", "")
    assert blocked_via_link["exit_code"] == rg.EXIT_BLOCKED


# ---------------------------------------------------------------------------
# 同一巡（同一 target × 同一 HEAD）内の発注本数上限
# ---------------------------------------------------------------------------


def test_same_head_dispatch_count(tmp_path: Path):
    write_state(tmp_path, "r1", "pr:o/r#1", "sha1", 100)
    write_state(tmp_path, "r2", "pr:o/r#1", "sha1", 200)
    write_state(tmp_path, "r3", "pr:o/r#1", "sha2", 300)  # 別 HEAD はカウントしない
    assert rg.same_head_dispatch_count(tmp_path, "pr:o/r#1", "sha1") == 2
    assert rg.same_head_dispatch_count(tmp_path, "pr:o/r#1", "sha2") == 1
    assert rg.same_head_dispatch_count(tmp_path, "pr:o/r#9", "sha1") == 0  # 別 target


def test_run_gate_blocks_after_max_same_head_dispatches(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(rg, "git_remote_repo", lambda workdir: ("o", "r"))
    monkeypatch.setattr(rg, "git_head_sha", lambda workdir: "shaFIXED")
    fetch = make_fetcher({"pr:o/r#1": ""})

    # 1〜3本目は通過する（同一巡＝同一 HEAD の束ねは変えない）
    for i in range(rg.MAX_SAME_HEAD_DISPATCHES):
        result = rg.run_gate("pr:o/r#1", "/tmp", tmp_path, "", "", fetch_body=fetch)
        assert result["exit_code"] == rg.EXIT_PASS, f"{i}本目で拒否された（想定外）"
        assert result["total_round"] == 1  # 同一 HEAD なので巡は増えない（束ね判定は不変）
        write_state(tmp_path, f"same{i}", "pr:o/r#1", "shaFIXED", 100 + i)

    # 4本目（同一巡の発注上限を超える）は拒否される
    blocked = rg.run_gate("pr:o/r#1", "/tmp", tmp_path, "", "", fetch_body=fetch)
    assert blocked["exit_code"] == rg.EXIT_BLOCKED
    assert "同一巡" in blocked["message"]


def test_run_gate_same_head_cap_resets_when_head_advances(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(rg, "git_remote_repo", lambda workdir: ("o", "r"))
    fetch = make_fetcher({"pr:o/r#1": ""})

    monkeypatch.setattr(rg, "git_head_sha", lambda workdir: "shaOLD")
    for i in range(rg.MAX_SAME_HEAD_DISPATCHES):
        write_state(tmp_path, f"old{i}", "pr:o/r#1", "shaOLD", 100 + i)
    blocked = rg.run_gate("pr:o/r#1", "/tmp", tmp_path, "", "", fetch_body=fetch)
    assert blocked["exit_code"] == rg.EXIT_BLOCKED

    # HEAD が進めば新しい巡として再び通過する
    monkeypatch.setattr(rg, "git_head_sha", lambda workdir: "shaNEW")
    passed = rg.run_gate("pr:o/r#1", "/tmp", tmp_path, "", "", fetch_body=fetch)
    assert passed["exit_code"] == rg.EXIT_PASS
    assert passed["total_round"] == 2


def test_run_gate_case_mismatched_repo_is_rejected_not_silently_matched(tmp_path: Path, monkeypatch):
    # 大文字小文字違いの owner/repo は「同じリポジトリ」と誤認せず拒否する（fail-safe。
    # 誤って一致扱いにすると別リポジトリの本文を書き換えるリスクがある）。
    monkeypatch.setattr(rg, "git_remote_repo", lambda workdir: ("todoroki-godai", "evolve-anything"))
    result = rg.run_gate("pr:Todoroki-Godai/Evolve-Anything#1", "/tmp", tmp_path, "", "")
    assert result["exit_code"] == rg.EXIT_BLOCKED


def test_run_gate_none_passes_until_cap(tmp_path: Path):
    for i in range(rg.MAX_NONE_DISPATCHES):
        r = rg.run_gate(f"none:probe{i}", "/w", tmp_path, "", "")
        assert r["exit_code"] == rg.EXIT_PASS
        (tmp_path / f"n{i}.state").write_text(f"review_target={r['record_target']}\nworkdir=/w\n")
    blocked = rg.run_gate("none:one-too-many", "/w", tmp_path, "", "")
    assert blocked["exit_code"] == rg.EXIT_BLOCKED


def test_run_gate_repo_mismatch(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(rg, "git_remote_repo", lambda workdir: ("other-owner", "other-repo"))
    result = rg.run_gate("pr:todoroki-godai/evolve-anything#563", "/tmp", tmp_path, "", "")
    assert result["exit_code"] == rg.EXIT_BLOCKED
    assert "一致しません" in result["message"]


def test_run_gate_indeterminate_on_git_head_failure(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(rg, "git_remote_repo", lambda workdir: ("todoroki-godai", "evolve-anything"))

    def boom(workdir):
        raise rg.Indeterminate("判定不能: git rev-parse HEAD が失敗しました: fatal")

    monkeypatch.setattr(rg, "git_head_sha", boom)
    with pytest.raises(rg.Indeterminate):
        rg.run_gate("pr:todoroki-godai/evolve-anything#563", "/tmp", tmp_path, "", "")


def test_run_gate_pass_and_block_using_real_body(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(rg, "git_remote_repo", lambda workdir: ("todoroki-godai", "evolve-anything"))
    monkeypatch.setattr(rg, "git_head_sha", lambda workdir: "672ab435672ab435672ab435672ab435672ab43")
    fetch = make_fetcher(
        {
            "pr:todoroki-godai/evolve-anything#563": BODY_563,
            "pr:todoroki-godai/evolve-anything#559": BODY_559,
        }
    )
    result = rg.run_gate(
        "pr:todoroki-godai/evolve-anything#563", "/tmp", tmp_path, "", "", fetch_body=fetch
    )
    assert result["exit_code"] == rg.EXIT_PASS
    assert result["total_round"] == 3


def test_run_gate_block_when_body_has_no_approval(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(rg, "git_remote_repo", lambda workdir: ("o", "r"))
    monkeypatch.setattr(rg, "git_head_sha", lambda workdir: "sha-new")
    # 台帳に既に2巡分の実績（3巡目の新規発注になる）だが本文に承認行が無い
    write_state(tmp_path, "r1", "pr:o/r#9", "sha1", 100)
    write_state(tmp_path, "r2", "pr:o/r#9", "sha2", 200)
    fetch = make_fetcher({"pr:o/r#9": "本文になにもなし"})
    result = rg.run_gate("pr:o/r#9", "/tmp", tmp_path, "", "", fetch_body=fetch)
    assert result["exit_code"] == rg.EXIT_BLOCKED
    assert result["record_target"] == ""


# ---------------------------------------------------------------------------
# record_round / backfill_one（gh を monkeypatch で模擬。実 gh は呼ばない）
# ---------------------------------------------------------------------------


def test_record_round_skips_none_and_bypass(tmp_path: Path):
    for target_val in ("none:probe", "bypass", ""):
        sf = tmp_path / f"{target_val or 'empty'}.state".replace(":", "_")
        sf.write_text(f"review_target={target_val}\nround=1\n")
        result = rg.record_round(sf, tmp_path)
        assert result["status"] == "skipped"


def test_record_round_writes_row_and_confirms(tmp_path: Path):
    sf = tmp_path / "r1.state"
    sf.write_text(
        "review_target=pr:o/r#1\nround=1\nhead_sha=abcdef1234567\n"
        "started_at_human=2026-08-25 18:00:00\nreviewer=codex\nlog=" + str(tmp_path / "r1.log") + "\n"
    )
    (tmp_path / "r1.log").write_text("no session id\n")

    store = {"body": "本文\n"}

    def fetch(target):
        return store["body"]

    def patch(target, new_body):
        store["body"] = new_body

    result = rg.record_round(sf, tmp_path, fetch_body=fetch, patch_body=patch)
    assert result["status"] == "ok"
    assert "| 1 |" in store["body"]
    assert "abcdef1" in store["body"]


def test_record_round_reports_failure_when_row_not_confirmed(tmp_path: Path):
    sf = tmp_path / "r1.state"
    sf.write_text("review_target=pr:o/r#1\nround=1\nhead_sha=abcdef1\nlog=" + str(tmp_path / "r1.log") + "\n")
    (tmp_path / "r1.log").write_text("")

    def fetch(target):
        return "本文\n"

    def patch(target, new_body):
        pass  # 書いたことにするが、確認 fetch では反映されない（同時編集で消えたケースを模擬）

    result = rg.record_round(sf, tmp_path, fetch_body=fetch, patch_body=patch)
    assert result["status"] == "failed"


def test_backfill_one_not_yet_when_no_session_id(tmp_path: Path):
    sf = tmp_path / "r1.state"
    sf.write_text("review_target=pr:o/r#1\nround=1\nlog=" + str(tmp_path / "r1.log") + "\n")
    (tmp_path / "r1.log").write_text("no session id here\n")
    result = rg.backfill_one(sf, tmp_path)
    assert result["status"] == "not_yet"


def test_backfill_one_ok(tmp_path: Path):
    sf = tmp_path / "r1.state"
    log_path = tmp_path / "r1.log"
    sf.write_text(f"review_target=pr:o/r#1\nround=1\nlog={log_path}\n")
    log_path.write_text("session id: uuidZZZ\n")
    day_dir = tmp_path / "2026" / "08" / "25"
    day_dir.mkdir(parents=True)
    (day_dir / "rollout-x-uuidZZZ.jsonl").write_text('{"total_token_usage":{"total_tokens":777}}\n')

    store = {
        "body": "## 巡の履歴\n\n"
        + rg.ROUND_ROW_HEADER
        + "\n"
        + rg.ROUND_ROW_SEP
        + "\n"
        + rg.render_round_row(1, "コード", "2026-08-25", "abc1234", "codex")
        + "\n"
    }

    def fetch(target):
        return store["body"]

    def patch(target, new_body):
        store["body"] = new_body

    result = rg.backfill_one(sf, tmp_path, fetch_body=fetch, patch_body=patch)
    assert result["status"] == "ok"
    assert "777" in store["body"]
    assert rg.read_state_file(sf).get("backfilled") == "1"


def test_same_head_dispatch_limit_value_is_pinned():
    """上限値そのものを固定する。

    他のテストは range(MAX) で件数を導くため、定数を書き換えても追随して緑のままになる
    （同一巡の発注上限を静かに緩められる）。値自体をここで固定して、その変異を赤くする。
    """
    assert rg.MAX_SAME_HEAD_DISPATCHES == 3


# ---------------------------------------------------------------------------
# 「1文字も返さずに終わった発注」を同一巡の本数に数えない
#
# 外部モデルの容量エラー・起動失敗（PATH 不備等）で codex が即死すると、report が
# 空のまま state だけが残る。これを数えると、外部が不調な日は上限 3 本を空振りで
# 食いつぶして**レビューを一切通せなくなる**。レビューが実行された回数を数える。
# ---------------------------------------------------------------------------


def _dead_pid() -> int:
    """確実に生きていない PID を得る（起動して即 wait し回収済みにする）。"""
    import subprocess
    p = subprocess.Popen(["true"])
    p.wait()
    return p.pid


def write_state_full(state_dir, run_id, target, head, started_at, pid, report_path):
    lines = [
        f"run_id={run_id}",
        f"review_target={target}",
        f"head_sha={head}",
        f"started_at={started_at}",
    ]
    if pid is not None:
        lines.append(f"pid={pid}")
    if report_path is not None:
        lines.append(f"report={report_path}")
    (state_dir / f"{run_id}.state").write_text("\n".join(lines) + "\n")


class TestAbortedDispatchNotCounted:
    def test_missing_report_and_dead_process_is_not_counted(self, tmp_path):
        """陰性: report が生成されず、プロセスも死んでいる＝レビュー不成立。数えない。"""
        write_state_full(tmp_path, "r1", "pr:o/r#1", "sha1", 100,
                         _dead_pid(), str(tmp_path / "r1.report"))
        assert rg.same_head_dispatch_count(tmp_path, "pr:o/r#1", "sha1") == 0

    def test_empty_report_and_dead_process_is_not_counted(self, tmp_path):
        """陰性: report ファイルはあるが 0 バイトで、プロセスも死んでいる。数えない。"""
        rp = tmp_path / "r2.report"
        rp.write_text("")
        write_state_full(tmp_path, "r2", "pr:o/r#1", "sha1", 100, _dead_pid(), str(rp))
        assert rg.same_head_dispatch_count(tmp_path, "pr:o/r#1", "sha1") == 0

    def test_nonempty_report_is_counted(self, tmp_path):
        """陽性対照: report が非空なら、プロセスが終わっていても数える（レビューは成立した）。"""
        rp = tmp_path / "r3.report"
        rp.write_text("修正要\n")
        write_state_full(tmp_path, "r3", "pr:o/r#1", "sha1", 100, _dead_pid(), str(rp))
        assert rg.same_head_dispatch_count(tmp_path, "pr:o/r#1", "sha1") == 1

    def test_running_process_is_counted_even_without_report(self, tmp_path):
        """陽性対照: 実行中（プロセス生存）は report 未生成でも数える。
        ここを数えないと、並行に無制限へ発注できる抜け道になる。"""
        write_state_full(tmp_path, "r4", "pr:o/r#1", "sha1", 100,
                         os.getpid(), str(tmp_path / "r4.report"))
        assert rg.same_head_dispatch_count(tmp_path, "pr:o/r#1", "sha1") == 1

    def test_state_without_pid_or_report_is_counted(self, tmp_path):
        """陽性対照（後方互換・fail-safe）: pid / report が state に無い旧形式は
        判定できないので**数える側**へ倒す。"""
        write_state(tmp_path, "r5", "pr:o/r#1", "sha1", 100)
        assert rg.same_head_dispatch_count(tmp_path, "pr:o/r#1", "sha1") == 1

    def test_empty_report_without_pid_is_counted(self, tmp_path):
        """陽性対照（fail-safe の要）: report が空でも **pid が state に無ければ**
        生死を判定できないので数える。pid 不明を空振り扱いにすると、旧形式の state が
        すべて上限から消えて上限が骨抜きになる。"""
        rp = tmp_path / "r6.report"
        rp.write_text("")
        write_state_full(tmp_path, "r6", "pr:o/r#1", "sha1", 100, None, str(rp))
        assert rg.same_head_dispatch_count(tmp_path, "pr:o/r#1", "sha1") == 1

    def test_empty_report_with_non_numeric_pid_is_counted(self, tmp_path):
        """陽性対照: pid が数値でない壊れた state も判定不能として数える。"""
        rp = tmp_path / "r7.report"
        rp.write_text("")
        write_state_full(tmp_path, "r7", "pr:o/r#1", "sha1", 100, "not-a-pid", str(rp))
        assert rg.same_head_dispatch_count(tmp_path, "pr:o/r#1", "sha1") == 1

    def test_run_gate_does_not_block_when_all_dispatches_aborted(self, tmp_path, monkeypatch):
        """陰性（統合）: 3本すべてが空振りなら、4本目は上限で拒否されない。"""
        monkeypatch.setattr(rg, "git_remote_repo", lambda workdir: ("o", "r"))
        monkeypatch.setattr(rg, "git_head_sha", lambda workdir: "shaFIXED")
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        for i in range(rg.MAX_SAME_HEAD_DISPATCHES):
            write_state_full(state_dir, f"a{i}", "issue:o/r#1", "shaFIXED", 100 + i,
                             _dead_pid(), str(state_dir / f"a{i}.report"))
        res = rg.run_gate(
            workdir=str(tmp_path),
            target_raw="issue:o/r#1",
            state_dir=state_dir,
            fetch_body=lambda t: "",
            predecessor_env_raw="",
            no_gate_reason="",
        )
        assert res["status"] != "blocked" or "発注上限" not in res["message"], (
            "空振りだけで上限に達したと判定してはいけない"
        )
