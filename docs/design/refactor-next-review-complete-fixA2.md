## 今回の作業（run名: review-complete-fixA2-validate）
作業場所: /Users/matsukaze-takashi/matsukaze-utils/codex-watch/_wt.noindex/review-complete（枝feat/review-gate-prerelease）。次の名: review-complete-fixA2-validate。
前提: review-complete-fixA2のcommitは名義hookに拒否され、HEAD 8e400b5からの修正を未commitで残した。頭が同じ変更をcommitしてから本作業を起動する。名義不整合が続くなら切替・迂回せず停止する。
読むもの: docs/design/review-complete-fixA2-REPORT.md、docs/design/review-complete.md、.tmp/impact/REPORT2.md、tests/check_prerelease_fixA2_mutations.py、.tmp/fixA2/full.log。
やること: 現在のHEAD・dirty状態・今回の変更を確認し、commit済みの修正と試験ログの対象ソースが一致することを確かめる。他LLM・本物のstate/本文への書込み・push/PR/枝操作・gh auth switch・dev/stg/prod操作はしない。
1. 修正commitでgit diff HEADが空になっていることを確認し、python3 tests/check_prerelease_fixA2_mutations.pyを実行。陰性①〜④、異種回避2件、陽性対照について非空差分と独立実行trace、赤/緑を確認する。未着弾・生存があれば完了にしない。
2. python3 .tmp/impact/compare2.pyを実行（--working-treeを使わない）。旧bdb4d62・新修正HEADで同じ31件/124判定を比較し、REPORT2の新規停止0件を確定する。
3. 全体ログとソースを照合し、ソースまたは試験が変わった場合はTMPDIRとGIT_CEILING_DIRECTORIESをこの作業場所の.tmp/fixA2へ設定してpython3 -m pytest tests -qを再実行する。試験の生成物は作業場所内に置く。
4. 変異の件数・差分・実行証跡と修正HEADでの影響を詳報に記録し、意味のある単位でcommitする。hookに拒否されたら未commitのまま停止・報告。
終わりの条件: 全体試験が緑、陰性の生存0・未着弾0、陽性が緑、31件比較の新規停止0、git diff空。指定共有先のrefactor-result-review-complete-fixA2-validate.md（10行以内）とrefactor-next-review-complete-fixA2-validate.mdへ結果と次回依頼を保存する。書込み不可なら詳報と転記用控えを残して未保存と明記する。別手番の巡4コードレビューは起動しない。
