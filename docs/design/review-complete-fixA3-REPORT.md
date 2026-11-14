A 直しの確認: 変異 陰性10件赤・陽性1件緑・生存0件／影響 止まるようになる 0件（HEAD 8142def）／試験 688件成功

## 読んだもの

|欄|内容|
|---|---|
|段取り表の該当行|無し（T番号・該当行の指定なし）|
|本人の決定|`.tmp/fixA2-issue38.md:37-45` に保存された #38 本文。2026-11-13 18:46:32 JST の「数え方を外す・上限4回 (Recommended)」|
|見本 HTML|無し（ローカルの判定検証で画面変更なし）|
|前身の設計と巡|`docs/design/review-complete.md`、`docs/design/review-complete-fixA-REPORT.md`、`docs/design/review-complete-fixA2-REPORT.md`|
|今回の手順|`tests/check_prerelease_fixA2_mutations.py`、`.tmp/impact/compare2.py`|

## 変異

開始時 HEAD は `8142defe74f4d934c136d8c8c85cec8c8c668ed2`、追跡差分なし。commit の archive の独立した写しに変異を適用し、実ソースを変更せず、変異後にも `git diff` が空であることを確認した。指定 runner は陰性8件すべて検出、陽性1件成功。さらに前回提案された E1/E2 と異なる2件を実際に適用し、いずれも検出した。各ケースで非空 `mutation.diff` と独立トレーサーの `executed.log` を確認した。陽性・陰性の件数は変異ケース数であり、pytest の個別試験数ではない。

|区分|入力クラス・変換|結果|
|---|---|---|
|①|7秒差の並行発注に通常経路の和集合を復活|赤|
|②|履歴説明文に解析停止を復活|赤|
|③|巡と総上限の比較順序を入れ替え|赤|
|④|規則 blob の照合を無効化|赤|
|①|同じ発注 ID の矛盾の拒否を削除|赤|
|②|解釈不能な履歴行の拒否を削除|赤|
|追加 E1|通常経路の history_round 出力を変更|赤|
|追加 E2|人間承認より特例評価を優先|赤|
|追加 E3|通常の巡数に 1 を加算|赤|
|追加 E4|特例の履歴と巡の不一致判定 `!=` を `<` に変更、過大な履歴を見逃す|赤|
|陽性|同じ body を位置引数からキーワード引数へ変更|緑|

証跡: `.tmp/fixA3/mutations.log`、`.tmp/fixA2/mutations/results.json` および各ディレクトリの `mutation.diff`・`executed.log`・`pytest.log`。追加2件は `.tmp/fixA3/extra_mutations.py`、`.tmp/fixA3/extra-mutations/`。runner は各陰性の pytest exit 1 と失敗、陽性の exit 0 を確認する。各変異の実行回数・試験結果は results.json を参照。

## 影響

`python3 .tmp/impact/compare2.py` を未commitフラグなしで実行。2026-11-13 時点の取得済み写し 31対象、旧 bdb4d62／新 8142def、2版×2 HEAD 条件で124判定。元のHEAD条件・更新後条件とも同じ31、巡が増える0、止まるようになる0、通るようになる0。現在の OPEN 状態の再取得や実送信は対象外。`.tmp/impact/REPORT2.md`、`comparison2.json`、`.tmp/fixA3/impact.log` に根拠を保存。

## 試験・範囲

全体試験 `TMPDIR="$PWD/.tmp/fixA3" GIT_CEILING_DIRECTORIES="$PWD/.tmp/fixA3" python3 -m pytest tests -q`: 688 passed、5 skipped、全693件、386.59秒。5 skip は keychain opt-in 4件と対象外 record 1件。失敗0件。ログは `.tmp/fixA3/pytest.log`。DB 検査は未実行（対象外）。製品コード・呼出し元は変更していない。機構や依存は追加していない。7段は前回報告に記載のとおり、通常経路の不要な計数を外す㋐、検証は既存 runner・比較器を再利用する㋑。

|環境|経路・設定・データの違い／今回|
|---|---|
|ローカル|合成 fixture と取得済み state・本文の写しを利用|
|dev|接続・読取・書込なし|
|stg|接続・書込なし|
|prod|接続・書込なし|

次は別手番のコードレビュー巡4。commit は指定により実施しない。指定された updater-index の共有先は書込許可範囲外のため、同内容の引継ぎファイルを作業場所内に用意し、頭による転記を既定とする。
