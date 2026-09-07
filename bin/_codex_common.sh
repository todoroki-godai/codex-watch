#!/usr/bin/env bash
# codex-review / codex-impl 共有ロジック（単一ソース）。
#
# 経緯（2026-09-08 codex レビュー [Must]1+2）: 当初 ~/.codex/config.toml を自前 awk で
# パースして実効値を推定していたが、TOML の字句規則（シングルクォート・`#` を含む値・
# CRLF 等）を実装しておらず、レビュー側で実際に食い違う入力が構成された。TOML パーサを
# 自作するのは blocking な検査にできない（~/.claude/rules/no-denylist-checks.md 系の
# 「名前・文字列・構文形で同一性を判定する検査は閉じない」と同型の問題）。
#
# そのため config.toml の解析はやめ、次の2本立てにする:
#   - requested_model / requested_effort: 呼び出し側が env で明示した「要求値」のみを
#     state に書く（未指定なら空文字）。config.toml の既定値を推測しない。
#   - model / effort (source=cli_log): codex exec が実際に起動した後、ログの起動ヘッダー
#     （`model: ...` / `reasoning effort: ...` の行、`--------` 区切り）を読んで
#     「実際に起動された値」を記録する。ヘッダーが一定時間内に出ない・書式が合わない
#     ときは model_source=unresolved / effort_source=unresolved を記録し、起動は妨げない
#     （fail-open）。

# 改行・タブ相当の文字を空白へ潰す（state はタブ区切りの行を使う箇所があるため、
# 値にタブ・改行が混じると行が壊れる）。
sanitize_single_line() {
  local v="$1"
  v="${v//$'\n'/ }"
  v="${v//$'\r'/ }"
  v="${v//$'\t'/ }"
  printf '%s' "$v"
}

# codex exec の起動ログ（stdout をそのままリダイレクトしたファイル）から起動ヘッダーを読み、
# 実際に起動された model / reasoning effort を取り出す。
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
# $1 = ログファイルパス  $2 = 待機上限秒（既定 5・小数不可・整数秒）
# stdout: "<model>\t<model_source>\t<effort>\t<effort_source>"
#   source は cli_log|unresolved。unresolved のとき値は "unresolved" を返す。
extract_codex_log_header() {
  local log_file="$1" timeout_s="${2:-5}"
  local interval="0.2"
  local max_iters=$(( timeout_s * 5 ))
  local i=0 model="" effort="" dash_count line

  while (( i < max_iters )); do
    if [[ -f "$log_file" ]]; then
      dash_count=0
      model=""
      effort=""
      while IFS= read -r line; do
        if [[ "$line" == "--------" ]]; then
          dash_count=$((dash_count + 1))
          if (( dash_count >= 2 )); then
            break
          fi
          continue
        fi
        if [[ "$line" =~ ^model:\ (.+)$ ]]; then
          model="${BASH_REMATCH[1]}"
        elif [[ "$line" =~ ^"reasoning effort: "(.+)$ ]]; then
          effort="${BASH_REMATCH[1]}"
        fi
      done < "$log_file"
      if (( dash_count >= 2 )); then
        break
      fi
    fi
    sleep "$interval"
    i=$((i + 1))
  done

  local model_source effort_source
  if [[ -n "$model" ]]; then
    model_source="cli_log"
  else
    model="unresolved"
    model_source="unresolved"
  fi
  if [[ -n "$effort" ]]; then
    effort_source="cli_log"
  else
    effort="unresolved"
    effort_source="unresolved"
  fi
  printf '%s\t%s\t%s\t%s\n' "$model" "$model_source" "$effort" "$effort_source"
}
