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
