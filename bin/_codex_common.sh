#!/usr/bin/env bash
# codex-review / codex-impl / codex-status / codex-watch 共有ロジック（単一ソース）。
#
# 経緯:
# - 2026-09-08 codex レビュー巡1 [Must]1+2: 当初 ~/.codex/config.toml を自前 awk で
#   パースして実効値を推定していたが、TOML の字句規則（シングルクォート・`#` を含む値・
#   CRLF 等）を実装しておらず食い違いが構成された。config.toml 解析はやめ、実際に
#   起動された値は codex 起動ログのヘッダーから読む方式へ変更した。
# - 2026-09-08 codex レビュー巡2 [Must]1: 起動スクリプト側でヘッダー出力を待ってから
#   run id を返す設計は、待機中に中断すると codex プロセスだけが state 無しで残る
#   （state 書込みより前に run id が返らない＝観測手段が消える）。**起動時は待たず
#   requested_* のみを即時に書き、実効値は「読み手側」（codex-status / codex-watch）が
#   毎回ログから read 時に導出する**方式へ変更した。ここに待機ループ・timeout変数は
#   一切残さない。
# - 2026-09-08 codex レビュー巡2 [Must]2: ヘッダー区間の特定が「任意の2本目の
#   `--------`」で打ち切っていたため、プロンプト本文中に偽のヘッダー風テキストを
#   混入されると誤検出することが実際に構成された。**`^OpenAI Codex v` の行を見つけ、
#   その直後の行が `--------` である場合に限りヘッダー区間へ入る**方式へ厳密化した。
#   直後が `--------` でない・区間が閉じない・区間内にキーが無い、のいずれでも
#   unresolved に倒す（実ヘッダーだと証明できないものは unresolved）。

# 改行相当の文字を空白へ潰す（state は1行1キー形式のため、値に改行が混じると
# 偽の行を注入できる）。「\n\r\t の3文字だけを列挙する」実装は、Python の
# str.splitlines() が行境界とみなす別の文字（\v \f \x1c-\x1e \x85     等）を
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

# codex exec の起動ログ（stdout をそのままリダイレクトしたファイル）を**その時点まで**
# 1回だけ読み、起動ヘッダーから実際に起動された model / reasoning effort を取り出す。
# 待機・ポーリングは行わない（呼び出し側が好きなタイミングで何度でも呼べる read-only
# な導出関数）。
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
# 判定手順（実ヘッダーだと証明できないものは unresolved に倒す）:
#   1. `^OpenAI Codex v` に一致する行を探す（見つかるまでの行は無視する。プロンプト
#      本文に紛れた偽のヘッダー風テキストが先に出ても、その前では拾わない）
#   2. その**直後の行**が `--------` である場合のみ、そこをヘッダー区間の開始とする
#      （直後でなければそのヘッダー候補は棄却し unresolved のまま終える。既存仕様上
#      2個目の "OpenAI Codex v" 行が後続ログに再度現れる余地は残すが、その探索も
#      同じ厳密な規則を要求するため誤検出はしない）
#   3. 区間内の `^model: ` / `^reasoning effort: ` の行頭一致だけを採用する
#   4. 次の `--------` で区間を閉じる。区間が閉じる前にログが終わっていれば unresolved
#
# $1 = ログファイルパス
# stdout: "<model>\t<model_source>\t<effort>\t<effort_source>"
#   source は cli_log|unresolved。unresolved のとき値は "unresolved" を返す。
extract_codex_log_header() {
  local log_file="$1"
  local model="" effort="" line state=0

  if [[ -f "$log_file" ]]; then
    # state: 0=`OpenAI Codex v` 行待ち 1=直後の `--------` 待ち 2=ヘッダー区間内 3=区間を正常に閉じた
    while IFS= read -r line; do
      case "$state" in
        0)
          if [[ "$line" =~ ^"OpenAI Codex v" ]]; then
            state=1
          fi
          ;;
        1)
          if [[ "$line" == "--------" ]]; then
            state=2
          else
            # ヘッダー行の直後が区切りでない＝実ヘッダーではない候補として棄却する。
            # 以降ログ末尾までこの候補では拾わない（unresolved のまま終える）。
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
