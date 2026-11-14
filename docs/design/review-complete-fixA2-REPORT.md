A 直し: 通常経路の数え方を本体と同じに戻した／影響 止まるようになる 0件／試験 688件成功

## 試験を書く前の入力区分表

出所: 今回の依頼1〜4、#38本文の本人回答「数え方を外す・上限4回」、設計2.3。正常系から書く。

|入力|区分・境目|置く値|期待|期待の出所|大きさ|試験名|
|---|---|---|---|---|---|---|
|通常発注|正常系の通し・時刻・継ぎ目|同じSHAへ7秒差の巡1を2行、台帳2件、次のSHA|巡2で通過、旧run_gateと一致|依頼D1|run_gate＋固定本文/台帳|ordinary_parallel_round2|
|履歴の説明|文字・欠け|履歴節に説明文、次巡2|履歴解析で停止せず通過|依頼D2|run_gate|ordinary_prose_round2|
|通常承認|できる操作・特例との境目|巡3の人間承認＋cap3、壊れた履歴、record参照あり/なし|humanで通過、特例照合を呼ばない|依頼1|run_gate|human_approval_with_bad_history|
|特例履歴|できない操作|同IDの巡/SHA/時刻/種別の食い違い、壊れた行|特例不成立、通常の判定へ戻る|依頼1|evaluate＋run_gate|conflicting_id / malformed_history / exception_bad_history_falls_back|
|特例巡数|数字・2/3境界と固定上限|台帳2巡、今回3巡、本文のみ余分なID|正常は特例通過、過小計数は特例拒否|依頼1・7段|CLI＋evaluate|completed_history_round3_dispatch / exception_extra_dispatch|
|規則blob|合図・できない操作|2ファイルそれぞれの既定枝/remote blob変更|特例拒否|依頼7段|Git/API fixture|each_registered_blob_change|
|承認境界|文字と欠け|承認無し/承認のみ/capのみ/両方|旧版の通常判定と一致|依頼1|run_gate|malformed_history|
|変更しない境界|時刻・空白・cap2/3/5/6、bypass併用、別PJ、公開後|既存の代表値を維持|既存の特例検査を維持|設計2.1〜2.3|既存パッケージ全体|test_prerelease.py / test_prerelease_implA3.py|

DB・画面・dev/stg/prod接続は対象外。新しい文字正規化や時刻の決めは足さず、既存試験で確認する。


## 実装・判断

`run_gate` の通常経路から `history(strict=False)` による上書き、矛盾行の先行停止、解析失敗の停止条件を削除した。通常の `total` と `decide(total, body)` は本体 bdb4d62 と同じ。通常判定が止まり、裁定IDがある場合だけ、既存 `evaluate` が `history(strict=True)` を呼ぶ。特例不成立時は通常の判定に理由を足して返す。`history_round` は特例成功時だけにし、通常前置きの台帳計数も本体に戻す。

`lib/prerelease.py` の検査は変更していない。2規則blob照合・固定上限・bypass併用禁止・PJ実体・公開終了・同IDの矛盾・壊れた行・履歴と判定巡の一致を保つ。Cの発注単位への移行・Dの接続は今回しない。

既存fixtureは、本文の履歴だけで巡3になる前提を、過去2巡を台帳にも置く入力に直した。CLIが新しく生成した `fixture-*.state` と過去のstateを区別して確認する。同一IDの重複・矛盾・壊れた行の検査は特例側のhistoryに移し、通常経路で止める旧期待を本人決定に合わせて変更した。試験の削除はない。

## 読んだもの

|必須欄|出所|
|---|---|
|段取り表の該当行|無し（今回にT番号・段取り表行の指定なし。#38のA直しだけ）|
|本人の決定|#38本文「巡4の人間承認」、回答「数え方を外す・上限4回 (Recommended)」、受領2026-11-13 18:46:32 JST。今回gh読み取りで取得し `.tmp/fixA2-issue38.md:37-45` に保存|
|見本HTML|無し（ローカルの発注関門で画面変更なし）|
|前身の設計と巡|`docs/design/review-complete.md`、`docs/design/review-complete-fixA-REPORT.md`、今回指定の `a-round4-materials-20261113.md`（updater-index共有notes/refactor）|
|影響確認|`.tmp/impact/REPORT.md` の31件・13件の内訳と本文行、`compare.py`、`verify_gates.py`、保存済みcomparison/github/inventory/predecessorsとstateの写し|
|製品|`lib/round_gate.py` の通常/特例分岐・台帳計数・CLI、`lib/prerelease.py`、`bin/codex-review` のgate/前置き/送信前確認、`git show bdb4d62:lib/round_gate.py`|
|試験設計|作業場所に `.claude/skills/test-design/` はない。設計が指す `/Users/matsukaze-takashi/updater/updater-index/_wt.noindex/rev9-audit/.claude/skills/test-design/SKILL.md` を読み、先に本書の区分表を作成|
|既存の検査|`tests/test_prerelease{,_implA3,_fixA}.py`、既存の変異runner、commitスキル|

## 7段・再利用

|項目|止まった段と判断|
|---|---|
|通常の和集合計数|㋐。Aの目的に要らないので削除。パーサの高機能化を採らない|
|特例の履歴と承認優先|㋐明示の不変条件、㋑既存 `evaluate/history/decide` で足りる。履歴パーサ・依存を足さない|
|D1/D2と境界の検査|㋐明示依頼、㋑既存pytest fixture・render_round_row・gateを再利用。通常入力の新しい代表だけ追加|
|変異証跡|㋐省略不可、㋑既存 `check_prerelease_implA3_mutations.py` のarchive/diff/line traceを再利用。修正commitを前提とするrunnerを用意、実行未了|
|影響の再比較|㋐明示依頼、㋑既存の取得済み写し・旧モジュールと実run_gateを再利用。㋒標準importlib/json/hashlibのみ。新規取得は不要|

追加前探索 `git grep -n -E 'render_round_row|target_total_rounds|ConflictingHistory|settrace|archive' -- lib tests` は48行（`.tmp/fixA2/reuse.txt`）。新しい製品関数・設定・依存は追加しない。CHANGELOGは追跡ファイルに存在せず、追加しない。

## 検証と停止理由

- 関連4ファイル: `python3 -m pytest tests/test_prerelease.py tests/test_prerelease_fixA.py tests/test_prerelease_implA3.py tests/test_prerelease_fixA2.py -q` → **116 passed**（`.tmp/fixA2/focused-final.log`）。最初の実行で2件失敗したのは、別targetの台帳が空のときの旧期待の直し残しで、今回修正済み。本線で測っていないため「前からある赤」とはしない。
- 全体試験: `TMPDIR="$PWD/.tmp/fixA2" GIT_CEILING_DIRECTORIES="$PWD/.tmp/fixA2" python3 -m pytest tests -q` → **688 passed, 5 skipped in 256.15s**（全tests、693件。`.tmp/fixA2/full.log`）。5skipはopt-in keychain4件とimplでは対象外のrecord1件。失敗0件。生成物は作業場所内。
- DB検査: 未実行（対象外、接続なし）。実環境の送信や採用は検証していない。
- 先頭の影響0件は未commit版での暫定値であり、終了条件全充足を意味しない。
- `git diff --check` 成功。runnerと影響比較スクリプトはAST構文検査成功。
- commit実行はPreToolUse hookで拒否された。期待 `todoroki-godai`、write時点の名義 `matsukaze-minden` というアカウント不整合。ユーザー指定どおり切替・再試行・迂回せず未commitで残した。indexも空、HEADは開始時の `8e400b5e407de0d6fb7dc8c61048286a707ca69d` のまま。
- **変異は未実行**。指示が要求する「修正commitから適用」を満たせず、未commit差分のoverlayでは代用しない。陰性の生存数・着弾数は未確認。修正diffは残っており、最終 `git diff` が空という条件も未充足。完了ではない。

## 変異の準備（結果ではない）

|分類|探索した入力クラスと適用予定の変換|判定に使う試験|
|---|---|---|
|①|7秒差の並行発注。通常経路に和集合maxを復活|ordinary_parallel_round2|
|②|説明文を含む通常本文。解析失敗で停止へ戻す|ordinary_prose_round2|
|③|巡と総上限の順序。cap比較の左右を入替え|round_cap_boundaries|
|④|既定枝/localの各規則blob変更。照合条件をFalse固定|each_registered_blob_change|
|①|同一IDの各固定欄の矛盾。拒否raiseを削除|conflicting_id|
|②|壊れた履歴行。拒否raiseをpassへ置換|exception_bad_history_falls_back[malformed]|
|異種回避1|出力契約。通常のhistory_roundもtotalへ固定し前置き経路を変える|ordinary_parallel_round2 / ordinary_prose_round2|
|異種回避2|評価順序。人間承認が通っていても特例evaluateを呼ぶ|human_approval_with_bad_history|
|陽性対照|正常判定。位置引数bodyを同じkeyword引数へ書換え|ordinary_parallel_round2 / ordinary_prose_round2 / human_approval_with_bad_history|

`tests/check_prerelease_fixA2_mutations.py` は、dirtyな追跡ファイルがあれば開始しない。修正commitのarchiveから各写しを作り、変更文字列の一致が1箇所であること・非空のmutation.diff・独立tracerのexecuted.log・pytestのexit1（陽性0）とassertion失敗を検査する。証跡は `.tmp/fixA2/mutations/<変異名>/{mutation.diff,executed.log,pytest.log}`、集計はresults.json。未実行なので、陰性8件赤・陽性緑と記載しない。予定した異種回避2件も適用未了。

## 31件の暫定影響確認

`.tmp/impact/REPORT2.md` の先頭: **A 直し後の影響: 対象 31件／同じ 31・巡が増える 0・止まるようになる 0・通るようになる 0**。HEADを進めた条件も同じ31・増加0・停止0・通過0。

`python3 .tmp/impact/compare2.py --working-tree` で旧bdb4d62と未commit修正を比較した。31対象×2版×2HEAD条件＝124判定。旧モジュールは `git show bdb4d62:lib/round_gate.py` とバイト一致し、旧側の62結果は前回のcomparison.jsonとも一致した。前回のHEADを固定しているので、当時から動いた作業場所のHEADを混ぜていない。現在HEAD不明3件の仮定も前回のまま。

`comparison2.json` に入力SHA256・製品2ファイルのSHA256・HEAD・未commitフラグ・全結果を記録し、入力を実行前後で照合した。`.tmp/impact/fixA2-workingtree.diff` が今回計測した製品差分。本物のstate/本文は変更せず、gh追加取得もしていない。**これは未commit版の測定で、依頼6の「新＝今回のHEAD」は未了**。頭のcommit後に `python3 .tmp/impact/compare2.py` を実行して版を確定する。

## 呼出し元

探索 `git grep --no-index -n -I -E 'run_gate\(|history_round|history\(|evaluate\(' -- lib bin tests` の全78行は `.tmp/fixA2/callers-all.txt`。未追跡の新規試験も含めた（通常のgit grep版は65行）。定義や変異文字列も含むため78を呼出し件数とはしない。

|変更した関数/値|製品の全呼出し元|確認|
|---|---|---|
|run_gate|`lib/round_gate.py:1412` mainのgate。シェルは `bin/codex-review:102` 通常gateと`:257` 送信前予約gate|test_round_gate、test_codex_review_cli、prerelease CLI/予約/鮮度/並行試験をパッケージ全体で検査|
|history_round|`bin/codex-review:122` 前置きの巡数選択|通常はNone→旧台帳、特例成功はtotal。D1/D2の出力検査と既存のCLI保存/前置き試験|
|history（通常呼出しを削除、関数は変更なし）|`lib/prerelease.py:178` evaluateのstrict=Trueだけ|矛盾ID・壊れた行・余分なdispatch・本文/state和集合の既存試験|
|evaluate（変更なし）|`lib/round_gate.py:1280` 特例分岐|通常承認を先に通す陽性/陰性入力、特例不成立のfallback、既存blob/上限/公開後/別PJ検査|

## 環境ごとの違い

|環境|経路・設定・データの違い／今回|
|---|---|
|ローカル|合成Git・fixtureのfake gh/codexと、2026-11-13取得のstate/本文の写しで検査。実LLMを呼ばない|
|dev|固有の分岐変更無し。接続・読み取り・書込み無し|
|stg|固有の分岐変更無し。接続・書込み無し|
|prod|固有の分岐変更無し。接続・書込み無し|

## 引継ぎ

頭が今回の変更をcommitした後、変異runnerを実行し、陰性全件赤・陽性緑・着弾の差分とtraceを確認する。暫定影響確認を修正HEADで確定し、停止0件と全体の緑、変異生存0件、diff空を揃えて初めて完了にする。その後のコードレビュー巡4は別の手番。

指定のupdater-index共有 `codex-queue` への2ファイル保存は、この窓の管理された書込み許可の範囲外で未実施。承認を求めてもこの窓の許可ポリシーでは拡張できない。選択肢は頭が転記する／共有先に書込可能な窓へ引き継ぐ。既定案は、作業場所の `docs/design/refactor-result-review-complete-fixA2.md` と `refactor-next-review-complete-fixA2.md` を頭が同名の指定先へ転記すること。
