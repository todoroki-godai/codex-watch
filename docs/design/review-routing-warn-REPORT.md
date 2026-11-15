D 警告接続: 試験 805件成功／変異 陰性9件赤・陽性1件緑・生存0件

# 現在地

`bin/codex-review` の既存A/C・点検・公開前特例の再照合/予約の後、nohup直前へ警告だけの接続を追加。
adapterのpass/would_block/error/invalid/timeout/missingによらず発注を継続し、stateと同じディレクトリの
`routing-warn.jsonl`へ1発注1行を追記する。stderrも1行。記録不能時は同じ行へ「記録失敗」を添えて継続する。
公開前予約を新設・削除するコードは追加していない。既存ゲートで拒否した発注はDに到達しない。

起点HEAD: `f750af362f3baa32cdcedc4912bf16d31151504a`。commitは今回の個別指示どおり行わず、未commit変更を頭へ渡す。
レビュー・push・PR・枝操作・実LLM発注・外部書込みは実施していない。1週間の実運用計数とレビューは頭の後続作業。

# 読んだもの・出所

参照ルートは `/Users/matsukaze-takashi/updater/updater-index/_wt.noindex/review-routing-d`。

- 段取り表の該当行: 無し（今回の依頼にパス/行なし）。既定案として今回の作業1〜6を対象にした。
- 本人の決定: 本依頼に転記された「警告だけでつなぐ (Recommended)」、調整役main-index経由、2026-11-15 10:08:23 JST受領。#2006/#38のD。新しい承認の取得や推定はしていない。
- 本人が見た説明: 本依頼の「発注は止めず、引っかかったものを理由ごとに1週間数える。その後、自動で作れる記録を足してから、止める形にするかを決め直す。今日の作業は小さく、戻すのも簡単」。
- 見本HTML: 無し（CLIの変更で画面なし）。
- 前身設計・巡: `_work/notes/review-routing/design.md`、`review-round1-receipt.md`、`round2-fix-report.md`、`round3-record.md`。設計冒頭と履歴の出所を確認し、過去の合否は再認定していない。
- 準備報告: `_work/notes/review-routing/activation/REPORT-d.md`。条件つき37件（系列/前身不足32、作業場所消失5）と予約が残る問題を確認。
- 同activationの`patches/`4本（CLIの往復パッチ、hookパッチの接続部分）を確認。停止型のCLIパッチは適用していない。
- `_work/notes/review-routing/skill-src/adapter.py`と`route.mjs`（入力/出力契約、段と理由、監督とworkerの起動経路）。部品の配布や変更はしていない。
- 作業場所の`bin/codex-review`、`bin/_codex_common.sh`、`lib/round_gate.py`の関連経路、`tests/`の既存CLI/fake/変異手順、`README.md`。
- 試験設計は参照ルートの`.claude/skills/test-design/SKILL.md`を使用。作業場所に同スキルがないため、前身にある正本を読む既定案で進めた。先に作成した表は`review-routing-warn-test-design.md`。

# 実装と7段

| 足したもの | 止めた段と理由 |
|---|---|
| 警告接続 | ㋐本人の明示依頼。㋑既存nohup前の接続位置を再利用、呼出し1行は㋕ |
| 判定処理 | ㋑既存adapterとrouteを呼び出す。振分けの判定は再実装しない |
| 外側の固定30秒・出力上限・終了処理 | ㋒Python標準subprocess/selectors/time/signalで実装。部品なし/異常でも継続する責任は新接続に必要 |
| 出力契約の検査 | ㋒jsonと既存五段契約。型/段順/終了値の整合を確認する信頼境界の検査 |
| 計数のJSONL | ㋒json/osの追記、単一write。秘密を含み得る生出力・生理由を保存せず固定理由へ分類 |
| adapterの指定 | ㋓既存環境変数の慣行。CODEX_REVIEW_ADAPTER、REVIEW_GATE_RECORD、CODEX_WATCH_DIRを使用 |
| 集計・戻し方 | ㋕READMEの1行コマンドと接続2行の削除。専用集計ツールは㋐で不要とした |
| 試験・変異証跡 | ㋑既存pytest/fake sender/一時state、既存の複製方式を再利用。外部依存追加なし |

追加前の検索:
`git grep -n -E 'routing-warn|routing_warn|REVIEW_GATE_RECORD|CODEX_REVIEW_ADAPTER' -- bin lib tests README.md` は0行。
`git grep -n -E 'TimeoutExpired|killpg|jsonl|setitimer' -- lib tests` は32行。
既存のJSONLはトークン読取等で、今回の警告追記処理は見つからなかった。結果は`.tmp/review-routing-warn/reuse-{exact,related}.log`。

`CODEX_REVIEW_ADAPTER`未設定時は`$HOME/.claude/skills/review-gate/adapter.py`。引数は記録JSONのパス・workdir。
REVIEW_GATE_RECORDが未設定でも空文字で部品へ渡し、その失敗を記録する。
正常でも警告1行を出す。JSONは一行性を守ってASCII escapeし、その前の固定ラベルに「時間切れ」「部品なし」などの日本語を明記する。理由分類は系列/前身不足・作業場所消失・累計差分超過・同族反復・検査記録不足・green記録不備・その他。
既知の理由に該当しない生文を保存しないため、「その他」の詳細をこのJSONLだけから復元することはできない。
UTCの時刻と対象・種別・発注ID、判定、停止相当の段を記録する。

# 試験と変異

パッケージ全体: **805件成功・5件skip・失敗0、全810件、354.45秒**（`package-final.log`）。skipは実keychainを読むopt-in試験4件と、implにreview専用記録試験を適用しない1件。DB試験は未実行（本作業はDBを使用しない）。
専用CLI/関数試験は39件（出力上限65535/65536/65537 bytesの境界を追加、初回36件は45.68秒で成功）、全てfake sender/ghと一時stateを使用。専用39件は51.81秒で成功、別session worker後始末の単体確認は0.53秒（`routing-final-current.log`・`detached-final.log`）。最終の終了状態と警告の日本語表示もパッケージ全体実行で確認した。
既存試験もユーザーの実adapterを実行しないよう、`tests/conftest.py`のautouse fixtureで不存在adapterを指定する。
実部品との接続は、前身のadapterに存在しない記録パスを渡し、`would_block / A / その他の判定理由`を得て正常終了した。
この手動確認は試験件数に足していない（`real-adapter.log`）。

探索した入力クラス: 正常・五段の停止・非0・成功JSONと非0の矛盾・壊れたJSON・null/配列/欠落・数値bool・段の矛盾・出力上限65535/65536/65537 bytes・部品なし/ディレクトリ・空/空白/日本語記録パス・別PJ/両種別・締切未満/等号/超過・孫のstdout保持・既存行/同時追記/書込不能・公開前予約・既存ゲート拒否。表に全試験名を対応づけた。
判定の締切は30秒で、超過時はSIGINTで後始末を最大0.2秒待ち、残るgroupをSIGKILLする。実時間試験は固定30秒を待ち、発注継続、時間切れの1行、同じprocess groupの孫のFIFO writerが閉じたEOFを検証する。
既存adapterはworkerを別sessionへ分離するため、割込みを受けた既存adapterの後始末へ短い猶予を渡す。これを模した監督部品で、別sessionのworkerが終了したEOFを確認した。任意の部品が割込みを無視して別sessionへ逃がした子まで外側から強制終了する保証はない。

| 変異 | 分類 | 結果 |
|---|---|---|
| positive-comment | 意味不変のコメント | 緑（陽性1件、陰性に加算しない） |
| 01-stop-verdict | ①停止相当をSystemExit＋shell exitへ伝播 | 赤 |
| 02-stop-failure | ②処理失敗をSystemExit＋shell exitへ伝播 | 赤 |
| 03-no-record | ③os.writeを外して記録を消す | 赤 |
| 04-no-deadline | ④解析後の全体締切照合を無効化 | 赤 |
| 05-numeric-bool | 別種回避: boolの同一性を数値等価へ変更 | 赤 |
| 06-swap-fields | 別種回避: 対象と種別を入れ替え | 赤 |
| 07-leak-reason | 別種回避: 分類を生理由へ置換 | 赤 |
| 08-disable-test | verdict検査を無効化して偽のwould_blockを返す | 段との独立整合検査で赤 |
| 09-no-worker-cleanup | 締切時の割込みを無効化、別session workerを残す | EOF確認が赤、試験のfinallyで子を回収 |

委譲は行っていない。①〜④の計画と型が異なる回避を05〜07で実際に適用した。
各変異の`invariant.diff.log`が(a)壊した差分、`landing.log`が(b)変更行の実行trace。
`execution.log`に実行argvとpytest結果、`results.log`に件別の終了値・実行行数を保存。
陽性も実行行を記録して緑を確認。全て隔離した写しに適用し、写しを元バイト列へ復元して削除、作業場所の3ファイルのSHA256一致を確認した。

制約: 個別指示がcommitを禁止しているので、共通雛形の「commit済み状態から」は満たしていない。
代わりにHEADと未commit版のSHA256を`mutations/baseline.log`へ固定し、復元を`restoration.log`へ保存した。
最終`git diff`は意図した実装差分が残るため空にはならない。変異差分が残っていないことをバイト比較で検証した。
初回の変異起動はPythonの探索パスと、写しから祖先repoの名義宣言を拾う問題で中断。
探索パスを維持し、GIT_CEILING_DIRECTORIESで写しの祖先探索を止めてから全件やり直した。中断した試行は件数に含めていない。

再現コマンド全文（cwdは本作業場所、実LLM/実ghは呼ばない）:

```sh
python3 -m pytest tests -q > .tmp/review-routing-warn/package-final.log 2>&1
python3 -m pytest tests/test_routing_warn.py -q > .tmp/review-routing-warn/routing-final-current.log 2>&1
python3 tests/check_routing_warn_mutations.py > .tmp/review-routing-warn/mutations-final.log 2>&1
git diff --check > .tmp/review-routing-warn/diff-check.log 2>&1
```

# 呼出し元と環境

`git grep --no-index -n -E 'routing_warn|routing-warn|CODEX_REVIEW_ADAPTER|REVIEW_GATE_RECORD' -- bin/codex-review lib/routing_warn.py tests/test_routing_warn.py tests/check_routing_warn_mutations.py tests/conftest.py README.md docs/design/review-routing-warn-test-design.md`
を全列挙として`callers-final.log`へ保存した（新規未追跡ファイルも含む）。
製品の新helper呼出し元は`bin/codex-review`の1か所のみ。`observe`はCLI mainと専用試験、`evaluate`はobserveと専用試験、`classify`はevaluateと専用試験から呼ぶ。
`git grep --no-index -n -E 'BUDGET_SECONDS|MAX_OUTPUT|STAGES|classify|evaluate|observe' -- lib/routing_warn.py tests/test_routing_warn.py tests/check_routing_warn_mutations.py`の全参照を`function-callers.log`に保存。定数・各呼出しを専用試験と全体試験で検証する。
CLI、既存preview/model/images/round-gate等はパッケージ全体で検証済み。予約の順序は専用shim試験で検証した。
既存A/Cの本番GitHubや公開前裁定そのものの意味判定を再認定する試験ではない。
READMEの旧「D未実装」を警告接続済みへ更新し、計数と戻し方を追記した。
記載した集計コマンドを一時stateで実行し1件を集計、接続2行をメモリ上で削除するとHEADのCLIとバイト一致することを確認（`readme-count.log`・`rollback.log`）。

| 環境 | 経路・設定・データの違い |
|---|---|
| dev | 今回の接続/読取/書込なし。ローカル発注口だけが対象 |
| stg | 同上 |
| prod | 同上。口座682251233834へ触れていない |

環境別の違いは無し。PJ別にはadapterの契約/登録不足の判定が異なり得るが、全て警告として通す。

# 引渡し

指定の外部queueディレクトリは書込範囲外で、今回の個別指示も「作業場所の外は読むだけ」。
選択肢は頭による移送か作業場所内の控え。既定案で`_work/notes/codex-queue/refactor-{result,next}-review-routing-warn.md`へ保存した。
頭が必要な確認とcommitを行い、結果控えを指定先へ移す。commit済み起点での変異が必須なら、その後に同コマンドを再実行する。
頭が後からレビューを出す指示に従い、この窓ではレビューを行っていない。停止型への昇格判断や記録自動生成器の追加は範囲外。

最終確認: `git diff --check`成功。未commitの意図した差分のみで、変異の固定起点と製品/試験3ファイルのSHA256が一致。`final-restoration.log`・`final-status.log`参照。
