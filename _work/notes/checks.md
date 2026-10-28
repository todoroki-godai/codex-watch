# 実行した検査の範囲

すべてオフラインのfixture。Codex/ghは必要な既存試験内でfake実行ファイルを使用し、実CLI・外部サービス・DBには接続していない。実keychainを使う5ケースは既定でskip。

|コマンド全文|対象試験ファイル数|結果|
|---|---:|---|
|`python3 -m pytest -q tests/test_codex_capacity.py -k 'role_section_error_quote or rechecks_capacity'`|1|修正前: 5 failed, 63 deselected|
|`python3 -m pytest -q tests/test_codex_capacity.py`|1|最小修正後68 passed。その後、範囲外故障の確認追加後76 passed|
|`python3 -m pytest -q tests`|8|7 failed, 361 passed, 5 skipped（合計373）|
|`python3 -m pytest -q _work/baseline/tests/test_codex_review_cli.py`|1|HEADをgit archiveで展開したコピー: 同じ7 failed, 6 passed。KIND_LABEL未指定で停止する既存失敗|
|`env CODEX_REVIEW_KIND_LABEL=コード python3 -m pytest -q tests`|8|368 passed, 5 skipped（合計373）|
|`python3 -m pytest -q tests/test_codex_capacity.py --basetemp=_work/pytest-capacity-final`|1|SIGHUP確認追加後の最終版77 passed|
|`env CODEX_REVIEW_KIND_LABEL=コード python3 -m pytest -q tests --basetemp=_work/pytest-full-final`|8|12 failed, 357 passed, 5 skipped（合計374）。作業場所内のfixtureが親Gitのoriginを拾い、example-org/example-repoとの不一致を検出。ソースは変更せず次の実行で親Git探索を隔離|
|`env CODEX_REVIEW_KIND_LABEL=コード GIT_CEILING_DIRECTORIES="$PWD" python3 -m pytest -q tests --basetemp=_work/pytest-isolated`|8|369 passed, 5 skipped（合計374）。最終版全8ファイル。出力: full-tests-isolated.txt|
|`python3 _work/notes/run_mutations.py`|各回1|初回76ケース版で探索。06がawk構文エラーのため不採用とし、修正して77ケース版で全7変異を再実行。内部コマンド全文・選択件数はmutations.md / mutation-results.json|
|`bash -n bin/codex-watch bin/_codex_common.sh`|シェル2ファイル|exit=0|
|`git diff --check`|変更3 trackedファイル|exit=0|

変異検査の正式採用結果はmutations.mdを参照。構文エラーによる初回06の赤は変異有効性の証拠に数えない。正式な陰性7件はすべてexit=1、陽性対照は77 passed。復元と元実装の不変を確認し、使い捨てコピーは削除済み。

## 判定と範囲外

M1・M2のはしごは各々第2段。M1は既存の共有判定を再利用して状態の固定化を除去。M2は既存report抽出の区間を再利用し、追加依存・終了コード保存・起動ラッパー・出力形式移行は足さない。

出力区間は平文の推定。真正な出力元や構造化イベントによる保証へは未移行。hook行の引用による偽装、codex本文区間に割り込むstderr、未知の文言は非保証。コードとadvisory_bypassable名の試験に残した。

通信切断、途中停止ではEXIT/異常終了を確認。起動親がいないまま実行プロセスが生きる状態はTIMEOUT通知を確認（親プロセスそのものの終了は再現せず、親の記録がない現設計と同じ生存状態で模擬）。watcher自身のSIGHUP/SIGTERM終了にはtrapがなく、EXIT通知なしを実測。この経路は今回修正しない。

既存のkill -0はstderrを捨てるため権限エラー等の理由を隠し、PIDの生存確認だけでは親・子の対応関係を保証しない（静的確認）。また非空の部分reportはwatcherの「報告あり」表示に使われるため、通信失敗時の作業完了保証にはならない（静的確認）。

受領5点はreview-receipt.md。HEADは開始時と終了前で同じa146cc5a7d40b7fee0de6fbb09ee6a50a6ba732b。commit/push/枝操作/PR/外部レビューは行わず、変更は作業ツリーに残した。
