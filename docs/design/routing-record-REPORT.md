記録の自動作成: 試験 848件成功／変異 陰性8件赤・陽性1件緑・生存0件／影響 37件中 旧理由が消えた件数未測定・全段通過件数未測定・未実行37件

# routing-record-impl2 の結果

生成・接続・試験・変異まで実施。**終わりの条件は未達**（当時の正本本文と作業木の固定資料がなく37件比較は再現できない）。実発注・実GitHub書込・LLM呼出し・AWS/DB接続・外部部品の変更・レビューは行っていない。
HEAD は `6136edc097524110bc8fba7784d97e982c36f85e` のまま。commit試行はPreToolUseの名義確認に拒否された（期待ghアカウントtodoroki-godai、現在matsukaze-minden）。アカウント切替・hook迂回・再試行はせず、頭がcommitするため変更を残した。git addも実行前に拒否された。

## 読んだもの

- 段取り表の該当行: 無し（依頼の欄が空）。今回の作業1〜6と課題45のround 0を対象とした。
- 本人の決定: 今回の依頼にある2026-11-15 18:25 JSTの技術判断4件。`gh issue view 45 -R todoroki-godai/codex-watch` を読取実行し、OPENと完成条件を確認した。出所は調整役の中継であり追加承認を推定しない。
- 見本HTML: 無し（欄が空、CLIの変更で画面変更なし）。
- 前身の設計と巡の履歴: `docs/design/routing-record.md` 全体、`~/.codex-watch/routing-record-d1-20261115-181705-86245.report`（Should 4件）、課題45の巡の履歴。
- 実装参照: `bin/codex-review`、`lib/routing_warn.py`、`lib/round_gate.py`、`lib/history_backfill.py`、`tests/test_routing_warn.py`。履歴節・ID契約のため既存`lib/prerelease.py`も参照した。
- 部品: `/Users/matsukaze-takashi/.claude/_wt.noindex/review-gate-parts/skills/review-gate/{route.mjs,adapter.py,routing.md}`。同じ部品のlimits.jsonとroute.test.mjsも契約確認に読んだ。すべて読むだけ。
- 影響資料: `/Users/matsukaze-takashi/updater/updater-index/_wt.noindex/review-routing-d/_work/notes/review-routing/activation/{REPORT-d.md,impact-d.json,impact-d.py}`。読むだけ。
- 試験スキル: `/Users/matsukaze-takashi/updater/updater-index/_wt.noindex/2023-impl/.claude/skills/test-design/SKILL.md`。入力区分表は`routing-record-test-design.md`へ試験の前に作成した。commit形式には`/Users/matsukaze-takashi/.agents/skills/commit/SKILL.md`を使用。今回の明示許可に従ってcommit試行した。

## 実装と欠落の扱い

`routing_record.py`を既存の警告プロセス内から呼ぶ。正本取得は既存`gh_fetch_body`、履歴のID補完は既存`history_backfill.backfill`、履歴節は既存`section`、HEADは既存`git_head_sha`、対象と同一性は部品のエクスポート`collectChanges/contentIdentity`を再利用した。巡数ゲート・予約再確認・警告・送り手の順を保持した。
構造化行は行頭`routing-record:`、JSON配列・JSON文字列（単一の非空トークンも可）を受ける。重複キーは項目全体を欠落、正本で無効な項目を依頼文で救済しない。正本との食い違いは固定分類「正本と依頼文の項目不一致」。作れないchecks・解除証跡・報告完了を追加せず、greensは[]、入力トークンは未測定理由を残す。
履歴は正本の出現順で巡番号＋種別を束ね、最初の発注ID、族タグの和を作る。欠けた巡・曖昧な照合・stateだけの履歴・現在IDとの衝突はmissing印。既存stateには受領結果・指摘族・対象別ハッシュが無いため、ファイルや報告の存在から受領を推測せずpendingのまま、whole-worktreeのcontent_hashも流用しない。初巡タグinitialは正本取得成功・履歴が完全に空・前身[]明示のときだけ。明示family_tagsがあればそれを使う。履歴の不足をnoneに変換しない。
一時記録は監督側でmkdtemp、0700と所有者確認、0600・O_EXCL、O_NOFOLLOW、通常ファイル・所有者・リンク数の確認を行う。生成側には専用パスを渡し、監督側のfinallyで自前ファイルをディレクトリFD相対で削除する。親が差し替えられた場合は置換先を削除しない（移動された元の空ディレクトリの名前は追跡しない）。外部指定は空文字を含め保持し上書き・削除しない。
生成・判定は監督開始時の30秒を共有する。生成時間を判定から引き、判定を0.25秒、監督待ちを0.05秒早く終了させて後始末時間を残す。記録open/write・stderrが詰まる場合も監督が打ち切る。互換性のため旧5引数APIの監督は従来の31秒。例外の本文・依頼文・部品の生理由はログへ出さず分類する。

## 試験

最初に正常通し試験を書き、生成器未実装の収集エラーを記録してから実装した。生成器の最終試験は30件成功（`record-tests.log`）。実部品のadapter/routeを呼び、生成JSONの全段通過とcode/greens欠落での停止相当、追加・変更・削除・未追跡の同一性一致を確認した。実CLIから記録が渡る通し、外部指定、並行2観測、親とファイルのリンク差替え、読込・書込失敗、時間切れと回収も含む。
警告＋生成の修正途中の確認は76件成功・長時間5件除外（`targeted-final.log`）。これを全体成功数としては扱わない。最初の全体実行は13件失敗・829件成功・5件skip（修正中の版、`full-tests.log`）。git不在時の既存Indeterminate例外を分類しきれていなかったため修正し、実例外型とgit不在の試験を追加した。origin/mainで同じ試験は測っておらず「前からある赤」とは扱わない。
2回目の全体は847件成功・1件失敗・5件skip（`full-before-timeout-assertion.log`）。失敗はtest_dispatch_timeoutの旧「理由1件だけ」の期待で、時間切れに加えて生成不足の分類を残す動作を反映できていなかった。先頭の時間切れと追加分類の許可集合を明示して修正した。最終のパッケージ全体 `python3 -m pytest tests -q` は848件成功・5件skip・失敗0、432.07秒（`final-full-tests.log`）。予約維持・入口拒否も生成付きで成功した。skipは明示opt-inの実gh/keychain試験4件と、起動口の対象外1件。実DB試験は対象外・未実行。テストは一時git・偽gh・偽送り手だけを使い、実adapter判定は読取専用で実発注しない。

## 変異と復元

commitが拒否されたため、許可どおり隔離コピーへ変異した。HEADとファイル別SHA256を`mutations/baseline.log`へ固定し、各変異の差分を`N*.diff.log`、実行行の独立sys.settrace証跡を`N*.executed.log`、実pytestの出力を`N*.test.log`に分離した。変更した行の実行と期待した赤/緑をスクリプトが機械で要求し、元ファイル全件のSHA256一致も確認する。結果は`mutations/results.log`。ログはすべて`.tmp/routing-record/`下、commit対象外。

| 変異 | 守る条件 | 結果 |
|---|---|---|
| N1 ①履歴を空にする | 欠落履歴を省かない | 赤・実行行確認 |
| N2 ②whole-worktreeハッシュへ置換 | 部品と同じ対象別同一性 | 赤・実行行確認 |
| N3 ③系列と前身を入替 | 型と意味を保持 | 赤・実行行確認 |
| N4 ④入力検査を常時成功 | 不正形・空白・重複を欠落にする | 赤・実行行確認 |
| N5 別種1: 正本重複を依頼文で救済 | 正本優先と欠落を保持 | 赤・実行行確認 |
| N6 別種2: リンクを追う | 外部ファイルを書き換えない | 赤・実行行確認 |
| N7 別種3: 外部指定の記録を削除 | 自前の記録だけを回収 | 赤・実行行確認 |
| N8 未追跡対象を省く | 対象全件 | 赤・実行行確認 |
| P1 boolの等価表現へ置換 | 意味を保持 | 緑・実行行確認 |

初回N6はリンク先0644の権限検査が代わりに止め、生存した。リンク先を0600へしてリンク検査そのものを踏むようにし、最終は8陰性赤・1陽性緑・生存0。初回は`N6-initial-survivor.log`と`mutations-initial.log`へ残した。探索した入力クラスは区分表の正本/構造化/履歴/対象/種別/外部記録/時刻/権限/合図。変換は削除、別レシピ、入替、常時成功、正本fallback、リンク追随、外部消去、対象の部分集合、等価bool。陽性は陰性に混ぜない。
再現コマンド全文（cwdは本作業場所、Python3.14.7 / Node v24.22.1 / Git2.50.1）:

```sh
cd /Users/matsukaze-takashi/matsukaze-utils/codex-watch/_wt.noindex/routing-record
python3 -m pytest tests -q > .tmp/routing-record/final-full-tests.log 2>&1
python3 tests/check_routing_record_mutations.py > .tmp/routing-record/mutations-final.log 2>&1
git diff --check
```

部品の固定hashは`source-versions.log`（route.mjs SHA256 `a1c0d3cb272bf28fc21313cdc85271b0c5f126cfb5edfe5c8dd7af4fa1a56909`）。変異終了時は元ファイルSHA256一致。commitできないためgit diffは実装差分が残り、空とは主張しない。

## 37件の影響

当時の固定集計JSON（2026-11-15T01:00:03+00:00）のSHA256は`411df57733c75bb007756ee71fd9bd338a96c85edf71862070ca852e0319a02a`。OPEN37件の対象、旧判定、本文hash、許可されたstate7項目は保存されているが、正本本文そのもの・当時の作業木スナップショットは無い。32件の系列/前身欠落、5件の作業場所消失という旧結果は参照できる。しかし新生成へ渡す同一の入力が無いため、新旧同route比較は**未実行37件**。旧理由解消数・全段通過数は未測定であり0件と数えない。
選択肢は当時の原資料を復元して比較／現在を新しい基準時刻にして別測定。既定案は前者を次回候補へ残し、今回の37件と現在を混ぜない。再現可能性の検査コマンド全文は以下（結果`impact.log`、外部は読取のみ）:

```sh
python3 - <<'PY'
import hashlib,json
from pathlib import Path
p=Path('/Users/matsukaze-takashi/updater/updater-index/_wt.noindex/review-routing-d/_work/notes/review-routing/activation/impact-d.json')
d=json.loads(p.read_text()); rows=[x for x in d['objects'] if x['state']=='OPEN']
assert len(rows)==37 and all('body' not in x for x in rows)
print(hashlib.sha256(p.read_bytes()).hexdigest(), '比較未実行',len(rows),'件: 本文・当時の作業木なし')
PY
```

## 7段・呼出し元

追加前の `git grep -n -E 'REVIEW_GATE_RECORD|collectChanges|contentIdentity|routing-record' -- bin lib tests README.md` は3行（`reuse.log`）。記録引数の既存受渡しと既存試験だけだった。機能が全て無いとは言わず、履歴・取得・同一性の既存部品を再利用した。

| 項目 | 止めた段と理由 |
|---|---|
| 生成JSONと接続 | ㋐明示依頼、㋑既存警告と取得/履歴/部品を再利用、統合のみ㋖最小コード |
| 一時記録の所有・安全な回収 | ㋒tempfile/os/fd/contextmanager、外部指定優先の明示要件 |
| 構造化行・欠落印 | ㋒re/json、㋖正本競合と束ねの必要な統合 |
| 総時間・打切り | ㋑既存の監督・deadline、signal/subprocess標準機能を再利用 |
| 試験と変異・報告 | ㋐明示依頼、㋑既存fake_bin・pytest、㋒隔離コピーとtrace |
| 新台帳・サービス・依存 | ㋐需要も依頼も無いため作らない |

変更関数/値の全呼出し箇所は `git grep -n -E 'routing_warn|evaluate\(|observe\(' -- bin lib tests README.md` を`callers-final.log`へ保存。未追跡の新規ファイルは `git grep --no-index -n -E 'routing_warn|rw\.(evaluate|observe|run_bounded)|rr\.|def (generate|identity|history|structured|record_path|write_record|valid|present|declared_keys|checked_parent)' lib/routing_record.py tests/test_routing_record.py tests/check_routing_record_mutations.py` を`callers-new.log`へ保存した。
`evaluate`はobserveと既存/新試験、`observe`はCLI mainと既存/新試験、`run_bounded`はCLI mainと監督/並行試験。新規のgenerate/write_recordはobserve、record_pathはrun_bounded、identity/history/structured/declared_keysはgenerate、valid/presentは構造化/履歴、checked_parentは一時記録から呼ぶ。それぞれ正常・欠落・異常と旧5引数互換を確認。CLI→生成→実adapter、既存の予約維持・入口拒否も試験に含めた。定数BUDGET_SECONDSや部品の関数定義・設定は変更していない。

| 環境 | 経路・設定・データの差 |
|---|---|
| dev | 接続・読書きなし。処理は手元の正本/state/git/部品のみ |
| stg | 同上 |
| prod | 同上（AWS/DB・口座682251233834に触れない） |

今回の変更に環境別分岐・設定差は無し。実環境のデータ差の調査はしていない。

## 次回とキュー

共有先 `/Users/matsukaze-takashi/updater/updater-index/_work/notes/codex-queue/` は書込許可範囲外。指定2ファイルは作業場所内の `_work/notes/codex-queue/` へ保存する。次回は頭によるcommit、当時の入力資料の復元可否の判断と比較測定。独立レビューは今回の指示どおり頭の手番であり実施していない。

=== CODEX QUEUE DONE ===

## routing-record-fix1（2026-11-15、レビューc1のMust/Should修正）

基点HEADは `4777982ab387c305cebc75821ed710093a30f33c`。今回の個別指示どおりcommitは試行せず変更を残す（名義hookで拒否される既知条件、頭がcommitする）。枝・アカウント操作、LLM呼出し、レビュー、実発注、本物のstateへの書込はしていない。部品・点数・設定は変更していない。

### 読んだもの・参照が無い欄

- 段取り表の該当行: 無し（依頼の欄が空）。選択肢は追加参照を待つ／今回のMust/Shouldだけを直す。個別指示の既定案として後者で進めた。
- 本人の決定の出所: 今回の依頼の受領①〜③と作業1〜5。追加の本人判断は推定していない。
- 見本HTML: 無し（CLI処理で画面の変更なし）。
- 前身の設計と巡の履歴: `docs/design/routing-record.md`、本報告の既存節、`docs/design/routing-record-test-design.md`、指定レビュー `~/.codex-watch/routing-record-c1-20261115-185706-49676.report`。レビューのread_shaは上記HEAD、対象内容hashは依頼の `e4e3a07742266d6d445777432434aaa8513e9081cabdbb8f75c645ead1b13f8c` と一致する記載を確認。レビュー全体ファイルのSHA256は `source-versions.log` に別記（対象内容hashとは別）。
- 実装参照: `lib/routing_record.py`、`lib/routing_warn.py`、`tests/test_routing_record.py`、`tests/check_routing_record_mutations.py`、旧入口互換確認の `tests/test_routing_warn.py`。
- test-design: 作業場所の `.claude/skills/test-design/` は無し。既存報告が指す `/Users/matsukaze-takashi/updater/updater-index/_wt.noindex/2023-impl/.claude/skills/test-design/SKILL.md` を読み、試験追加前に既存区分表へfix1節を追記した。

### 修正したことと限界

`record_path` は作成したディレクトリFD、ファイルのst_dev/st_inoを保持する `OwnedRecord`（既存の文字列パスと互換）を返す。元ファイルFDも回収まで保持し、削除後のinode再利用を防ぐ。監督から子への `pass_fds` と引数で同じディレクトリFDとファイル同一性を渡す。`write_record` は保持FD相対で開き、元のinode・所有者・0600・通常ファイル・リンク数1を確認してから切り詰める。親パスの0700・所有者・inodeも保持FDの対象と照合し、通常ディレクトリへの置換も拒否する。
`observe` はadapter呼出し直前・直後に同じ照合を行う。読込側の検査openも保持FD相対・O_NOFOLLOWで行い、失敗は固定分類「処理失敗」に倒す。明示された外部記録と旧5引数APIは従来どおり。書込後のリンク・別ファイル・通常ディレクトリ置換は判定へ渡す前に拒否し、判定中に残った置換もpassを破棄する。

**残る範囲:** 部品adapterがパスを開く契約は変更していない。直前照合からadapterのopenまでの間、およびadapterが開いてから直後照合までに置換して元へ戻す競合は防ぎきれない。照合後に置換された対象をadapterが一時的に読む可能性は残る。同inodeへの内容変更もinode比較だけでは検出しない。外部指定パスは今回作成物ではないためこの所有照合の対象外。完全に閉じるには部品側のFD入力等の別契約が必要で、今回の範囲では追加しない。
本人はこの競合を既知の限界として認めた（調整役 main-index 経由、2026-11-15 19:17:10 JST受領）。

構造化行は共通 `fields` でJSON引用符と配列（オブジェクトも含む）の深さを追い、文字列内の `キー=` を境界にも宣言キーにも数えない。未閉鎖引用符・配列を裸トークンとして救済しない。レビュー例、エスケープ引用符、配列内の偽キー、未閉鎖値を固定した。

### 7段と呼出し元

追加前の検索全文: `git grep -n -E 'record_path|write_record|checked_parent|declared_keys|structured\(|_run_bounded\(|st_ino|dir_fd' -- lib tests`。35行を `.tmp/routing-record-fix1/reuse.log` に保存。既存一時記録・JSON検査・監督・FD回収を再利用した。

| 項目 | 止めた段と理由 |
|---|---|
| 対象保持・照合・継承 | ㋐Mustの明示依頼、㋑既存record_path/write_record/監督、㋒os.fstat・dir_fd・pass_fdsとstrで足りる |
| 構造化項目境界・未閉鎖値 | ㋐Shouldの明示依頼、㋑既存structured/declared_keysを共通化、㋒re/jsonで足りる |
| 試験・変異 | ㋐明示依頼、㋑既存pytest/隔離コピー/traceを再利用、㋒標準ライブラリで証跡を残す |
| 文書・キュー | ㋐明示依頼、㋑既存設計・報告へ追記 |
| 新しい依存・サービス・台帳 | ㋐今回不要なので作らない |

全呼出し元検索: `git grep -n -E 'fields\(|OwnedRecord|check_record|record_path|write_record|declared_keys|structured\(|_run_bounded\(|rw.observe\(' -- lib tests`（72行、`callers.log`）。`fields`はstructured/declared_keys、両者はgenerate。`OwnedRecord`はrecord_pathとobserveの子側復元、型判定はobserve/_run_bounded。`check_record`はwrite_record・自身のFD読込・observeの前後。`record_path`はrun_bounded、`write_record`はobserve、`_run_bounded`はrun_bounded。残りは記録/警告試験内の直接呼出しと変異文字列で、保存ログに全件を記載。正常通し・子FD継承・並行・回収・外部指定・旧入口・異常分類を既存/追加試験で確認した。

| 環境 | 経路・設定・データの差 |
|---|---|
| dev | 接続・読書きなし、実データ差は未調査 |
| stg | 接続・読書きなし、実データ差は未調査 |
| prod | 接続・読書きなし、口座682251233834へ未接触 |

今回変更したコードに環境ごとの差は無し。全試験は一時データ・偽gh・偽送り手を使い、部品は読取判定のみ。実DB試験は対象外・未実行。

### 変異・再現

`.tmp/routing-record-fix1/` に全検証出力を`.log`で保存。陰性15件赤、陽性1件緑（記録試験48件成功）、生存0件。F1〜F4は今回指定①inode比較削除、②パス再open、③読込前照合削除、④空白境界の分割へ戻す、に対応する。F2は安全検査の多重防御が残っていてもFD相対書込という要求自体を外したことを実open引数で検出する。F3は直後検査がerrorへ倒しても、adapterを呼んでしまったことを検出する。
追加の別種はF5通常ディレクトリ照合削除、F6読込後照合削除、F7未閉鎖値の裸値救済、F8文字列内の偽キー宣言。従来のN1履歴省略、N2別hash、N3系列/前身入替、N4常時valid、N5正本fallback、N7外部消去、N8対象省略も再実行した。従来N6のO_NOFOLLOW単独削除は新しいinode照合で拒否できるため今回の欠陥変異から外し、リンク置換自体は前後検査の試験で引き続き確認する。P1は等価なbool表現への書換えで、陰性に混ぜていない。
探索入力クラス: 元inode/別inode、元親/リンク親/通常別親、書込前/書込後・読込前/読込中、空/外部記録、JSON文字列/配列/escape/未閉鎖/偽キー、既存履歴・対象同一性。変換: 条件削除、パス再open、境界の退行、入力救済、偽宣言、項目省略、別レシピ、入替、常時成功、等価表現。
各隔離コピーについて、置換対象が1箇所であること・非空差分・変換前後文字列の一致を機械で要求し、仕様を壊す指定差分を `mutations/*.diff.log` へ保存。別のsys.settraceで変更行の実行を `*.executed.log` へ保存し、両方の存在とpytestの期待終了値を機械で要求する。pytest結果は `*.test.log`、一覧は`results.log`。不変条件の根拠は上の区分表とF1〜F8の固定変換であり、任意差分の意味を一般判定する仕組みは追加しない。原本は全件SHA256一致（`restored.log`）。HEADは変えておらず、git diffには依頼どおり実装・試験・文書の変更が残る。変異差分は原本に残っていない。

再現コマンド全文（cwdと基点HEADを固定、変更後ファイルのSHA256は`source-versions.log`、隔離原本全件は`mutations/baseline.log`）:

```sh
cd /Users/matsukaze-takashi/matsukaze-utils/codex-watch/_wt.noindex/routing-record
python3 -m pytest tests/test_routing_record.py tests/test_routing_warn.py -q > .tmp/routing-record-fix1/targeted.log 2>&1
python3 tests/check_routing_record_mutations.py > .tmp/routing-record-fix1/mutations.log 2>&1
python3 -m pytest tests -q > .tmp/routing-record-fix1/full-tests.log 2>&1
git diff --check > .tmp/routing-record-fix1/diff-check.log 2>&1
```

Python3.14.7 / Node v24.22.1 / Git2.50.1。部品route.mjs SHA256 `a1c0d3cb272bf28fc21313cdc85271b0c5f126cfb5edfe5c8dd7af4fa1a56909`、adapter.py SHA256 `44ccbf61a0d4a5c6c5b300c5459463ae788b8e03cf5e4848ea3824097b917d63`。

### 最終試験と引継ぎ

記録＋警告の対象試験は `100 passed in 154.83s`（`targeted.log`）。パッケージ全体 `python3 -m pytest tests -q` は **866 passed, 5 skipped in 463.60s**（`full-tests.log`）、失敗0。5 skipは既存のopt-in実gh/keychainと対象外起動口で、成功件数へ含めない。新しい試験18件を追加した。origin/mainでの比較試験は未実行であり、「前からある赤」という判断はしていない。`git diff --check` 成功。実装・試験・adapter・レビューのSHA256が検証版と同じことを最後に再確認した（`source-final-check.log`）。
指定共有キュー `/Users/matsukaze-takashi/updater/updater-index/_work/notes/codex-queue/` はsandbox書込許可範囲外で、今回の承認方針では拡張もできない。そこへの書込は試さず、指定2ファイルを作業場所の `_work/notes/codex-queue/` に保存した。頭が共有先へ転記し、変更をcommitして独立レビューへ渡す。次の実装修正依頼は現時点で無し（nextファイルは「なし」）。全体試験緑・今回実施の変異生存0という終わりの条件は満たした。adapter契約に由来する競合窓の制約は上記のとおり残る。

=== CODEX QUEUE DONE ===
