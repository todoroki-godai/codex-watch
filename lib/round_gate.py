#!/usr/bin/env python3
"""巡数ゲート v3（台帳駆動） — codex-review 発注前に巡数を判定する。

設計正本: design-gate-v3.md（scratchpad。この実装はそこに書かれた仕様のみを実装する）。

契約の要旨（詳細は各関数の docstring）:
- 巡の単位は「同一 target × 同一 HEAD SHA」（state dir のヘッダ束ねで判定）。
- 前身の巡数は env REVIEW_PREDECESSOR + 本文の継承行（PR番号のみ抽出）から辿って合算する。
- ゲートが本文から読むのは3種の正規表現だけ（継承 PR 番号 / 承認行の巡番号+総上限 / 裁定行の有無）。
  巡数そのものを本文の表やコードブロックから数えることはしない（design 注記どおり）。
  「本文の巡数と台帳の巡数、大きい方を採る」は、承認行が明示する巡番号 vs 台帳(state dir) の
  比較として実装する（承認行は人間が書いた「その時点の巡番号」の記録なので、state dir 消失時の
  フォールバックとして機能する）。
- 判定は fail-closed。gh/git 呼び出し失敗・循環・過深は「判定不能」として拒否する。

このモジュールは純粋関数（parse_*, decide, ledger からの計算）と I/O 関数（gh api / git を呼ぶもの）を
分離してある。テストは純粋関数だけを対象にし、gh/codex/LLM は一切呼ばない。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# 定数・正規表現（design-gate-v3.md §3 のとおり。ここだけが正）
# ---------------------------------------------------------------------------

RE_INHERIT = re.compile(r"前身[^#]*PR[^#]*#([0-9]+)")
RE_APPROVAL = re.compile(r"巡[ \t]*([0-9]+)[ \t]*の人間承認")
RE_TOTAL_CAP = re.compile(r"総上限[:：][^0-9]*([0-9]+)")
RE_VERDICT = re.compile(r"裁定[:：]|裁定（人間）")

RE_TARGET = re.compile(r"^(pr|issue):([A-Za-z0-9_.\-]+)/([A-Za-z0-9_.\-]+)#([0-9]+)$")
RE_NONE_TARGET = re.compile(r"^none:(.*)$", re.DOTALL)

MAX_CHAIN_DEPTH = 5
MAX_NONE_DISPATCHES = 3
MAX_SAME_HEAD_DISPATCHES = 3  # 同一 target × 同一 HEAD（＝同一巡）内で許される発注本数の上限

# exit code 契約
EXIT_PASS = 0
EXIT_USAGE = 2
EXIT_BLOCKED = 4
EXIT_INDETERMINATE = 5


class Indeterminate(Exception):
    """判定不能。fail-closed で拒否する（reason を保持）。"""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


# ---------------------------------------------------------------------------
# ターゲット
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Target:
    kind: str  # "pr" | "issue"
    owner: str
    repo: str
    number: int

    def key(self) -> str:
        return f"{self.kind}:{self.owner}/{self.repo}#{self.number}"

    def repo_slug(self) -> str:
        return f"{self.owner}/{self.repo}"


def parse_target(raw: str) -> Target:
    """`pr:owner/repo#N` / `issue:owner/repo#N` を厳密にパースする。

    改行を含む値は state への行注入になるため拒否する（既存 codex-review の踏襲）。
    """
    if raw is None or raw == "":
        raise Indeterminate("REVIEW_TARGET が空です")
    if "\n" in raw:
        raise Indeterminate("REVIEW_TARGET に改行を含められません")
    m = RE_TARGET.match(raw)
    if not m:
        raise Indeterminate(
            f"REVIEW_TARGET の形式が不正です（pr:owner/repo#N or issue:owner/repo#N）: {raw!r}"
        )
    kind, owner, repo, number = m.groups()
    return Target(kind=kind, owner=owner, repo=repo, number=int(number))


def is_none_target(raw: str) -> str | None:
    """`none:<理由>` なら理由を返す。理由が空なら Indeterminate。"""
    if raw is None:
        return None
    m = RE_NONE_TARGET.match(raw)
    if not m:
        return None
    reason = m.group(1).strip()
    if not reason:
        raise Indeterminate("none: の理由が空です")
    if "\n" in raw:
        raise Indeterminate("REVIEW_TARGET に改行を含められません")
    return reason


# ---------------------------------------------------------------------------
# 本文パース（純粋関数。gh を呼ばない）
# ---------------------------------------------------------------------------


def parse_inherited_pr_numbers(body: str) -> list[int]:
    """継承行から前身 PR 番号を抽出する（順序保持・重複除去）。"""
    seen: list[int] = []
    for m in RE_INHERIT.finditer(body or ""):
        n = int(m.group(1))
        if n not in seen:
            seen.append(n)
    return seen


def parse_approval_rounds(body: str) -> list[int]:
    """承認行が宣言する巡番号の一覧（例: 「巡3の人間承認」→ [3]）。"""
    return [int(m.group(1)) for m in RE_APPROVAL.finditer(body or "")]


def parse_total_cap(body: str) -> int | None:
    """承認行が宣言する総上限。複数あれば最大値（最新の承認が上限を引き上げた場合を許容）。"""
    caps = [int(m.group(1)) for m in RE_TOTAL_CAP.finditer(body or "")]
    return max(caps) if caps else None


def has_verdict(body: str) -> bool:
    return RE_VERDICT.search(body or "") is not None


def body_own_round(body: str) -> int:
    """本文が示す「own target の巡数」= 承認行が宣言する巡番号の最大値。無ければ0。"""
    rounds = parse_approval_rounds(body)
    return max(rounds) if rounds else 0


# ---------------------------------------------------------------------------
# 台帳（state dir）
# ---------------------------------------------------------------------------


def read_state_file(path: Path) -> dict[str, str]:
    """1行1キー形式の state ファイルを dict にする。壊れた行は無視する。"""
    out: dict[str, str] = {}
    try:
        text = path.read_text()
    except OSError:
        return out
    for line in text.splitlines():
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k] = v
    return out


def ledger_head_shas_for_target(state_dir: Path, target_key: str) -> list[tuple[float, str]]:
    """state dir を走査し、target に一致する state ファイルの (started_at, head_sha) を
    started_at 昇順で返す（head_sha 未記録のエントリは除外＝v2 以前の state）。
    """
    entries: list[tuple[float, str]] = []
    if not state_dir.is_dir():
        return entries
    for p in sorted(state_dir.glob("*.state")):
        d = read_state_file(p)
        if d.get("review_target") != target_key:
            continue
        head = d.get("head_sha")
        if not head:
            continue
        try:
            started = float(d.get("started_at", "0"))
        except ValueError:
            started = 0.0
        entries.append((started, head))
    entries.sort(key=lambda t: t[0])
    return entries


def ledger_own_round(state_dir: Path, target_key: str, head_sha: str) -> int:
    """この HEAD で発注したら何巡目になるか（同一 HEAD の既存発注があればその巡、無ければ新規=len+1）。"""
    distinct: list[str] = []
    for _started, head in ledger_head_shas_for_target(state_dir, target_key):
        if head not in distinct:
            distinct.append(head)
    if head_sha in distinct:
        return distinct.index(head_sha) + 1
    return len(distinct) + 1


def same_head_dispatch_count(state_dir: Path, target_key: str, head_sha: str) -> int:
    """同一 target × 同一 HEAD（＝同一巡）に対する既存の発注本数（state ファイル数）。

    「同一 target × 同一 HEAD は同一巡に束ねる」（design §1）こと自体は変えない。ここは
    その**同一巡の中で何本まで発注してよいか**という別の不変条件（review-round-cap.md
    「確定した集合へ出すぶんは1巡」＝通常はレビュアー集合2本程度）を守るための独立カウント。
    束ね判定を変えると total_round の計算まで壊れるため、意図的に別関数にしてある。
    """
    count = 0
    if not state_dir.is_dir() or not head_sha:
        return count
    for p in state_dir.glob("*.state"):
        d = read_state_file(p)
        if d.get("review_target") == target_key and d.get("head_sha") == head_sha:
            count += 1
    return count


def normalize_workdir(workdir: str) -> str:
    """末尾スラッシュ・`.`/`..`・symlink 経由の差で同一 workdir が別物に見えるのを防ぐ
    （none: 上限の回避経路）。`os.path.realpath` で symlink・相対要素を解決してから
    正規化する（`normpath` だけでは symlink 先が実体と同一でも別パス扱いになる）。
    実在しないパス（テストの仮想 workdir 等）は realpath がそのまま返すため normpath へフォールバックする。
    """
    if not workdir:
        return workdir
    return os.path.realpath(workdir)


def none_dispatch_count(state_dir: Path, workdir: str) -> int:
    """同一 workdir の none: 発注の累計件数（workdir は正規化して比較する）。"""
    count = 0
    if not state_dir.is_dir():
        return count
    target_workdir = normalize_workdir(workdir)
    for p in state_dir.glob("*.state"):
        d = read_state_file(p)
        if normalize_workdir(d.get("workdir", "")) != target_workdir:
            continue
        rt = d.get("review_target", "")
        if rt.startswith("none:"):
            count += 1
    return count


# ---------------------------------------------------------------------------
# 前身チェーンの合算 / 総巡数
# ---------------------------------------------------------------------------
#
# 「本文の巡数」は本文の表やコードブロックを数えるのではなく、承認行が宣言する巡番号
# （RE_APPROVAL）を読む。実データで確認したとおり（design-gate-v3.md §3・#563）、承認行の
# 「巡N」は target 自身のローカル巡数ではなく、前身からの継承分を含む**総巡数**である
# （#563: 前身 #559 の2巡 + #563 ローカル1巡目 = 「巡3の人間承認」）。ゆえに
# `target_total_rounds()` は「台帳（ledger）由来の総巡数」と「本文の承認行が示す総巡数」の
# 大きい方を返す（§2 ★「本文の巡数と台帳の巡数、大きい方を採る」の実装）。


def ledger_own_round_for_predecessor(state_dir: Path, target_key: str) -> int:
    """target が過去に消化した巡数（台帳のみ。distinct HEAD 数。新規 HEAD の加算はしない）。"""
    distinct: list[str] = []
    for _started, head in ledger_head_shas_for_target(state_dir, target_key):
        if head not in distinct:
            distinct.append(head)
    return len(distinct)


def target_total_rounds(
    target: Target,
    state_dir: Path,
    fetch_body,
    env_predecessors: list[Target] | None = None,
    pending_new_head: str | None = None,
    *,
    _visited: set[str] | None = None,
    _depth: int = 0,
) -> int:
    """target が消化した（または、これから消化しようとしている）総巡数を返す。

    - `pending_new_head` は depth 0（今まさにゲート判定している target 自身）にのみ渡す。
      その HEAD が台帳に無ければ「これから発注される1巡」として +1 する。同一 HEAD が既に
      台帳にあれば束ねて加算しない（同一 target × 同一 HEAD は同一巡）。
    - 前身は ①env_predecessors（depth 0 の target にのみ適用） ②本文の継承行（PR番号のみ）の
      和集合を辿る。孫以降は本文の継承行のみで辿る。循環・深さ5超は Indeterminate。
    """
    visited = _visited if _visited is not None else set()
    key = target.key()
    if key in visited:
        raise Indeterminate(f"判定不能: 継承チェーンが循環しています（{key}）")
    if _depth > MAX_CHAIN_DEPTH:
        raise Indeterminate("判定不能: 継承チェーンが深すぎます（5超）")
    visited.add(key)

    body = fetch_body(target)

    own_count = ledger_own_round_for_predecessor(state_dir, key)
    if pending_new_head is not None:
        heads = [h for _s, h in ledger_head_shas_for_target(state_dir, key)]
        distinct: list[str] = []
        for h in heads:
            if h not in distinct:
                distinct.append(h)
        own_count = len(distinct) if pending_new_head in distinct else len(distinct) + 1

    predecessors: list[Target] = list(env_predecessors or []) if _depth == 0 else []
    for n in parse_inherited_pr_numbers(body):
        predecessors.append(Target(kind="pr", owner=target.owner, repo=target.repo, number=n))

    pred_total = 0
    for pred in predecessors:
        pred_total += target_total_rounds(
            pred, state_dir, fetch_body, None, None, _visited=visited, _depth=_depth + 1
        )

    ledger_total = own_count + pred_total
    body_total = body_own_round(body)
    return max(ledger_total, body_total)


# ---------------------------------------------------------------------------
# 判定
# ---------------------------------------------------------------------------


@dataclass
class Decision:
    status: str  # "pass" | "blocked" | "indeterminate"
    exit_code: int
    total_round: int
    message: str


def decide(total_for_decision: int, body: str) -> Decision:
    if total_for_decision <= 2:
        return Decision("pass", EXIT_PASS, total_for_decision, f"巡{total_for_decision}: 通過")

    if total_for_decision <= 5:
        approvals = parse_approval_rounds(body)
        cap = parse_total_cap(body)
        if not approvals:
            return Decision(
                "blocked",
                EXIT_BLOCKED,
                total_for_decision,
                f"巡{total_for_decision}: 承認行（巡Nの人間承認）が本文に必要です",
            )
        if cap is None or total_for_decision > cap:
            return Decision(
                "blocked",
                EXIT_BLOCKED,
                total_for_decision,
                f"巡{total_for_decision}: 承認済み総上限（{cap}）を超えています",
            )
        return Decision(
            "pass", EXIT_PASS, total_for_decision, f"巡{total_for_decision}: 承認済み（総上限{cap}）で通過"
        )

    # 6以上
    if has_verdict(body):
        return Decision(
            "pass", EXIT_PASS, total_for_decision, f"巡{total_for_decision}: 裁定行ありで通過"
        )
    return Decision(
        "blocked",
        EXIT_BLOCKED,
        total_for_decision,
        f"巡{total_for_decision}: 6巡以上は裁定行（縮小／切り出し／撤回のいずれか）が必要です",
    )


# ---------------------------------------------------------------------------
# 巡行の書式（design §3・§4。純粋関数）
# ---------------------------------------------------------------------------

ROUND_ROW_HEADER = "| 巡 | 種別 | 発注日時 | 対象 SHA | レビュアー | 実測入力トークン | 族タグ |"
ROUND_ROW_SEP = "|---|---|---|---|---|---|---|"
ROUND_SECTION_TITLE = "## 巡の履歴"
MEASURING_PLACEHOLDER = "計測中"


def render_round_row(
    round_no: int,
    kind: str,
    dt_iso: str,
    sha7: str,
    reviewer: str,
    tokens: str = MEASURING_PLACEHOLDER,
    family_tag: str = "-",
) -> str:
    return f"| {round_no} | {kind} | {dt_iso} | {sha7} | {reviewer} | {tokens} | {family_tag} |"


def render_inherit_line(pred_pr: int, design_k: int, code_m: int) -> str:
    return f"前身 PR #{pred_pr} で 設計{design_k}巡・コード{code_m}巡 消化済み（継承）。"


def append_round_row(body: str, row: str) -> str:
    """本文の「## 巡の履歴」セクション末尾に巡行を差し込む。セクションが無ければ末尾に新設する。

    差し込みは「セクション末尾」＝次の `## ` 見出し（または本文末尾）の直前。既存の表があれば
    そのすぐ下に追記し、無ければヘッダ+セパレータごと新設する。
    """
    lines = body.splitlines()
    title_idx = None
    for i, line in enumerate(lines):
        if line.strip() == ROUND_SECTION_TITLE:
            title_idx = i
            break

    if title_idx is None:
        # セクションが無い: 末尾に新設する
        new_section = [
            "",
            ROUND_SECTION_TITLE,
            "",
            ROUND_ROW_HEADER,
            ROUND_ROW_SEP,
            row,
        ]
        return body.rstrip("\n") + "\n" + "\n".join(new_section) + "\n"

    # セクション末尾（次の "## " 見出しの直前 or 本文末尾）を探す
    end_idx = len(lines)
    for i in range(title_idx + 1, len(lines)):
        if lines[i].startswith("## "):
            end_idx = i
            break

    # そのセクション内に表があるかを確認する
    has_table = any(
        lines[i].strip() == ROUND_ROW_HEADER for i in range(title_idx, end_idx)
    )

    insert_at = end_idx
    # 末尾の空行の直前に差し込む（見出し直前の空行を保つ）
    while insert_at > title_idx + 1 and lines[insert_at - 1].strip() == "":
        insert_at -= 1

    new_lines = list(lines)
    if has_table:
        new_lines[insert_at:insert_at] = [row]
    else:
        new_lines[insert_at:insert_at] = ["", ROUND_ROW_HEADER, ROUND_ROW_SEP, row]
    return "\n".join(new_lines) + ("\n" if body.endswith("\n") else "")


def row_present(body: str, row: str) -> bool:
    """PATCH 前後で自分の追記行が本文に実在するかを確認する（同時編集の上書き消失対策）。"""
    return row in body


def backfill_measuring_row(body: str, round_no: int, tokens_value: str) -> tuple[str, bool]:
    """「計測中」のままの巡行を実測値へ置換する。対象行が見つかれば (新本文, True)、
    見つからなければ (元本文, False)。
    """
    pattern = re.compile(
        rf"^\|\s*{re.escape(str(round_no))}\s*\|(.*)\|\s*{re.escape(MEASURING_PLACEHOLDER)}\s*\|(.*)\|$",
        re.MULTILINE,
    )
    m = pattern.search(body)
    if not m:
        return body, False
    old_row = m.group(0)
    new_row = old_row.replace(MEASURING_PLACEHOLDER, tokens_value, 1)
    return body[: m.start()] + new_row + body[m.end() :], True


# ---------------------------------------------------------------------------
# トークン backfill 突合（design §5。純粋関数 + 薄い I/O ラッパー）
# ---------------------------------------------------------------------------

RE_SESSION_ID = re.compile(r"^session id: ([0-9a-zA-Z-]+)\s*$", re.MULTILINE)
RE_TOTAL_TOKEN_USAGE = re.compile(r'"total_token_usage":\s*(\{[^}]*\})')


def extract_session_id(log_text: str) -> str | None:
    m = RE_SESSION_ID.search(log_text or "")
    return m.group(1) if m else None


def find_rollout_jsonl(sessions_dir: Path, session_id: str) -> Path | None:
    if not session_id or not sessions_dir.is_dir():
        return None
    matches = sorted(sessions_dir.glob(f"**/rollout-*{session_id}*.jsonl"))
    return matches[0] if matches else None


def extract_total_tokens_from_jsonl(text: str) -> int | None:
    """jsonl 本文中の最後の total_token_usage.total_tokens を返す（そのセッションの最終累計）。"""
    last = None
    for m in RE_TOTAL_TOKEN_USAGE.finditer(text or ""):
        try:
            obj = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if "total_tokens" in obj:
            last = obj["total_tokens"]
    return last


def compute_backfill_value(log_text: str, sessions_dir: Path) -> tuple[str, str]:
    """(tokens_value_str, note) を返す。取得できなければ `計測不能: <理由>` を tokens_value に入れる。"""
    session_id = extract_session_id(log_text)
    if not session_id:
        return "計測不能: session id を log から取得できません", "no_session_id"
    jsonl_path = find_rollout_jsonl(sessions_dir, session_id)
    if jsonl_path is None:
        return f"計測不能: rollout jsonl が見つかりません（session {session_id}）", "no_jsonl"
    try:
        text = jsonl_path.read_text()
    except OSError as e:
        return f"計測不能: rollout jsonl を読めません（{e}）", "read_error"
    tokens = extract_total_tokens_from_jsonl(text)
    if tokens is None:
        return f"計測不能: rollout jsonl にトークン数がありません（session {session_id}）", "no_token_field"
    return str(tokens), "ok"


# ---------------------------------------------------------------------------
# I/O（gh / git）— テスト対象外。main() からのみ使う
# ---------------------------------------------------------------------------


def git_head_sha(workdir: str) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", workdir, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Indeterminate(f"判定不能: git rev-parse に失敗しました（{e}）") from e
    if out.returncode != 0:
        raise Indeterminate(f"判定不能: git rev-parse HEAD が失敗しました: {out.stderr.strip()}")
    return out.stdout.strip()


def git_remote_repo(workdir: str) -> tuple[str, str] | None:
    """workdir の origin から owner/repo を返す。git 管理外・remote 無しは None。"""
    try:
        out = subprocess.run(
            ["git", "-C", workdir, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    url = out.stdout.strip()
    # git@github.com:owner/repo.git / https://github.com/owner/repo.git / https://github.com/owner/repo
    m = re.search(r"github\.com[:/]([^/]+)/([^/.]+?)(?:\.git)?$", url)
    if not m:
        return None
    return m.group(1), m.group(2)


def gh_fetch_body(target: Target) -> str:
    cmd = [
        "gh",
        target.kind,
        "view",
        str(target.number),
        "-R",
        target.repo_slug(),
        "--json",
        "body",
        "-q",
        ".body",
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Indeterminate(f"判定不能: gh {target.kind} view に失敗しました（{e}）") from e
    if out.returncode != 0:
        raise Indeterminate(
            f"判定不能: gh {target.kind} view #{target.number} が失敗しました: {out.stderr.strip()}"
        )
    return out.stdout


def gh_patch_body(target: Target, new_body: str) -> None:
    """PR/issue の本文を丸ごと置換する（gh api PATCH）。呼び出し側が read-modify-write する。"""
    resource = "pulls" if target.kind == "pr" else "issues"
    cmd = [
        "gh",
        "api",
        f"repos/{target.repo_slug()}/{resource}/{target.number}",
        "-X",
        "PATCH",
        "--input",
        "-",
    ]
    payload = json.dumps({"body": new_body})
    try:
        out = subprocess.run(cmd, input=payload, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"gh api PATCH に失敗しました（{e}）") from e
    if out.returncode != 0:
        raise RuntimeError(f"gh api PATCH #{target.number} が失敗しました: {out.stderr.strip()}")


def gh_edit_body_with_row(target: Target, row: str, fetch_body=gh_fetch_body, patch_body=gh_patch_body) -> bool:
    """read-modify-write で巡行を1本追記する。PATCH 後に自分の行が実在するか確認する。"""
    body = fetch_body(target)
    new_body = append_round_row(body, row)
    patch_body(target, new_body)
    confirm = fetch_body(target)
    return row_present(confirm, row)


def retry_pending_backfills(
    state_dir: Path,
    target: Target,
    sessions_dir: Path,
    fetch_body=gh_fetch_body,
    patch_body=gh_patch_body,
) -> list[dict]:
    """target 向けの state のうち、round 記録済みで未 backfill のものを探し、ログから
    トークン数が取得できればいま本文へ反映する（design §4「前行が計測中なら retry」）。
    """
    results: list[dict] = []
    if not state_dir.is_dir():
        return results
    for p in sorted(state_dir.glob("*.state")):
        d = read_state_file(p)
        if d.get("review_target") != target.key():
            continue
        if d.get("backfilled") == "1":
            continue
        round_no = d.get("round")
        log_path = d.get("log")
        if not round_no or not log_path:
            continue
        try:
            log_text = Path(log_path).read_text()
        except OSError:
            continue
        tokens_value, note = compute_backfill_value(log_text, sessions_dir)
        if note != "ok":
            continue  # まだ計測不能。次回に持ち越す
        body = fetch_body(target)
        new_body, found = backfill_measuring_row(body, int(round_no), tokens_value)
        if found:
            patch_body(target, new_body)
            with p.open("a") as fh:
                fh.write("backfilled=1\n")
        results.append({"run_id": p.stem, "round": round_no, "found": found, "tokens": tokens_value})
    return results


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


DEFAULT_STATE_DIR = os.environ.get("CODEX_WATCH_DIR", str(Path.home() / ".codex-watch"))
DEFAULT_SESSIONS_DIR = str(Path.home() / ".codex" / "sessions")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="codex-review 巡数ゲート")
    sub = p.add_subparsers(dest="cmd", required=True)

    gate = sub.add_parser("gate", help="判定のみ行う（副作用なし）")
    gate.add_argument("--target", default=os.environ.get("REVIEW_TARGET", ""))
    gate.add_argument("--workdir", required=True)
    gate.add_argument("--state-dir", default=DEFAULT_STATE_DIR)
    gate.add_argument("--predecessor", default=os.environ.get("REVIEW_PREDECESSOR", ""))
    gate.add_argument("--no-gate-reason", default=os.environ.get("CODEX_REVIEW_NO_GATE", ""))
    gate.add_argument("--json", action="store_true")

    record = sub.add_parser("record", help="gate 通過後、巡行を本文へ追記する")
    record.add_argument("--state-file", required=True)
    record.add_argument("--sessions-dir", default=DEFAULT_SESSIONS_DIR)
    record.add_argument("--json", action="store_true")

    backfill = sub.add_parser("backfill", help="単一 run のトークン実測値を backfill する")
    backfill.add_argument("--state-file", required=True)
    backfill.add_argument("--sessions-dir", default=DEFAULT_SESSIONS_DIR)
    backfill.add_argument("--json", action="store_true")

    return p


def parse_predecessor_env(raw: str) -> list[Target]:
    out: list[Target] = []
    for chunk in (raw or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        out.append(parse_target(chunk))
    return out


def run_gate(
    target_raw: str,
    workdir: str,
    state_dir: Path,
    predecessor_env_raw: str,
    no_gate_reason: str,
    fetch_body=gh_fetch_body,
) -> dict:
    """判定のみを行い、副作用（body 追記・state 書込）は行わない。呼び出し側（bash）が
    exit code を見て dispatch の可否を決め、通過時に record を別途呼ぶ。
    """
    # 空白のみの理由（例: `CODEX_REVIEW_NO_GATE=" "`）は「理由必須」の実質的な迂回になるため、
    # strip 後に空なら bypass を成立させない（理由なしと同じ扱いで通常ゲートへ進む）。
    if no_gate_reason and no_gate_reason.strip():
        return {
            "status": "bypass",
            "exit_code": EXIT_PASS,
            "message": f"CODEX_REVIEW_NO_GATE により巡数ゲートを迂回します: {no_gate_reason}",
            "reason": no_gate_reason,
            "record_target": "bypass",
        }

    if not target_raw:
        return {
            "status": "usage_error",
            "exit_code": EXIT_USAGE,
            "message": "REVIEW_TARGET が指定されていません（pr:owner/repo#N / issue:owner/repo#N / none:<理由>）",
            "record_target": "",
        }

    none_reason = is_none_target(target_raw)
    if none_reason is not None:
        n = none_dispatch_count(state_dir, workdir)
        if n >= MAX_NONE_DISPATCHES:
            return {
                "status": "blocked",
                "exit_code": EXIT_BLOCKED,
                "message": f"none: 発注は同一 workdir で累計{MAX_NONE_DISPATCHES}件までです（現在{n}件）",
                "record_target": "",
            }
        return {
            "status": "pass",
            "exit_code": EXIT_PASS,
            "message": f"none: 発注（{n + 1}件目）: {none_reason}",
            "none_reason": none_reason,
            "record_target": f"none:{none_reason}",
        }

    target = parse_target(target_raw)

    remote = git_remote_repo(workdir)
    if remote is None:
        # git 管理外の対象は「台帳のみ・本文追記なし」モード。巡数ゲート自体は動かす
        # （リポジトリ照合はスキップ）。
        head_sha = None
    else:
        if remote != (target.owner, target.repo):
            return {
                "status": "blocked",
                "exit_code": EXIT_BLOCKED,
                "message": (
                    f"REVIEW_TARGET の repo（{target.repo_slug()}）と workdir の origin"
                    f"（{remote[0]}/{remote[1]}）が一致しません"
                ),
                "record_target": "",
            }
        head_sha = git_head_sha(workdir)

    env_predecessors = parse_predecessor_env(predecessor_env_raw)
    # 束ね判定用の HEAD（git 管理外は head_sha=None のため束ねができない＝台帳のみモードで
    # 毎回新規1巡として扱う。target_total_rounds に None を渡すと own_count に加算されないため、
    # ここではダミーの一意な擬似 HEAD を都度生成しない代わりに "unmanaged" 固定値を使い、
    # 同一セッション内の複数発注は束ねない（git 管理外は既知の限界として許容する）。
    pending_head = head_sha if head_sha is not None else "unmanaged"

    # 同一巡（同一 target × 同一 HEAD）の中での発注本数の上限（review-round-cap.md
    # 「確定した集合へ出すぶんは1巡」）。束ね判定（total_round の計算）自体は変えず、
    # 束ねられた同一巡の中で無制限に発注できてしまう抜け道だけを別途塞ぐ。
    existing_same_head = same_head_dispatch_count(state_dir, target.key(), pending_head)
    if existing_same_head >= MAX_SAME_HEAD_DISPATCHES:
        return {
            "status": "blocked",
            "exit_code": EXIT_BLOCKED,
            "message": (
                f"同一巡での発注上限（{MAX_SAME_HEAD_DISPATCHES}本）に達しています。"
                "HEAD を進めるか、次巡として人間承認を取ること"
            ),
            "record_target": "",
        }

    total = target_total_rounds(target, state_dir, fetch_body, env_predecessors, pending_head)

    body = fetch_body(target)
    decision = decide(total, body)

    return {
        "status": decision.status,
        "exit_code": decision.exit_code,
        "message": decision.message,
        "total_round": total,
        "target": target.key(),
        "target_kind": target.kind,
        "head_sha": head_sha,
        # blocked でも record_target を出す: 万一 bash 側が exit code を無視しても
        # record が「巡数超過ブロック中の対象」に誤って書き込まないよう、blocked 時は空にする。
        "record_target": target.key() if decision.status == "pass" else "",
    }


def record_round(
    state_file: Path,
    sessions_dir: Path,
    fetch_body=gh_fetch_body,
    patch_body=gh_patch_body,
) -> dict:
    """gate 通過後、実際に発注した RUN_ID の state を見て巡行を本文へ追記する。

    state ファイルに `review_target=` / `round=` / `head_sha=` / `kind=` / `reviewer=` が
    書かれている前提（bash 側が gate の JSON 出力を使って書く）。git 管理外・none:・bypass は
    本文追記なし（台帳のみ）で正常終了扱いにする。
    """
    d = read_state_file(state_file)
    target_key = d.get("review_target", "")
    if not target_key or target_key.startswith("none:") or target_key == "bypass":
        return {"status": "skipped", "reason": "本文追記の対象外（none/bypass/未設定）"}

    m = RE_TARGET.match(target_key)
    if not m:
        return {"status": "skipped", "reason": f"review_target の形式が不正です: {target_key}"}
    kind, owner, repo, number = m.groups()
    target = Target(kind=kind, owner=owner, repo=repo, number=int(number))

    round_no = d.get("round")
    if not round_no:
        return {"status": "skipped", "reason": "round が state にありません"}

    row = render_round_row(
        int(round_no),
        d.get("kind_label", "コード"),
        d.get("started_at_human", ""),
        (d.get("head_sha") or "")[:7],
        d.get("reviewer", "codex"),
    )

    ok = False
    err = None
    for attempt in range(2):
        try:
            ok = gh_edit_body_with_row(target, row, fetch_body, patch_body)
        except RuntimeError as e:
            err = str(e)
            ok = False
        if ok:
            break
    if not ok:
        return {"status": "failed", "reason": err or "PATCH 後に追記行が確認できませんでした", "row": row}

    with state_file.open("a") as fh:
        fh.write(f"round_row_written=1\n")

    retry_results = retry_pending_backfills(state_file.parent, target, sessions_dir, fetch_body, patch_body)
    return {"status": "ok", "row": row, "retried_backfills": retry_results}


def backfill_one(state_file: Path, sessions_dir: Path, fetch_body=gh_fetch_body, patch_body=gh_patch_body) -> dict:
    """単一 run の巡行をトークン実測値で backfill する。"""
    d = read_state_file(state_file)
    target_key = d.get("review_target", "")
    if not target_key or target_key.startswith("none:") or target_key == "bypass":
        return {"status": "skipped", "reason": "本文追記の対象外（none/bypass/未設定）"}
    m = RE_TARGET.match(target_key)
    if not m:
        return {"status": "skipped", "reason": f"review_target の形式が不正です: {target_key}"}
    kind, owner, repo, number = m.groups()
    target = Target(kind=kind, owner=owner, repo=repo, number=int(number))

    round_no = d.get("round")
    log_path = d.get("log")
    if not round_no or not log_path:
        return {"status": "skipped", "reason": "round または log が state にありません"}
    try:
        log_text = Path(log_path).read_text()
    except OSError as e:
        return {"status": "skipped", "reason": f"log を読めません（{e}）"}

    tokens_value, note = compute_backfill_value(log_text, sessions_dir)
    if note != "ok":
        return {"status": "not_yet", "reason": tokens_value}

    body = fetch_body(target)
    new_body, found = backfill_measuring_row(body, int(round_no), tokens_value)
    if not found:
        return {"status": "row_not_found", "tokens": tokens_value}
    patch_body(target, new_body)
    with state_file.open("a") as fh:
        fh.write("backfilled=1\n")
    return {"status": "ok", "tokens": tokens_value}


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    if args.cmd == "gate":
        state_dir = Path(args.state_dir)
        try:
            result = run_gate(
                args.target,
                args.workdir,
                state_dir,
                args.predecessor,
                args.no_gate_reason,
            )
        except Indeterminate as e:
            result = {"status": "indeterminate", "exit_code": EXIT_INDETERMINATE, "message": e.reason}
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(result["message"])
        return result["exit_code"]

    if args.cmd == "record":
        try:
            result = record_round(Path(args.state_file), Path(args.sessions_dir))
        except Indeterminate as e:
            result = {"status": "indeterminate", "message": e.reason}
        exit_code = EXIT_PASS if result.get("status") in ("ok", "skipped") else EXIT_BLOCKED
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(result.get("message") or result.get("status"))
        return exit_code

    if args.cmd == "backfill":
        try:
            result = backfill_one(Path(args.state_file), Path(args.sessions_dir))
        except Indeterminate as e:
            result = {"status": "indeterminate", "message": e.reason}
        exit_code = EXIT_PASS if result.get("status") in ("ok", "skipped", "not_yet") else EXIT_BLOCKED
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(result.get("message") or result.get("status"))
        return exit_code

    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
