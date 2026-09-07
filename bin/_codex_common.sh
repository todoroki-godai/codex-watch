#!/usr/bin/env bash
# codex-review / codex-impl 共有の実効値解決ロジック（単一ソース）。
#
# なぜ要るか: state の model= / effort= 行は未指定時「既定」という文字列しか残らず、
# 後からどのモデルで走ったか検証できなかった（#pipeline-routing 系の運用要求）。
# ここで実際に効くモデル/effortを解決し、両スクリプトから同じロジックで state に書く。
#
# 解決順（model / model_reasoning_effort で共通）:
#   1. 環境変数（呼び出し側が渡す CODEX_REVIEW_MODEL 等）
#   2. ~/.codex/config.toml（CODEX_HOME があればそちら）のトップレベル `key = "..."` 行
#      - `[section]` 以降（トップレベルを外れた行）は対象にしない
#      - コメント（`#`）を含む行はコメント部分を落としてから判定する
#   3. どちらも取れなければ unresolved
#
# 使い方:
#   resolve_codex_setting "$ENV_VALUE" "model"          # -> "gpt-5.6-sol<TAB>env" 等
#   出力は "<値><TAB><source>"（source は env|config|unresolved）。unresolved のとき値も
#   "unresolved" を返す。

_codex_common_toml_path() {
  local home="${CODEX_HOME:-$HOME/.codex}"
  printf '%s\n' "$home/config.toml"
}

# $1 = 環境変数の値（未設定なら空文字を渡す） $2 = toml のトップレベルキー名
resolve_codex_setting() {
  local env_val="$1" key="$2"
  if [[ -n "$env_val" ]]; then
    printf '%s\t%s\n' "$env_val" "env"
    return 0
  fi

  local toml
  toml="$(_codex_common_toml_path)"
  if [[ -f "$toml" ]]; then
    local val
    val="$(awk -v key="$key" '
      # 最初の [section] 行に到達したらそこで打ち切る（トップレベルのみを対象にする）。
      /^\[/ { exit }
      {
        line = $0
        sub(/#.*/, "", line)          # コメント部分を落とす
        if (line ~ ("^[ \t]*" key "[ \t]*=")) {
          sub(("^[ \t]*" key "[ \t]*=[ \t]*"), "", line)
          gsub(/[ \t]+$/, "", line)
          gsub(/^"/, "", line)
          gsub(/"$/, "", line)
          print line
          exit
        }
      }
    ' "$toml")"
    if [[ -n "$val" ]]; then
      printf '%s\t%s\n' "$val" "config"
      return 0
    fi
  fi

  printf '%s\t%s\n' "unresolved" "unresolved"
}
