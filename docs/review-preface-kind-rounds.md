# レビュー前置きの巡数（2026-11-10）

前置きだけは既存台帳の同じ review_target・kind_label の distinct HEAD を巡として数え、今回の HEAD が未登録なら1巡足す（同じ HEAD への再発注は同じ巡）。kind_label がない旧 state は「コード」、head_sha がない旧 state は既存の台帳の読み方に合わせて除外する。git 管理外では既存ゲートと同じ unmanaged を今回の HEAD として扱う。総上限・前身の継承・本文承認による総巡数の判定は変更しない。

台帳を読めない・種別が不正などで数えられないときは exit 2 で止める。初巡を解消確認だけに狭める誤りも、後続巡を無制限に広げる誤りも避けるため。

## 検証と CC への引き継ぎ

起点: `9f756803a7fb0cff7d17d06b900786212d21a0e5`。変更はステージまでとし、commit / push はしない。

全試験: `GIT_CEILING_DIRECTORIES="$PWD" TMPDIR="$PWD/.tmp/fx" python3 -m pytest -q -p no:cacheprovider --basetemp="$PWD/.tmp/fx/base"` → **419 passed, 5 skipped**（214.47秒）。初回の対象試験は一時ディレクトリの親がなく実行前に停止したため、`.tmp/fx` を作成して再実行した。

探索した入力クラス:
- 履歴なし、設計→コード、コード→コード、設計→設計、コード→設計。
- kind_label のない旧 state（コード／設計へ発注）、不正な種別、読めない state（ディレクトリで OSError を再現）。
- 同じ HEAD への再発注、同じ HEAD の複数発注、別課題の state。
- 正本の欠落、ディレクトリ、0バイト、更新された正本（空白・日本語・絵文字を含む）。

変換は指定の4種（total_round への巻き戻し／種別比較除去／空正本の停止除去／初巡への前置き）に加え、旧形式の既定種別を反転・HEAD の重複排除を除去・対象課題の照合を除去する3種を当てる。追加の3種はそれぞれスキーマ互換・巡の同一性・対象の分離を壊す変換。陽性対照は整数の `>= 2` を `> 1` に書き換える。

再現: `python3 evidence/check_review_preface_mutations.py`。すべて `.tmp/fx/review-preface-mutations/` 内の隔離コピーに当て、正本の実装を壊す変更はしない。CLI は既存の fake codex / fake gh だけを使う。`evidence/review-preface-mutations.json` に各変異の差分・変更前後の SHA256・pytest 結果・実際に実行した行を残す。生ログと隔離コピーは `.tmp/fx/review-preface-mutations/` に残す。

Python は標準ライブラリの行トレース、bash は `set -x` で実行行を確認する。macOS bash 3.2 は BASH_XTRACEFD に対応しないため、bash のトレースは判定用の試験とは別実行で stderr を保存する（判定用の stderr は変更しない）。初回の計測器の失敗は変異の検出件数へ含めない。

結果: 陰性7種はすべて exit 1（pytest の assertion failure）で、生き残り0。陽性対照は **32 passed**。各変異の変更前後の差分と実行行の証跡は上記 JSON に保存した。正本の実装は全試験を通した状態のまま、変異は隔離コピーにだけ適用した。
