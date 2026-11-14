C の実装: 試験 754件成功／変異 陰性0件赤・陽性0件緑・生存未測定（commit拒否により未実行）／影響 止まるようになる6件・通るようになる3件

## 入力の区分表（試験追加前）
期待の出所は `docs/design/round-count-c.md` §2〜5、課題 #37、今回の明示依頼。
|入力|区分・境目・値|期待|試験の大きさ・名前|
|---|---|---|---|
|正常通し|設計3・N3/cap3→コード新HEAD|gate/前置き/state/本文が1|fake CLI design3_code1|
|巡境界|コード2/3承認なし、設計4 cap3|2可・3/4停止|関数 boundary|
|承認帰属|N5、コード2+設計3|全候補で停止|関数 attribution|
|承認候補|無し/両種/不正round/HEAD欠落/別target|判定不能|関数 invalid|
|同種実績|前身2+今回1、別種混在、過去HEAD|同種のみ・前置きも3|関数/CLI predecessor|
|文字|round 0/全角/空/負/ASCII正整数|不正は停止|関数 invalid|
|履歴|説明文/空行/ヘッダ/区切り|読み飛ばす|特例 history|
|ID|偽区切り/壊れた表/同ID矛盾（他種含む）|停止|特例 history_invalid|
|HEAD|同HEAD複数run/別HEAD/短縮一意・曖昧/予約重複|distinct計数・曖昧停止|特例 history_heads|
|状態×操作|帰属不能＋特例指定|解除不可|gate invalid|
|時刻・合図|新しい待ち処理・時刻判断なし|既存特例の時刻/予約検査を維持|既存全体試験|

必須参照: 設計全文、lib/round_gate.py・prerelease.py・history_backfill.py、bin/codex-review、README、巡数関連tests、gh issue view 37。段取り表: 無し（#37/#38 C割当）。本人決定: 今回依頼・#37。見本HTML: 無し（画面変更なし）。前身・巡履歴: 設計§1・#37。設計書の未レビュー表記より今回の「実装着手可・指摘0」を優先。

## 実装・検証結果

製品差分は種別を計数・前身へ通し、承認の各Nを保存済みround/kind_labelへ一意に帰属させ、その種別の保存済み実績のみで検証する。前置き・点検・state・本文はgateのtotal_roundを使う。特例はID照合後の同種distinct HEADへpending HEADを集合追加する。IDなし説明文は飛ばし、ID付き偽区切り・壊れた表・重複ID・曖昧短縮HEADは拒否する。

特例の同時予約は既存ロック下で未完了予約を確認する。distinct HEADでは同HEADの別予約が巡を増やさなくなるため、既存の二重予約停止を維持するために必要。完了stateと対になる予約は履歴として照合する。新しい予約形式・台帳・依存・移行は追加していない。

commitは名義確認PreToolUse hookが実行前に拒否した。期待todoroki-godai、検出matsukaze-minden。認証切替・hook迂回は行っていない。新commit無し、基点 `61b8fde1eb649e1c6d478da759c77987c5577196`。今回の「拒否されたら変更を残し、頭がcommitする」に従い差分を残した。したがって完了条件未達。

試験追加前の正常通しを含む20件は旧版で20件赤（`.tmp/round-count-c-red.log`）、実装後20件緑。最終追加30件緑（`.tmp/round-count-c-extra3.log`）。既存試験は、承認だけで台帳消失を補う旧期待を停止へ変更し、正常承認の入力に同種の保存済み実績を与えた。特例・履歴のfixtureはIDごとに実際のHEADを記載するよう補正した。意味の違う期待は設計§2の変更に限る。

パッケージ全体: 754 passed, 5 skipped in 536.10s (0:08:56)。範囲 `python3 -m pytest tests -q`、全出力 `.tmp/round-count-c-final-suite2.log`。全759件（754成功・5skip）。skipは tests/test_codex_github_account.py の test_real_gh_from_child（2 account×2 entry、実鍵を使うopt-in未指定）4件と test_review_records_after_codex_exit（impl入口は対象外）1件。DB試験は対象外・接続なし。過去の赤かは本線で未測定のため未確認。`bash -n bin/codex-review` と `git diff --check` も実施。

### 変異（未実行）

`tests/check_round_count_c_mutations.py` はcommit済みHEADのarchiveへ変異を適用し、差分ログと実行行・ローカル値の証跡ログを別々に残す実行器として準備した（構文解析のみ済み）。未commit差分のoverlayでcommit要件を迂回していない。陰性①〜④、別種回避、陽性対照は実行0件で、生存0件を確認したとは言わない。変異後復旧・git status空の確認も未実施。現在は実装差分を保有しておりdirtyである。

予定12変換: ①種別filter除去・前身への種別欠落、②全種別で承認Nを裏付け、③帰属種別交換、④帰属不能の停止無効化・偽区切り無視・予約停止無効化、説明文skip除去。別種回避2件はdispatch件数への置換（集合の重複除去を破る）と承認を最大Nだけへ射影（複数承認の情報を落とす）。陽性2件は比較の向きの同値変換と集合add→update。探索入力クラスは上の区分表と追加試験（予約、同HEAD再発注、短縮SHAの一意性・競合、前身の不足を子孫で埋めない、各承認N）を参照。実際の探索結果は未取得。

再開時は依頼元がこの差分をcommitした後、そのSHAとcleanを確認し、以下を実行する（実行器は開始時と終了時にgit diff/status空を検査する）。
```
python3 tests/check_round_count_c_mutations.py > .tmp/round-count-c-mutations.log 2>&1
python3 -m pytest tests -q > .tmp/round-count-c-final-suite2.log 2>&1
git diff --check
git status --short
```
変異ログは `.tmp/round-count-c-mutations/<case>.diff.log` と `<case>.executed.log`、`<case>.pytest.log`、`results.log`（予定）。実行器は試験失敗・実行行の観測・非空差分・前後SHA256・baseline収集IDと実行結果IDの一致・skip無しを照合し、陽性を陰性件数に混ぜない。実行器自身の動作検証は未了なので、再開時にsetup/collection errorや読まれない変異を成功と数えないこと。

### 影響（実物のrun_gate・非送信）

設計§4と同じ `2026-11-14T22:40:52.360285+00:00` までの7日、期間内最新stateで対象を重複排除。実台帳は読取のみ。資格情報・本文全量・state全量は保存せず、必要な計数欄だけの隔離コピーを作り、計測後に削除した。旧版はgit show 61b8fde:lib/round_gate.py、実装版は作業差分。両方の実run_gateを呼び、Git repo/HEAD取得だけを各対象の観測値へ固定し、同じ本文fetch cache・隔離state・goal-cutで比較した。計数・承認・decide・同HEAD上限はmockしていない。通常経路・前身envなし・特例IDなし。

走査state 5177件、期間内890件、issue/pr発注84件、重複排除42対象。取得完了UTC 2026-11-14T23:36:58.399987+00:00。

|範囲|対象|新たに停止|新たに通過|巡増加|巡減少|同じ巡|巡不明|未取得|
|---|---:|---:|---:|---:|---:|---:|---:|---:|
|OPEN_current|33|6|3|0|4|23|6|0|
|OPEN_fresh|33|3|4|0|4|23|6|0|
|all_current|42|7|3|0|4|30|7|1|
|all_fresh|42|4|4|0|4|30|7|1|

巡不明は承認帰属/不足によるindeterminate（0巡・巡減少には算入しない）。閉鎖済み対象はallだけに含めた。設計時との新HEAD停止4→3の差は#880が今回旧版でも停止するため。未取得は `pr:min-sys/docs-platform#1057`。

新たに停止する各件（現HEAD・全対象、括弧内は状態）:

- `issue:min-sys/updater-index#1564` (OPEN): issue:min-sys/updater-index#1564: 承認N=3を一意に帰属できません（候補種別0）
- `issue:min-sys/updater-index#1596` (OPEN): issue:min-sys/updater-index#1596: 承認N=4の設計実績3が不足しています
- `issue:min-sys/updater-index#2015` (OPEN): issue:min-sys/updater-index#2015: 承認N=3のコード実績2が不足しています
- `issue:min-sys/updater-index#880` (OPEN): issue:min-sys/updater-index#880: 承認N=4の設計実績3が不足しています
- `issue:todoroki-godai/codex-watch#38` (OPEN): issue:todoroki-godai/codex-watch#38: 承認N=4のコード実績3が不足しています
- `pr:min-sys/updater-index#2007` (OPEN): pr:min-sys/updater-index#2007: 承認N=5のコード実績4が不足しています
- `pr:min-sys/updater-index#2043` (MERGED): pr:min-sys/updater-index#2043: 承認N=5のコード実績1が不足しています

OPEN各対象の現HEAD/新HEAD（旧巡・判定 → 実装巡・判定）:

|対象|現HEAD|新HEAD|
|---|---|---|
|issue:min-sys/updater-index#1564|5/pass → None/indeterminate|5/pass → None/indeterminate|
|issue:min-sys/updater-index#1596|4/pass → None/indeterminate|4/pass → None/indeterminate|
|issue:min-sys/updater-index#1677|1/pass → 1/pass|2/pass → 2/pass|
|issue:min-sys/updater-index#1708|3/blocked → 2/pass|3/blocked → 2/pass|
|issue:min-sys/updater-index#1737|2/pass → 1/pass|3/blocked → 2/pass|
|issue:min-sys/updater-index#1982|3/pass → 3/pass|4/blocked → 4/blocked|
|issue:min-sys/updater-index#1987|2/pass → 2/pass|3/blocked → 3/blocked|
|issue:min-sys/updater-index#1990|3/pass → 3/pass|4/blocked → 4/blocked|
|issue:min-sys/updater-index#2004|3/pass → 3/pass|4/blocked → 4/blocked|
|issue:min-sys/updater-index#2006|2/pass → 2/pass|2/pass → 2/pass|
|issue:min-sys/updater-index#2008|2/pass → 2/pass|2/pass → 2/pass|
|issue:min-sys/updater-index#2014|2/pass → 2/pass|3/blocked → 3/blocked|
|issue:min-sys/updater-index#2015|4/pass → None/indeterminate|5/blocked → None/indeterminate|
|issue:min-sys/updater-index#2016|2/pass → 2/pass|3/blocked → 3/blocked|
|issue:min-sys/updater-index#2018|3/blocked → 2/pass|3/blocked → 2/pass|
|issue:min-sys/updater-index#2021|1/pass → 1/pass|2/pass → 2/pass|
|issue:min-sys/updater-index#2022|1/pass → 1/pass|2/pass → 2/pass|
|issue:min-sys/updater-index#2023|3/blocked → 3/blocked|4/blocked → 4/blocked|
|issue:min-sys/updater-index#2028|1/pass → 1/pass|2/pass → 2/pass|
|issue:min-sys/updater-index#2029|1/pass → 1/pass|2/pass → 2/pass|
|issue:min-sys/updater-index#2031|3/blocked → 2/pass|3/blocked → 2/pass|
|issue:min-sys/updater-index#880|5/pass → None/indeterminate|6/blocked → None/indeterminate|
|issue:todoroki-godai/claude-config#140|2/pass → 2/pass|2/pass → 2/pass|
|issue:todoroki-godai/codex-watch#16|1/pass → 1/pass|2/pass → 2/pass|
|issue:todoroki-godai/codex-watch#26|2/pass → 2/pass|3/blocked → 3/blocked|
|issue:todoroki-godai/codex-watch#38|4/pass → None/indeterminate|5/blocked → None/indeterminate|
|issue:todoroki-godai/codex-watch#40|2/pass → 2/pass|3/blocked → 3/blocked|
|issue:todoroki-godai/harness-nudge#4|5/blocked → 5/blocked|5/blocked → 5/blocked|
|pr:min-sys/updater-index#1991|3/blocked → 3/blocked|3/blocked → 3/blocked|
|pr:min-sys/updater-index#2007|5/pass → None/indeterminate|5/pass → None/indeterminate|
|pr:min-sys/updater-index#2038|1/pass → 1/pass|2/pass → 2/pass|
|pr:min-sys/updater-index#2039|3/pass → 3/pass|4/blocked → 4/blocked|
|pr:min-sys/updater-index#2050|2/pass → 2/pass|3/blocked → 3/blocked|

公開前特例を指定した実対象の次発注判定は未測定（通常経路の結果を特例へ拡張しない）。特例の履歴説明文・同HEAD/予約・blob・固定上限・bypassは隔離fixture試験の範囲。実発注・本文追記・予約・実台帳書込・AWS/dev/stg/prod操作は行っていない。

再現（作業場所内の実行スクリプトを保存済み。本文/state/HEADを再取得するため再実行で数値は変わり得る）:
```
PYTHONDONTWRITEBYTECODE=1 python3 .tmp/impact_c.py > .tmp/round-count-c-impact.log 2>&1
```
詳細結果 `.tmp/round-count-c-impact/impact.json`、実装版の製品ファイルSHA256は同JSONのsummary.source_hashes。未commit版であることを明示し、旧版基点と取り違えない。

### 呼出し元・7段・環境

事前探索 `git grep -n -E 'target_total_rounds|ledger_own_round_for_predecessor|history\(' -- lib bin tests` は37行（`.tmp/round-count-c-callers.log`）。既存関数・filter・再帰・承認parser・ID照合・変異実行器を確認して再利用した。「無い」という判断で新設した道具はない。

変更関数の全呼出し元は `git grep -n -E 'target_total_rounds|ledger_own_round_for_predecessor|ledger_own_round\(|history\(' -- lib bin tests`（`.tmp/round-count-c-callers-final.log`）に列挙。製品は ledger_own_round_for_predecessor←target_total_rounds、target_total_rounds←自身の前身再帰/承認実績検証/run_gate、history←prerelease.evaluate。CLIは独立ledger_own_round呼出しを削除してgate JSONを読む。各経路は新規種別/前身/承認/履歴/CLI通し試験と全体試験で確認。ledger_own_round本体・history_backfill本体の変更無し。直接historyを呼ぶ既存試験はコード既定、設計の補完試験だけ明示種別。旧変異スクリプトにある呼出し文字列は実行口でなく過去版用変異で、今回は実行していない。その他の呼出し元（新試験）は未追跡なのでgit grepには出ず、tests/test_round_count_c.pyに記載。

|項目|7段の適用と止まった段|
|---|---|
|種別計数・前身・表示値統一|㋐明示依頼、㋑既存filter/再帰/gate JSONを利用。1行の受渡し・既存呼出し削除で足りる|
|承認の帰属と同種実績|㋐安全要件、㋑既存parser/state/再帰、㋒標準set/re、㋓新たな標準機能不要、㋔依存追加不要、㋕1行では複数N/エラーを扱えず、㋖最小の検証分岐|
|特例の照合とHEAD集合|㋑既存ID/state/予約の照合を改修、㋒標準dict/set/reで充足、依存追加無し|
|未完了予約の停止維持|㋐既存安全策の維持、㋑既存lock/予約を利用、㋒Pathと既存state reader、㋕対象/完了stateの確認は1行に縮めず㋖最小の分岐|
|試験・変異実行器・影響計測|㋐明示依頼、㋑既存fixture/pytest/実行器の型、㋒標準trace/tarfile/subprocess。新しい検査基盤は作らない|
|新台帳・移行・種別付き承認・D配線|㋐不要、作らない|

|環境|経路・設定・データの差/今回の扱い|
|---|---|
|ローカル|製品差分、隔離fake CLI/台帳、実台帳とGitHub本文の読取のみで影響比較|
|dev|巡数コードの環境別分岐は無し。接続/読取/書込なし|
|stg|同上。接続/書込なし|
|prod|同上。接続/操作なし|

指定外部結果2ファイルの親 `/Users/matsukaze-takashi/updater/updater-index/_work/notes/codex-queue/` はsandboxの書込許可外、approval policy=never。指定先に書けたとは扱わない。選択肢は依頼元による転記/作業場所内の転記用ファイル。既定案として `docs/design/refactor-result-round-count-c-impl.md` と `docs/design/refactor-next-round-count-c-impl.md` に作成した。

引渡し用の全差分は `.tmp/round-count-c-impl.patch.log`、ファイル別SHA256は `.tmp/round-count-c-manifest.log`。現在の差分を消さずに保持する。
