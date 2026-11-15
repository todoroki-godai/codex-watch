C の実装: 試験 766件成功／変異 陰性13件赤・陽性2件緑・生存0件／影響 止まるようになる0件・通るようになる3件

影響の1行目はOPEN33件・現HEAD。新HEADは停止0件・通過4件。run: round-count-c-impl2、2026-11-15 JST。

## impl2 入力の区分表（試験変更前）
正常系を先頭に置き、期待の出所は設計 §2.2/§3/§5 と今回の本人決定。
|入力|区分・境目・値|期待|大きさ・試験名|
|---|---|---|---|
|正常通し|設計3・N3/cap3・コード新HEAD|前置き/state/判定=1|CLI design3_code1（維持）|
|裏付け不足|前回6件形のN3/4/5・候補なし/同種不足|旧本体と同値|gate fallback_cases|
|混算境界|コード2・設計3・N5/cap5・新コードHEAD|巡6・停止|gate attribution_deficit|
|帰属不明・文字欠損|候補0/2・round空/0/全角/負・HEAD空・別target|旧計算へ戻す|gate invalid|
|信頼境界|不正kind・state読取失敗|停止|gate trust_boundary|
|各承認・前身|小さいNのみ不明・前身不足・子孫余剰|全体を旧計算、各ノード下限|関数 all_approvals/predecessor|
|継ぎ目|fallbackで巡4・CLI前置き/本文/state|全て4|CLI fallback_cli|
|特例|fallback時の説明文/同HEAD複数run|旧history/旧判定|gate legacy_prerelease|
|履歴/ID|裏付けあり、説明文・偽dispatch_id区切り|説明文skip・偽ID拒否|history既存維持|
|時刻・合図|新しい待ち/時刻分岐無し|既存予約/時刻試験維持|全体試験|

## 試験

範囲 `python3 -m pytest tests -q`、766 passed, 5 skipped in 406.41s (0:06:46)。全771件、赤0件。ログ `.tmp/round-count-c-impl2-final-suite.log`。skipは実鍵のopt-in未指定4件とimpl入口対象外1件（tests/test_codex_github_account.py）。`git diff --check` と `bash -n bin/codex-review` も成功。DB試験は対象外で未実行。

初回の関連試験は5件赤（期待値4件と特例fixture1件）。修正前fixtureを収集した初回全体は765成功・1赤・5skipで、修正後に全体を取り直した。前の赤との判定は本線で行っていないため未確認であり、「前からある赤」とは扱わない。

## 変異

陰性13件赤・陽性2件緑、実行ID一致、skip無し、setup/collection error無し、着弾証跡あり。各ケースの`.diff.log`と前後SHA256が(a)の差分、`.executed.log`が(b)の実行行・ローカル値、`.reports.log`が実際の試験ID/結果、`.restored.log`が復旧hash。`.tmp/round-count-c-impl2-mutations/results.log`にコマンド全文・基点SHA・各hashを記録。

|変換|区分|結果|実行行観測数|
|---|---|---|---:|
|N1-filter-removed|① remove kind propagation|赤|2|
|N2-all-kinds-support|② mixed support|赤|1|
|N3-attribution-swapped|③ swap kind|赤|1|
|N4-unattributed-allowed|④ disable attribution guard|赤|1|
|N5-forged-separator|④ ignore forged separator|赤|1|
|N6-prose-rejected|① remove prose skip|赤|1|
|N7-count-dispatches|extra1 replace set cardinality with dispatch count|赤|1|
|N8-max-approval-only|extra2 project multiple approvals onto maximum|赤|1|
|N9-pred-kind-lost|① recursive propagation removed|赤|1|
|N10-reservation-guard|④ disable outstanding reservation check|赤|2|
|N11-no-legacy-fallback|③ use kind count on fallback|赤|1|
|N12-pending-support|extra3 future work as completed evidence|赤|1|
|N13-unicode-round|extra4 normalize non-ASCII candidate number|赤|1|
|P1-equivalent-comparison|positive|緑|1|
|P2-equivalent-head-set|positive|緑|2|

①種別filter除去/前身伝播欠落、②全種別の件数で裏付け、③帰属種別交換/fallbackで種別値を使う、④帰属検査/偽区切り/予約検査の無効化を含む。説明文skip削除も赤。陽性は比較方向の同値変換・集合add→updateで、陰性へ合算していない。

依頼側のID衝突隠し・時差の再照合回避とは異なる、dispatch件数への置換・最大承認Nへの射影・未発注pendingを実績へ混入・非ASCII数字の受理も実際に適用した。探索した入力クラスは区分表の全て、および同HEAD複数run/複数承認/前身不足を子孫で埋める/予約済の組合せ。

初回にN1の選択試験だけでは緑が残ったため、既存design_predecessor_filterを選択へ追加し赤を確認した。最終に生存なし。pytest探索パスと実行ID照合の初期実行器エラーは最終件数に含めない。表示文字列に区切りを含むparamがあるため、実行IDはpytest既存hookでcall reportから機械的に照合する。

## 実対象の非送信比較

本線 `origin/main 0f630c5` と実装差分の実物run_gateを、前回と同じ固定期間（2026-11-14T22:40:52.360285+00:00までの7日）・対象選択・通常経路・同じ隔離state/本文fetch cache/HEAD/goal-cutで比較した。Git remote/HEAD境界だけを観測値へ固定し、計数・承認・decide・同HEAD上限は実物を使った。実台帳は読取のみ。今回state 5187、期間内890・issue/pr発注84・重複排除42対象。本文取得完了UTC 2026-11-15T00:05:39.965350+00:00。前回5177stateから増加したが対象42/OPEN33は同数。

|範囲|対象|未取得|新たに停止|新たに通過|同判定|巡減少|同じ巡|
|---|---:|---:|---:|---:|---:|---:|---:|
|OPEN_current|33|0|0|3|30|4|29|
|OPEN_fresh|33|0|0|4|29|4|29|
|all_current|42|1|0|3|38|4|37|
|all_fresh|42|1|0|4|37|4|37|

未取得はpr:min-sys/docs-platform#1057（OPENではない）。巡不明・巡増加は0。閉鎖済み8対象はallにのみ含めた。前回の6件は次のとおりで、全て旧本体と同じ巡・判定へ戻った。

|対象|現HEAD（旧→新）|新HEAD（旧→新）|
|---|---|---|
|issue:min-sys/updater-index#1564|5/pass → 5/pass|5/pass → 5/pass|
|issue:min-sys/updater-index#1596|4/pass → 4/pass|4/pass → 4/pass|
|issue:min-sys/updater-index#2015|4/pass → 4/pass|5/blocked → 5/blocked|
|issue:min-sys/updater-index#880|5/pass → 5/pass|6/blocked → 6/blocked|
|issue:todoroki-godai/codex-watch#38|4/pass → 4/pass|5/blocked → 5/blocked|
|pr:min-sys/updater-index#2007|5/pass → 5/pass|5/pass → 5/pass|

全42対象の個別判定は `.tmp/round-count-c-impl2-impact/impact.json` に保存。本文/全state/資格情報は保存せず、必要欄だけの隔離stateは計測後削除した。本文とHEADは再取得するため再実行で値は変わり得る。

## 読んだもの・判断

設計 `docs/design/round-count-c.md` §2.2・§3・§4・§5 と `git diff 61b8fde f5c9267 -- docs/design/round-count-c.md`、前実装 `d504d4a`、前回 REPORT（新規停止6件と理由）、`lib/round_gate.py`・`lib/prerelease.py`・`bin/codex-review`、`tests/test_round_count_c.py`・round_gate/prerelease関連試験・既存変異実行器を確認した。
段取り表: 無し（今回の割当ては #37/#38 C）。本人決定: 今回の明示依頼「裏付けなしは今の数え方で」、設計§1のmain-index受領記録。見本HTML: 無し（画面変更なし）。前身の設計と巡: 設計§1・前実装d504d4a・前回REPORT。設計中の未レビュー表記より今回の「実装着手可・指摘0件」を優先した。
指定 `.claude/skills/test-design/` は存在しない（`git grep -l '' -- .claude/skills/test-design/` 0件）。選択肢は補充待ち／設計と同じ既存skillを使用。今回の既定案として `/Users/matsukaze-takashi/updater/updater-index/_wt.noindex/rev9-audit/.claude/skills/test-design/SKILL.md` を読み、試験変更前に本書へ入力区分表を記録した。他LLMは呼んでいない。

## 実装

承認Nを一意に帰属でき、同種の保存済みdistinct HEAD実績が各Nを満たす場合だけ、種別別計数を採る。帰属不能・実績不足・round欠落/非ASCII/非正整数・候補HEAD欠落は専用の内部例外で区別し、発注全体を旧計算でやり直す。各ノードで全種別distinct HEADと前身を加算し、本文承認N最大値とのmaxを採る。独立した不正種別・読取不能・循環/深さ検査は停止を維持する。
run_gateが巡と選択した経路を受け取り、既存gate JSON経由で前置き・点検・state・本文へ同じ値を渡す。公開前特例もfallback時は旧historyと+1照合へ戻す。旧historyはorigin/main 0f630c5の関数をそのまま再利用した。裏付けあり経路の説明文skip・偽dispatch_id区切り拒否は維持する。新台帳・承認形式・依存・設定は追加していない。

## 版・再現

作業場所 `/Users/matsukaze-takashi/matsukaze-utils/codex-watch/_wt.noindex/round-count-c`、HEAD `f5c9267ee2965d23593f86c61079221acb0ab6b3`、本線 `origin/main=0f630c55c3e65defe52949a419462c018a83d866`。今回の指定に従いcommitしない。差分は依頼元がcommitするため残す。

```sh
python3 tests/check_round_count_c_mutations.py > .tmp/round-count-c-impl2-mutations.log 2>&1
PYTHONDONTWRITEBYTECODE=1 python3 .tmp/impact_c_impl2.py > .tmp/round-count-c-impl2-impact.log 2>&1
python3 -m pytest tests -q > .tmp/round-count-c-impl2-final-suite.log 2>&1
git diff --check
bash -n bin/codex-review
```

製品版のSHA256は影響結果JSONのsummary.source_hashesと変異snapshot.logに記録（未commit版）。再現には当該差分を適用する。変異実行器は区切り時点の全追跡ファイルを作業場所内 `.tmp/` の隔離コピーへ控えてから変更し、各ファイルを写しから復旧してSHA256一致を検査した後、隔離コピーを削除する。原本のgit diff/statusと全ファイルhashが変異前と同じことをrestoration.logで確認する。stash・checkout・resetは使わない。

## 呼出し元・7段

事前 `git grep -n -E 'target_total_rounds|ledger_own_round_for_predecessor|evaluate\(|history\(' -- lib bin tests` は68行（`.tmp/round-count-c-impl2-callers.log`）。既存filter・再帰・parser・旧本体関数・変異実行器を再利用。「道具が無い」ための新設はない。
最終の全呼出し元は `.tmp/round-count-c-impl2-callers-final.log`。製品は `run_gate→_selected_rounds→_target_total_rounds`、互換公開関数 `target_total_rounds→_selected_rounds`、`_target_total_rounds→自身（前身・同種実績）/ledger_own_round_for_predecessor`、`run_gate→prerelease.evaluate→historyまたは_legacy_history`。CLIはgate JSONを既存経路で読む。前身・同種実績・旧本文下限・fallback CLI・特例両経路・既存直接呼出しを試験で確認。全試験呼出し・過去用変異文字列もgrepログへ列挙した。

|項目|7段で止まった段|
|---|---|
|旧計算への切替|㋐本人の明示依頼、㋑既存再帰/filter/body_own_roundを再利用、㋒標準例外/tuple、㋓追加不要、㋔依存追加不要、㋕全系列の選択は1行では扱えず㋖最小の選択関数|
|旧特例履歴|㋑origin/mainの既存関数を再利用。新しい互換形式を作らない|
|入力検査維持|㋐削減不可、㋑既存strict reader/kind filterを利用|
|試験・変異証跡|㋐明示依頼、㋑既存fixture/pytest/実行器、㋒標準trace/hash/diff、pytest既存hookで実行IDを記録|
|影響比較|㋑前回の非送信実run_gate比較を再利用、㋒標準mock、㋓gh読み取り|
|新台帳/移行/承認形式/環境分岐|㋐不要、作らない|

|環境|経路・設定・データの差／今回の扱い|
|---|---|
|ローカル|隔離state/fixtureで試験、実stateとGitHub本文は読取のみで比較|
|dev|巡数処理の環境別分岐は無し。接続・読取・書込なし|
|stg|同上。接続・書込なし|
|prod|同上。接続・操作なし|

実発注・実本文追記・実台帳書込・予約・課題更新は行っていない。CLI通しは隔離fakeのみ。DB試験は対象外で未実行。公開前特例を指定した実対象の影響は未測定で、隔離fixtureの成功と区別する。承認説明文のパーサー・共有祖先visited・トークン補完等の範囲外課題には手を出していない。

指定の外部結果2ファイルはsandbox書込許可外、approval policy=never。指定先へ書けたとは扱わない。選択肢は依頼元による転記／作業場所内へ転記用ファイル。既定案として `docs/design/refactor-result-round-count-c-impl2.md` と `docs/design/refactor-next-round-count-c-impl2.md` を用意する。
