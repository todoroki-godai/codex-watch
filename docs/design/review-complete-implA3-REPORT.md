codex-watch#38 A 変異: 陰性 9件すべて赤／陽性対照 3件緑／全試験 656件成功

入力の区分表（追加試験を書く前。出所は設計2.1〜2.3とimplA3依頼）
|入力|区分・境目|置く値|期待|出所|大きさ|試験|
|---|---|---|---|---|---|---|
|正常発注|補完後の巡3通し|本文2発注・cap3|判定・前置き・予約・保存が3|Should②|fake CLI|既存 completed_history_round3_dispatch|
|通常承認|公開API失敗|人間承認・cap3|通過|Should①|fake CLI|既存 human_approval_ignores_policy_failure|
|規則blob|2登録ファイル×ローカル/公開先|それぞれの内容変更|特例拒否|設計2.1・依頼1②|一時Git＋関数|追加 each_registered_blob_change|
|公開日|終了状態からの操作|dev-standing-approval.md写しに公開日・本人原文・受領時刻を追記|特例拒否|依頼3|一時Git＋関数|追加 publication_append|
|申告|環境だけ／本文だけ|project_prereleaseの語、正本JSON無し|送信拒否|依頼1④|fake CLI|追加 claim_channels / claim_gate_core|
|数・継ぎ目|巡とcap入替・本文履歴の消失|既存境界表・state空|不正受理なら試験が赤|依頼1異種回避|関数＋CLI|既存 round_cap_boundaries / union_body_only_and_state_only|
|時刻・合図|未来／snapshot変化|既存境界表・本文改行|拒否|設計2.2・2.1|関数＋CLI|既存 decision_time / recheck_and_reservation|
|文字|意味保存|比較の等価変換・timezone同値|緑|依頼2|関数＋CLI|既存 semantic_positive_control とソース変異|

7段: ㋐明示依頼、㋑既存fixture・8変異runnerを再利用、㋒標準ライブラリで追加runnerを構成。新依存無し。既存原本の変更無し。

実測版: `f75723cf238e2c2ec3b43acdc9536485dc0aad51`。commitは依頼どおり無し。原本はgit archive HEADから取り、追加試験1ファイルだけを各写しへ配置した。
再現コマンド全文（この作業場所で実行）: `python3 tests/check_prerelease_implA3_mutations.py > .tmp/implA3-mutations.log 2>&1`、続いて `python3 -m pytest tests -q > .tmp/implA3-final-full.log 2>&1`。
既存探索: `git grep -n -E 'dev-standing-approval|published-rule|mutation' -- tests/check_prerelease_mutations.py tests/test_prerelease.py config/prerelease-projects.json` と `git grep -n -E 'check_prerelease_mutations|test_policy_and_history_fail_closed|test_semantic_positive_control' -- tests docs/design/review-complete.md` で既存runner・fixture・対照を確認して再利用（記録 `.tmp/implA3-existing-reuse.log`）。原本runnerは子Pythonのpytest探索で停止し、既存M4試験は履歴解析で早期停止して未着弾だったため、追加runnerのPYTHONPATHと独立したgate本体試験で補った。前からある赤とは呼ばない。

|陰性変異（各1写し）|変換・探索クラス|赤の試験数|独立実行行trace件数|
|---|---|---|---|
|M1-other-project|①共通Git実体比較の削除／同一slug・未登録実体|1|2|
|M2-published-policy|②blob比較無効／2ファイル×origin・公開commit、公開日追記|6|44|
|M3-missing-policy|③規則走査削除／既定枝に規則無し|1|1|
|M4-claim-fail-open|④拒否処理無効／環境申告・本文の語だけ|2|2|
|M5-body-history-lost|異種1: 本文発注を捨てstate数へ置換／履歴の継ぎ目|2|2|
|M6-future-time|異種2: 未来判定削除／時刻|1|4|
|M7-stale-snapshot|異種3: 再比較無効／合図・鮮度|1|7|
|M8-cap-swap|異種4: 巡とcap入替／数・境界|2|11|
|M9-selective-release-skip|公開日ファイルだけ走査除外／終了状態|1|10|
陰性9件すべてexit=1・生存0・未着弾0（失敗したassertionを各pytest.logで確認）。陽性は時刻比較を `when > now` → `not when <= now` に等価変換し、正常巡3通し・API失敗時の通常人間承認・timezone同値の3件が緑。上表の赤の試験数と変異件数は別であり、合算しない。
差分・traceのソース行一致の再監査も成功（`.tmp/implA3-evidence-audit.log`、追加2ファイルのSHA256を記録）。独立証跡: `.tmp/implA3-mutations/<変異名>/mutation.diff` が不変条件を壊した差分、`executed.log` が変更箇所の独立line trace、`pytest.log` が全出力。集計と個別コマンド全文は同ディレクトリの `results.json`、全実行の出力は `.tmp/implA3-mutations.log`。M8はcap・巡・比較結果もtraceに記録。差分非空・trace非空・期待exit・setup/collectionエラー無しをrunnerで機械確認した。
公開終了の専用試験は、rev9-auditの `dev-standing-approval.md` 全文の写しを追加試験に固定し、公開日・本人原文・受領時刻の行を追記した一時Gitの既定枝版を使用。追記前の受理、blob変化、追記後の「公開終了・規則欠落・未知版」拒否を確認。対象HEAD/base/contentも更新し、対象版不一致に隠れた拒否を避けた。M9の走査除外でこの試験が「例外無し」の赤になるため、公開後の自動終了検査自体も着弾を確認済み。

読んだもの: `docs/design/review-complete-implA2-REPORT.md`、`refactor-next-review-complete-implA2.md`、`review-complete.md` Aと入力区分、指定 `task-review-complete-implA2.md` 陰性試験節、`~/.codex-watch/review-complete-d1-20261113-163337-8555.report` のShould2件、既存runner・test_prerelease・prerelease・round_gate・CLI・conftest・固定登録、rev9-auditのtest-design SKILL.mdとdev-standing-approval.md。段取り表のT番号は無し（指定なし）、割当ては `_work/notes/rev9-review-history.md:275`。本人決定は今回依頼のA・C・D中継原文と16:22:03 JST受領。見本HTMLは無し（画面変更無し）。
製品の関数・値は変更無し。呼出し元は既存runnerを手動起動する上記コマンド、追加試験はpytest収集。既存fixture/ヘルパーの使用箇所は `git grep --no-index -n -E 'case|evaluate|run_cli|run_gate|CASES|PYTHONPATH' -- tests/test_prerelease_implA3.py tests/check_prerelease_implA3_mutations.py` で列挙して `.tmp/implA3-callers.log` に保存。全試験で既存経路も再検証。

|環境|経路・設定・データの違い／今回の実施|
|---|---|
|ローカル|一時Git・fake gh/codexのみ。公開前／公開後は規則blobで区別。fixture内のcommit・ref更新は合成データのみ|
|dev|常時承認の別規則。今回は接続・読取・書込無し|
|stg|公開前特例は書込許可を発行しない。今回は接続無し|
|prod|同上。今回は接続無し|
AWS・DB・実GitHub・実LLM試験は未実行（対象外）。資格情報の取得・表示・保存、実物~/.codex-watchへの書込無し。配布・cold review・C/Dは本作業の対象外。
指定queue出力先はsandboxの書込許可外（承認要求も不可）。既定案として作業場所の `docs/design/refactor-result-review-complete-implA3.md` と `refactor-next-review-complete-implA3.md` を転記用に残す。頭が指定先へ転記し、必要な新規ファイルをcommitする。製品・既存試験の原本は変更せず、追加試験・runner・報告は未追跡で残す。

最終全試験: `python3 -m pytest tests -q` → **656 passed, 5 skipped in 298.31s**（tests全体661件、既存647成功＋追加9成功）。skipは実gh/keychain opt-in4件とreview専用のimpl側1件。全出力 `.tmp/implA3-final-full.log`。変異後の `git diff`・`git diff --cached` は空、HEADはf75723cのまま。未追跡5ファイルだけを引渡し、commit無し。変異検証1〜5は完了、指定queueパスへの直接保存のみ許可制約で未実行。
