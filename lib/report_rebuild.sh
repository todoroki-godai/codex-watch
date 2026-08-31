#!/usr/bin/env bash
# codex exec の -o 出力（.report）を、逐次出力運用（codex-review が前置きで指示する
# 「セクションごとに出力せよ」）に合わせて組み立て直す共有ライブラリ。
#
# なぜ要るか（2026-08-26実測）: 対策1（逐次出力の指示）を入れた最初の実運用
# （rev435r2-20260826-130717-57786）で、codex は指示どおり8セクションに分けて出力した
# （判定行「修正要」も最初のメッセージに正しく出た）。しかし `-o` は「最終メッセージだけ」を
# 受け取る仕様のため、.report は最終セクション（見出し1つ・4065B）だけになり、判定行と
# 大半の [Must] が report から失われた（元の -o report は判定行を含まない）。
# 一方 log には 'codex' role マーカーで区切られた全セクションが残るため、それを結合して
# report を再構築する。
#
# 使い方（source して関数を呼ぶ）:
#   source .../lib/report_rebuild.sh
#   rebuild_report_if_needed "<log>" "<report>"
#   # 戻り値: 0=そのまま維持 or 再構築成功／1=再構築できなかった（log読込失敗・0セクション等）
#
# 判定行の正規パターン（codex-exec.md の1行目規約）。
REPORT_REBUILD_VERDICT_REGEX='^(マージ可|マージ不可|修正要|実装着手可|設計修正要)$'

# 'codex' role のメッセージ本文だけを結合して標準出力へ出す（セクション間は空行区切り。
# 判定行が確実に1行目に来るよう、区切りマーカー等の付加テキストは入れない）。
# log が読めない、または 'codex' セクションが1件も無ければ何も出力しない（呼び出し側は
# 出力が空なら「取れなかった」と判定する＝失敗を成功扱いにしない）。
_report_rebuild_extract_sections() {
  local log="$1"
  [[ -r "$log" ]] || return 1
  awk '
    /^codex$/ { f=1; seen=1; next }
    /^(user|hook: )/ { if (f) { print "" }; f=0; next }
    f { print }
    END { if (!seen) exit 1 }
  ' "$log"
}

# report の1行目が判定行として妥当かを判定する。
_report_rebuild_has_valid_verdict() {
  local report="$1"
  [[ -s "$report" ]] || return 1
  local first_line
  first_line="$(head -1 "$report")"
  [[ "$first_line" =~ $REPORT_REBUILD_VERDICT_REGEX ]]
}

# 本体: log から再構築した内容で report を上書きするかどうかを決め、必要なら実行する。
# - -o の出力（report）が非空かつ1行目が判定行として妥当 → 何もしない（従来どおり優先。
#   逐次出力に従わなかった回や、たまたま1セクションで完結した回を壊さないため）
# - それ以外（report が空、または1行目が判定行でない） → log から結合を試みる
#   - 結合結果が得られ、かつ元の report に内容があった場合は "<report>.raw" として温存する
#     （結合結果と -o の出力が食い違っても、どちらも捨てない）
#   - 結合結果が得られなければ、report には一切手を触れない（空のまま＝失敗を隠さない）
rebuild_report_if_needed() {
  local log="$1"
  local report="$2"

  if _report_rebuild_has_valid_verdict "$report"; then
    return 0
  fi

  local combined
  combined="$(_report_rebuild_extract_sections "$log")" || return 1
  [[ -n "$combined" ]] || return 1

  if [[ -s "$report" ]]; then
    # 既存の (壊れた/部分的な) report を捨てずに退避する。上書きループでも直前の raw を
    # 消さないよう、raw が無いときだけ作る（rebuild を複数回呼んでも直近の rebuild 前の
    # -o 出力を保持し続ける）。
    [[ -e "${report}.raw" ]] || cp "$report" "${report}.raw"
  fi

  local tmp
  tmp="$(mktemp "${report}.rebuild.XXXXXX")"
  printf '%s' "$combined" > "$tmp"
  mv "$tmp" "$report"
  return 0
}

# report から判定行を取り出す。妥当な判定行でなければ「特定できず」を返す（見出し行等を
# 判定行として誤表示しない）。
extract_verdict_line() {
  local report="$1"
  if [[ ! -s "$report" ]]; then
    echo "（report空）"
    return
  fi
  local first_line
  first_line="$(head -1 "$report")"
  if [[ "$first_line" =~ $REPORT_REBUILD_VERDICT_REGEX ]]; then
    echo "$first_line"
  else
    echo "判定行を特定できず（先頭行: ${first_line}）"
  fi
}
