#!/usr/bin/env bash
# codex-review / codex-impl / codex-status / codex-watch 共有ロジック（単一ソース）。
#
# 経緯:
# - 2026-09-08 codex レビュー巡1 [Must]1+2: 当初 ~/.codex/config.toml を自前 awk で
#   パースして実効値を推定していたが、TOML の字句規則（シングルクォート・`#` を含む値・
#   CRLF 等）を実装しておらず食い違いが構成された。config.toml 解析はやめ、codex 起動
#   ログのヘッダーから読む方式へ変更した。
# - 2026-09-08 codex レビュー巡2 [Must]1: 起動スクリプト側でヘッダー出力を待ってから
#   run id を返す設計は、待機中に中断すると codex プロセスだけが state 無しで残る。
#   起動時は待たず requested_* のみを即時に書き、以降は「読み手側」（codex-status /
#   codex-watch）が毎回ログから read 時に導出する方式へ変更した。
# - 2026-09-08 codex レビュー巡2 [Must]2: ヘッダー区間の特定が「任意の2本目の
#   `--------`」で打ち切っていたため、プロンプト本文中の偽ヘッダー風テキストを
#   誤検出することが構成された。`^OpenAI Codex v` 行の直後が `--------` である
#   場合に限りヘッダー区間へ入る方式へ厳密化した。
# - 2026-09-08 codex レビュー巡3（族2巡で打ち切り・ユーザー裁定「縮小してマージ」）:
#   文字列の形で「これは実ヘッダーだ」と同定する方式は、レビュー側で
#   `extract_codex_log_header tests/test_codex_model_effort.py`（ログでも codex の
#   出力でもない任意のテキストファイル）に値を返させることが実際に構成された
#   （＝文字列の形による同定は実効値の保証にならない。~/.claude/rules/
#   verify-checks-by-breaking.md・PJ no-denylist-checks.md と同型の限界）。
#   これ以上「もう一段厳密にする」パッチを重ねず、次の3点で機構を増やさずに縮小した:
#     ① **呼び出し側の表示から「実効値」という言い切りを外す**（codex-status /
#        codex-watch。「ログ先頭のヘッダー（参考・run 同一性は未検証）」と名乗る）
#     ② **先頭200行しか読まない**（巨大ログでの走査コストを打ち切る。1行目が
#        一致しなければ1行読んだだけで即 unresolved に抜ける）
#     ③ **1行目が `^OpenAI Codex v` で始まらないファイルは即 unresolved**
#        （state の `log=` が指すファイル以外を渡された場合の素通りを塞ぐ最小限の対策。
#        「run/session の同一性を証明する」までは踏み込まない＝別 issue 候補）

# 改行相当の文字を空白へ潰す（state は1行1キー形式のため、値に改行が混じると
# 偽の行を注入できる）。「\n\r\t の3文字だけを列挙する」実装は、Python の
# str.splitlines() が行境界とみなす別の文字（\v \f \x1c-\x1e \x85     等）を
# 見逃す（round_gate.py の is_single_line() が既に踏んだ問題と同型）。ロジックを
# 二重管理せず、同じ判定源（round_gate.is_single_line）を呼ぶ。
_codex_common_round_gate_py() {
  local here
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  printf '%s\n' "$here/lib/round_gate.py"
}

sanitize_single_line() {
  local v="$1"
  local gate_py gate_dir
  gate_py="$(_codex_common_round_gate_py)"
  gate_dir="$(dirname "$gate_py")"
  python3 -c "
import sys
sys.path.insert(0, sys.argv[1])
from round_gate import is_single_line
v = sys.argv[2]
print(v if is_single_line(v) else ' '.join(v.splitlines()))
" "$gate_dir" "$v"
}

# codex exec の起動ログ（stdout をそのままリダイレクトしたファイル）の**先頭200行だけ**を
# 1回読み、起動ヘッダーらしき行から model / reasoning effort を取り出す。
#
# 重要な限界（2026-09-08 レビュー巡3の裁定）: これは「文字列の形」による抽出であって
# 「実際にこの run で使われた値である」ことの証明ではない。呼び出し側は結果を
# 「実効値」と言い切って表示してはならない（「ログ先頭のヘッダー（参考・run 同一性は
# 未検証）」等、参考情報であることが分かる文言にする）。
#
# ヘッダー例（`~/.codex-watch/*.log` の実ログで確認済み。2026-09-08）:
#   OpenAI Codex v0.153.4
#   --------
#   workdir: /path/to/workdir
#   model: gpt-5.6-sol
#   provider: openai
#   approval: never
#   sandbox: read-only
#   reasoning effort: medium
#   reasoning summaries: none
#   session id: 01a0....
#   --------
#
# 判定手順（fail-closed。1つでも条件を満たさなければ unresolved に倒す）:
#   1. **1行目**が `^OpenAI Codex v` に一致すること（1行目固定。一致しなければ
#      1行読んだだけで即座に unresolved を返す＝ codex のログでも state の `log=` が
#      指すファイルでもない任意のテキストファイルを渡されても、ほぼ何も読まずに弾く）
#   2. その**直後（2行目）**が `--------` であること
#   3. 3行目以降、`^model: ` / `^reasoning effort: ` の行頭一致だけを採用する
#   4. 200行以内に次の `--------` で区間が閉じること（閉じなければ unresolved）
#
# $1 = ログファイルパス
# stdout: "<model>\t<model_source>\t<effort>\t<effort_source>"
#   source は cli_log|unresolved。unresolved のとき値は "unresolved" を返す。
extract_codex_log_header() {
  local log_file="$1"
  local model="" effort="" line state=0
  local line_no=0
  local max_lines=200

  if [[ -f "$log_file" ]]; then
    while (( line_no < max_lines )) && IFS= read -r line; do
      line_no=$((line_no + 1))

      if (( line_no == 1 )); then
        if [[ "$line" =~ ^"OpenAI Codex v" ]]; then
          state=1
          continue
        fi
        # 1行目固定: 一致しなければここで即座に読むのをやめる（fail-closed）。
        break
      fi

      case "$state" in
        1)
          if [[ "$line" == "--------" ]]; then
            state=2
          else
            # ヘッダー行の直後が区切りでない＝実ヘッダーではない候補として棄却する
            # （fail-closed。unresolved のまま終える）。
            break
          fi
          ;;
        2)
          if [[ "$line" == "--------" ]]; then
            state=3
            break
          fi
          if [[ "$line" =~ ^"model: "(.+)$ ]]; then
            model="${BASH_REMATCH[1]}"
          elif [[ "$line" =~ ^"reasoning effort: "(.+)$ ]]; then
            effort="${BASH_REMATCH[1]}"
          fi
          ;;
      esac
    done < "$log_file"
  fi

  local model_source effort_source
  if [[ "$state" == "3" && -n "$model" ]]; then
    model_source="cli_log"
  else
    model="unresolved"
    model_source="unresolved"
  fi
  if [[ "$state" == "3" && -n "$effort" ]]; then
    effort_source="cli_log"
  else
    effort="unresolved"
    effort_source="unresolved"
  fi
  printf '%s\t%s\t%s\t%s\n' "$model" "$model_source" "$effort" "$effort_source"
}

# PJ が宣言した場合だけ gh の設定を名義ごとに隔離する。共有設定・保管庫は変更しない。
# 呼び出し元は STATE_DIR 作成直後に呼ぶ（review の gate/record にも同じ名義を使う）。
prepare_codex_github_account() {
  CODEX_GITHUB_ACCOUNT=""
  CODEX_GITHUB_CONFIG_DIR=""
  CODEX_GITHUB_ARGS=()
  local root declaration actual
  root="$(git -C "$WORKDIR" rev-parse --show-toplevel 2>/dev/null || true)"
  [[ -n "$root" ]] || return 0
  declaration="$root/.claude/codex-github-account"
  [[ -e "$declaration" || -L "$declaration" ]] || return 0
  if ! CODEX_GITHUB_ACCOUNT="$(python3 - "$declaration" <<'PYACCOUNT'
import pathlib, re, sys
try:
    account = pathlib.Path(sys.argv[1]).read_text().strip()
except (OSError, UnicodeError):
    sys.exit(1)
# GitHub login は最大39文字。空値・内部空白・複数行・資格情報らしき値を拒否。
if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", account):
    sys.exit(1)
print(account)
PYACCOUNT
)"; then
    echo 'GitHub 名義の宣言が不正です（読取可能な英数字・ハイフンの1行、1〜39文字が必要）' >&2
    return 5
  fi
  CODEX_GITHUB_CONFIG_DIR="$STATE_DIR/gh-account/$CODEX_GITHUB_ACCOUNT"
  (umask 077; mkdir -p "$CODEX_GITHUB_CONFIG_DIR")
  chmod 700 "$CODEX_GITHUB_CONFIG_DIR"
  # STATE_DIR が相対パスでも、子シェルの cwd に依存しない絶対パスを渡す。
  CODEX_GITHUB_CONFIG_DIR="$(cd "$CODEX_GITHUB_CONFIG_DIR" && pwd)"
  # 同じ名義の同時起動でも、読取側に途中のファイルを見せない。
  python3 - "$CODEX_GITHUB_CONFIG_DIR" "$CODEX_GITHUB_ACCOUNT" <<'PYCONFIG'
import os, pathlib, sys, tempfile
folder, account = sys.argv[1:]
files = {
    "hosts.yml": f"github.com:\n    users:\n        {account}:\n    user: {account}\n".encode(),
    "config.yml": b'version: "1"\n',
}
for name, data in files.items():
    fd, temporary = tempfile.mkstemp(dir=folder, prefix="." + name + ".")
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
        os.replace(temporary, pathlib.Path(folder) / name)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
PYCONFIG
  export GH_CONFIG_DIR="$CODEX_GITHUB_CONFIG_DIR"
  # gh は環境の token を保管庫より優先する。値を読まず除去し、HTTP debug も抑止する。
  unset GH_TOKEN GITHUB_TOKEN GH_ENTERPRISE_TOKEN GITHUB_ENTERPRISE_TOKEN GH_DEBUG GH_HOST
  if ! actual="$(gh api --hostname github.com user --jq .login 2>/dev/null | python3 -c '
import re, sys
value = sys.stdin.read().strip()
print(value if re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", value) else "(invalid-or-empty)")
')"; then
    printf 'GitHub 名義の検証失敗: requested=%s returned=%s (gh failed)\n' "$CODEX_GITHUB_ACCOUNT" "${actual:-(none)}" >&2
    return 5
  fi
  if [[ "$actual" != "$CODEX_GITHUB_ACCOUNT" ]]; then
    printf 'GitHub 名義の不一致: requested=%s returned=%s\n' "$CODEX_GITHUB_ACCOUNT" "$actual" >&2
    return 5
  fi
  # inherit=core/none や include_only に左右されず、子のシェルにも固定値を渡す。
  CODEX_GITHUB_ARGS=(-c "$(python3 -c 'import json,sys; print("shell_environment_policy.set.GH_CONFIG_DIR=" + json.dumps(sys.argv[1]))' "$GH_CONFIG_DIR")")
  # config.toml の set 経由で資格情報が再注入されることも防ぐ（空文字は gh が無視する）。
  local name
  for name in GH_TOKEN GITHUB_TOKEN GH_ENTERPRISE_TOKEN GITHUB_ENTERPRISE_TOKEN GH_DEBUG GH_HOST; do
    CODEX_GITHUB_ARGS+=(-c "shell_environment_policy.set.$name=\"\"")
  done
}

# 宣言ありの場合だけ、検証済み login を記録する。
codex_github_account_state() {
  [[ -n "$CODEX_GITHUB_ACCOUNT" ]] && printf 'github_account=%s\n' "$CODEX_GITHUB_ACCOUNT"
  return 0
}

# 末尾の CLI ERROR ブロックと容量の表現を組み合わせる（全文の単語検索ではない）。
# プロンプト・ツール出力・途中で回復したエラーは、後続の本文で候補を解除する。
# tokens used と数値は失敗時にも出るため、直前のエラー候補を保持する。
# 文面変更には capacity / overloaded 等で対応するが、任意の将来文面や
# CLI と同じ末尾形を持つ引用の識別までは保証できない（ログ形式による推定）。
codex_log_has_capacity_error() {
  [[ -r "$1" ]] || return 1
  awk '
    function capacity(text) {
      # 否定された容量表現は、別原因のエラーを容量不足にしない。
      if (text ~ /(not|no[[:space:]]+longer)[[:space:]]+(at[[:space:]]+capacity|overloaded)/) return 0
      return (text ~ /at[[:space:]]+capacity/ ||
        (text ~ /model/ && text ~ /capacity|overload|no[[:space:]]+(free[[:space:]]+)?slots/))
    }
    {
      sub(/\r$/, "")
      gsub(sprintf("%c", 27) "\\[[0-9;]*[[:alpha:]]", "")
      if ($0 ~ /^[[:space:]]*$/) next
      if ($0 == "tokens used") { result=pending; pending=0; block=""; summary=1; next }
      if (summary && $0 ~ /^[0-9,]+$/) { summary=0; next }
      summary=0; result=0
      line=tolower($0)
      if (line ~ /^error:[[:space:]]*/) {
        block=line
        pending = pending || capacity(block)
      } else if (block != "" && line ~ /^[[:space:]]+/) {
        sub(/^[[:space:]]+/, "", line)
        block=block " " line
        pending = pending || capacity(block)
      } else { pending=0; block="" }
    }
    END { exit !(result || pending) }
  ' "$1"
}
