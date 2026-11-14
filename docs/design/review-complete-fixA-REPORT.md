codex-watch#38 A コード巡1の直し: Must 2・Should 1 対応／全試験 675件成功／陰性 16件赤

## 試験前の入力区分表
|入力|区分・境目|置く値|期待|期待の出所|大きさ|試験名|
|---|---|---|---|---|---|---|
|通常state→特例|正常通し・継ぎ目|authority=ordinary, evidence={}|巡3特例が通る|今回Should3|実evaluate|ordinary_empty_evidence|
|同IDの本文|同じ内容の重複|巡1の同一行2本|1件|今回Must1|run_gate|identical_duplicate|
|同IDの本文|矛盾・承認済み操作|巡/SHA/日時/種別の各1欄を変更、承認有無|常に停止|今回Must1|run_gate|conflicting_id|
|本文だけ2発注|文字と欠け|2行目の巡をunreadableへ置換、参照IDなし|停止|今回Must2|run_gate|malformed_history|
|壊れた本文|通常承認の境目|承認のみ/capのみ/両方|両方だけ通過|今回Must2|run_gate|malformed_history|
|承認の通常経路|正常|正常履歴、巡3、承認・cap3|humanで通過|今回Must2|run_gate|normal_human|
|特例証跡|合図・権限の継ぎ目|project_prereleaseのcap変更|停止|既存設計2.3|evaluate|saved_exception_cap|
|時刻|同日/境界|履歴日時の同一/不一致|同一のみ統合|今回Must1|run_gate|conflicting_id|
数字の巡2/3・cap境界は既存試験も再実行。非ASCII等は新しい正規化要件がないため追加せず、既存の構文を維持。

## 修正と出所
同一IDの本文行は、巡・種別・日時・短SHA・レビュアーの固定欄を比較し、矛盾を専用のValueError派生例外にする。実測トークンなど後で補完する欄は同一性に含めない。run_gateではこの矛盾を通常承認より先に停止する。書式不明は別扱いとし、既存decideの通常承認・総上限がともに成立する場合だけ通す。正常な通常発注の空証跡はauthorityで除外する。予約もauthorityを保存し、既存cap試験のfixtureには実際の特例stateと同じauthorityを補った。新規fixtureでもcap変更拒否を独立に確認する。

7段: ㋐レビューの再現3件を止める明示依頼。㋑既存history/run_gate/evaluate、既存fixture、既存CASESと独立line traceを再利用。㋒標準dict・例外・jsonで足りる。㋓プラットフォーム機能は追加不要。㋔依存追加無し。㋕権限による除外は既存条件の1行置換。㋖矛盾と書式不明では承認の扱いが違うため例外型の最小追加。
探索: `git grep -n -E 'authority|prerelease_evidence|history\(' -- lib/prerelease.py lib/round_gate.py bin/codex-review tests/test_prerelease.py` は27行（`.tmp/fixA/reuse.log`）。既存機能を再利用した。「無い」を根拠とした追加無し。

読んだもの:
- レビュー全文 `~/.codex-watch/review-complete-c1-20261113-171549-52271.report`（read_sha e6b0e42）。本文には実行スクリプト全文は無く、記述された2行・ID・SHA・破損置換・対象other/repoを試験に固定した。
- `lib/prerelease.py`、`lib/round_gate.py` の履歴・通常承認・特例・予約、`bin/codex-review` の呼出しと保存、`tests/test_prerelease.py`、`tests/test_prerelease_implA3.py`、変異runner2本、conftest。
- 前身設計 `docs/design/review-complete.md` A・入力区分と `docs/design/review-complete-implA3-REPORT.md`、`refactor-next-review-complete-implA3.md`（なし）。巡の出所は今回レビューと依頼原文。
- 段取り表: T番号は無し（今回指定なし）。割当てとして `/Users/matsukaze-takashi/updater/updater-index/_work/notes/rev9-review-history.md:275` を読んだ。
- 本人決定: 今回の依頼原文「Must 2件・Should 1件を採用」。前身A/C/Dの判断は設計書の出所欄を照合。
- 見本HTML: 無し（発注関門の変更で画面変更無し）。
- test-design: `/Users/matsukaze-takashi/updater/updater-index/_wt.noindex/rev9-audit/.claude/skills/test-design/SKILL.md`。この作業場所に当該skillが無いため前回REPORTに記載された所在を使用。

## 変異と対照
`.tmp/fixA/mutations/results.json` に全18写しのコマンド・commit基点・overlay SHA256・exit・実行行数を保存した。各写しの `mutation.diff` が不変条件を壊す差分、`executed.log` が独立line tracerによる実行証跡、`pytest.log` が試験出力。全16陰性はexit1でassertion失敗、未着弾0・生存0。陽性2組は各3試験成功（同じ試験を全試験の成功数に再加算しない）。

|変異|入力クラスと適用した変換|赤の試験数|実行行trace|
|---|---|---:|---:|
|M1|別PJ実体の照合を削除|1|2|
|M2|公開規則blobの意味を無視|6|44|
|M3|規則走査を削除|1|1|
|M4|申告だけを通過へ変更|2|2|
|M5|本文だけの発注を捨てstate件数へ置換|2|2|
|M6|未来時刻の拒否を削除|1|4|
|M7|snapshotの鮮度比較を無効化|1|7|
|M8|巡とcapを入替え|2|11|
|M9|公開日ファイルだけ走査から除外|1|10|
|F1 ①|矛盾IDの拒否処理を消す|10|10|
|F2 ②|履歴読取失敗を握りつぶす|3|4|
|F3 ③|通常と特例のauthorityを入替え|2|2|
|F4 ④|ID内容の比較そのものを自己比較で無効化|10|20|
|F5 異種回避1|承認条件のANDをORへ広げ、cap無しを通す|1|4|
|F6 異種回避2|発注同一性をSHAだけへ射影し、日時・巡・種別の変更を隠す|6|20|
|F7|予約から保存authorityを消す|1|1|

陽性: 既存の時刻比較の等価変換で、巡3特例・通常人間承認・timezone同値の3試験が緑。新規ID比較の等価変換で、同内容の重複・正常な通常承認・通常空証跡からの特例の3試験が緑。探索クラスは上表に加え、同一IDの各固定欄を単独変更×人間承認有無、参照IDなしの書式破損×承認/capの4組、特例stateの固定cap不一致、予約への保存を試した。

commit禁止が今回の個別指示のため、修正自体はcommitしていない。変異は `git archive HEAD`（e6b0e421da561b7947ec30eb58f247fe1b46f472）から各写しを作り、今回の製品・試験だけをoverlayしてから1件ずつ適用した。厳密な「修正commitから変異」とは異なるため、基点commitとoverlay差分を別保存している。原本に変異を当てず、終了時のtracked diffが開始時の修正差分とbyte単位で同一であることをrunnerと独立監査で確認。`.tmp/fixA/source-audit.json` で製品2・試験2ファイルが未変異写しと一致することも確認した。原本のgit diffは今回の未commit修正として残す。

## 呼出し元と環境
`git grep -n -E 'history\(|pre\.evaluate\(|prerelease import|run_gate\(|authority=\{result' -- lib bin tests` の全44行を `.tmp/fixA/callers-final.txt` に保存。
|変更箇所|製品の呼出し元|確認|
|---|---|---|
|history|evaluateのstrict=True、run_gateのstrict=False|既存和集合・本文/台帳重複・新規矛盾/書式破損・CLI通し|
|evaluateの保存証跡判定|run_gateの特例分岐|通常空証跡→特例・保存cap拒否・特例CLI通し|
|run_gate|round_gate.mainのgate、bin/codex-reviewのgate呼出し|既存round_gate/CLI試験と人間承認/特例対照|
|予約のauthority保存|round_gate.mainのreserve-run-id経路|reservation_keeps_authority、既存予約・鮮度・同時発注試験|

|環境|経路・設定・データの違い／今回の実施|
|---|---|
|ローカル|合成Git・fake gh/codex、作業場所内の小さい写しと証跡。実物~/.codex-watchはレビュー読取のみ|
|dev|接続・読取・書込無し。今回の製品変更にdev固有分岐無し|
|stg|接続・書込無し。今回の製品変更にstg固有分岐無し|
|prod|接続・書込無し。今回の製品変更にprod固有分岐無し|

## 検証コマンドと残り
- 修正前: committed HEADの独立写しへ最終の再現試験と既存fixtureを配置し `python3 -m pytest -q -p no:cacheprovider tests/test_prerelease_fixA.py` を実行。15失敗・4成功（`.tmp/fixA/before-exact.log`）。矛盾ID10件・壊れた履歴3件・通常空証跡1件・予約authority1件が赤。
- 変異: `python3 tests/check_prerelease_fixA_mutations.py > .tmp/fixA/mutations.log 2>&1`。16陰性赤・2組の陽性対照各3成功。
- 全体の初回は679件中577成功・97失敗・5skip。試験の一時ファイルをrepo内に置いたため非repo想定のfixtureが親Gitを拾う失敗が95件、authority無しの特例fixtureが2件。後者は実stateに合わせてauthorityを補い、前者は実行時のGit探索上限で隔離した。origin/mainでは同一試験を実行していないので「前からある赤」とはしない。
- 最終全体: `GIT_CEILING_DIRECTORIES="$PWD/.tmp/fixA" python3 -m pytest tests -q -p no:cacheprovider --basetemp=.tmp/fixA/final-temp > .tmp/fixA/final-full.log 2>&1`。最終件数は先頭行に記載。5skipは実keychainを使うopt-in4件とimplでは対象外のrecord1件。AWS・DBへ接続する試験は対象外で未接続。
- 原本検査: `git diff --check` 成功、差分は今回の修正のみ。製品2・既存試験1・追加試験/runner・報告類を未commitで残す。HEADはe6b0e42のまま。commit・push・PR・枝操作無し。
- 共有先 `/Users/matsukaze-takashi/updater/updater-index/_work/notes/codex-queue/` はこの窓の管理された書込許可範囲外のため2ファイルを直接保存できない。選択肢は頭が転記する、またはその場所に書込可能な窓へ渡す。既定案として同名2ファイルをこの作業場所の `docs/design/` に保存し、次回依頼を転記だけに限定した。製品作業は今回分を終え、共有先への保存は未完了。
