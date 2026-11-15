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
