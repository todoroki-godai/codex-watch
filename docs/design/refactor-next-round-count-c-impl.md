## 今回の作業
run名: round-count-c-impl-verify。
作業場所: /Users/matsukaze-takashi/matsukaze-utils/codex-watch/_wt.noindex/round-count-c（feat/round-count-c）。
前提: 頭がround-count-c-implの全差分を名義ルールに従いcommitしたこと。HEAD SHAを固定しgit statusが空であることを確認する。未commitなら変異を当てず止める。checkout・枝操作・push・認証切替・他LLM呼出し・実台帳書込は禁止。
読むもの: docs/design/round-count-c.md 全体、round-count-c-REPORT.md、tests/check_round_count_c_mutations.py、tests/test_round_count_c.py。
やること: tests/check_round_count_c_mutations.pyを実行し、陰性①〜④と別種回避2件以上・陽性対照について、差分と実行行証跡を個別に検証する。実行器は未動作検証なので、setup/collection errorや証跡無しを赤成功として数えない。生存変異があれば対象Cだけ修正して意味のある単位でcommitし、固定SHAから再実行する。全出力を.logへ残してcommitしない。python3 -m pytest tests -qを全体で実行し、報告先頭の件数と変異集計を更新する。変更があれば実run_gate比較も再測定する（.tmp/impact_c.py、実台帳は読取のみ）。
終わりの条件: 全tests緑、陰性変異が全件赤・陽性全件緑・生存0、各差分と分岐実行証跡あり、変異後git diff/status空。REPORTと結果/次回ファイルを更新してcommitし、最終status空を確認する。指定外部パスが書込不可なら作業場所内の転記用を使い未転記と明記する。
次のrun名: round-count-c-impl-review（実装の別系統レビューは依頼元が手配。この窓では他LLMを呼ばない）。
