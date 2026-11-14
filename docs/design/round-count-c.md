C の設計: 承認Nを同種実績で裏付けられる場合は種別別、それ以外は旧本体の数え方を使う／新たに停止0件は見込み・未実測

更新: 2026-11-15 JST。run: `round-count-c-design4`。対象: #38 C・#37。読取基点 `d504d4a`。
作業場所: `/Users/matsukaze-takashi/matsukaze-utils/codex-watch/_wt.noindex/round-count-c`、枝 `feat/round-count-c`。design3の読取基点は `2f6e92d`。
本書は設計案。製品コード・試験・設定・実台帳は変更しない。別系統レビュー済み・実装着手可とは扱わない。

## 1. 読んだもの・縮める根拠

| 必須参照 | 出所・今回の扱い |
|---|---|
| 段取り表の該当行（パス:行） | 無し（今回の割当てはT番号ではなく #38 C と #37）。別PJの段取り表は更新しない |
| 本人の決定の出所 | 本人の回答「裏付けなしは今の数え方で (Recommended)」、調整役 main-index 経由、2026-11-15 08:46:28 JST 受領。#37の承認節。原文は再取得せず、今回の明示依頼を出所とする |
| 見本HTML | 無し（画面変更なし） |
| 前身の設計・巡（design3当時） | `e7d8cf1:docs/design/round-count-c.md`、特に§1.2の実測。`docs/design/review-complete.md` §3、`docs/review-preface-kind-rounds.md`。`2f6e92d:docs/design/round-count-c.md` と指定レビュー `~/.codex-watch/round-count-c-d1-20261115-080959-34508.report` を読んだ。レビューのread_shaは2f6e92d、指定本文hashはb731e4d9cdaaced494d028482c4e44fc314a7ace9fca50bffd82b174c7816002。今回はdesign2の承認下限規則を差し替える |
| 指定実装（design3当時の参照箇所。design4では `lib/round_gate.py` 全体を確認） | `lib/round_gate.py:279-297,444-489,614-674,688-729,1246-1302,1406-1441`、`lib/prerelease.py:41-98,148-178`（以降の固定上限・版照合も確認）、`bin/codex-review:115-123,236-239,285,341` |
| 試験設計 | 作業場所の `.claude/skills/test-design/` は無し（`git grep -l '' -- .claude/skills/test-design/` は0件）。前回の出所 `/Users/matsukaze-takashi/updater/updater-index/_wt.noindex/rev9-audit/.claude/skills/test-design/SKILL.md` を読み直して§5へ適用 |
| 既存試験・計測 | `tests/test_round_gate.py:191-269`、`tests/test_prerelease_fixA.py`、既存変異実行器のgrep参照、`.tmp/round-count-c-design2/{impact.py,impact.json}` と設計付録。旧版の結果を今回の実測へ転用しない |

以下はdesign3当時の記録。skill欠落への選択肢は「補充まで停止／前回の同じskillを読む」、既定案は後者で進めた。今回も同skillを読んだ。今回の規則は本依頼を優先する。別系統レビュー1巡は後続の受入条件として残し、他のLLMは呼ばない。

前回§1.2の実測: (a) 設計state3 HEAD＋承認cap3→コード新HEADは混算4で停止、(b) 同一HEADコード2run→新HEADは通常経路では2巡・説明文があっても通過、(c) 特例historyはその2runを2と数え、説明文では例外を投げる。今回はこの観察を根拠に縮小し、(b)の通常経路を直す対象にはしない。前回の観察を新仕様の成功試験とは呼ばない。

追加前に `git grep -n -E 'target_total_rounds|ledger_head_shas_for_target|ledger_own_round_for_predecessor|body_own_round|parse_approval_rounds|parse_total_cap|history\(' -- lib bin tests` を実施し、**57行**を今回も確認。既存filter・再帰・承認パース・特例照合・変異実行器を再利用する。「既存の道具が無い」という主張はしない。

## 2. 最小案

### 2.1 通常経路: 種別を通し、結果を1つ使う

巡の単位は既存の **同じtarget・同じ種別のdistinct HEAD**。同HEADの複数runは1巡、異なるHEADは別巡。内容hash・集合・時刻から新しい単位を作らない。

- `target_total_rounds` と `ledger_own_round_for_predecessor` に今回の `kind_label` を渡し、既存 `ledger_head_shas_for_target(..., kind_label=...)` を使う。前身の再帰にも同じ種別を渡す。今回HEADが今回種別に未登録なら1加算、登録済みならdistinct数のまま。前身には加算しない。
- `kind_label` 欠落stateは既存filterどおりコード、不正種別・読取失敗は既存filterどおり停止。HEAD欠落の旧stateは既存の除外を維持し、移行機構は作らない。循環・深さ上限・本文取得失敗の停止も維持する。
- gateの `total_round` を唯一の今回巡とし、CLIの前置き・点検・stateの `round`・本文追記にその値を渡す。前置きで `ledger_own_round` を再計算しない。前身込み総巡を使うため、前身2巡＋今回1巡は全箇所3。過去HEADへの再発注でも先頭からの序数へ戻さない。
- 同一target×HEADの3本上限は別の安全策であり、現在どおり全種別の本数で判定する。通常1〜2巡、3〜5巡の承認、6以上の既存裁定経路、none/bypassの既存分岐は作り替えない。

### 2.2 種別なし承認: 裏付けに応じて使う数え方を選ぶ

**選ぶ規則は1つ:** 裏付けがあるときに限り、既存「巡Nの人間承認」と「総上限: M」を、設計・コード両カウンタへの承認の存在と固定capとして適用する。Nを両カウンタの消化数にしない。裏付け不能なら以下の旧本体への切替を優先する。capの既存パース（複数は最大値）を維持し、3〜5巡の `decide` を再利用する。承認行の真正性や新たな本人決定を機械が作るものではない。

| 条件 | 期待 |
|---|---|
| 設計3 HEAD（round3は設計のみ）＋種別なし承認「巡3・総上限3」、コード初回新HEAD | 設計3を保持しコード1で通過。承認はコード1の必須条件ではない |
| コード3巡目、承認行なし | 停止。capだけあっても承認にはならない |
| 設計4巡目、上のcap3あり | 停止 |
| コード3巡目、上の承認・cap3が残り、round3の候補は設計のみ | 両カウンタへ適用する互換規則により通過。種別別の本人承認が新たにあったという意味ではない |

**数え方の選択:** 承認の許可/capは両種別へ適用する。対象と前身の各承認Nについて、次の条件で帰属と同種実績を確認する。

1. 今回targetと各前身ノードの本文で `parse_approval_rounds` が返す**各N**を検査する（最大Nだけに縮めない）。そのノードと同じ `review_target` の既存stateから、発注時に保存した `round=N` の行を探し、その `kind_label` の集合を得る。同種の複数runは競合でない。kind欠落は既存互換どおりコード。種別不正・読取失敗は既存の入力エラーとして停止し、round欠落/正整数でない値、対応候補のHEAD欠落は裏付け不能として旧本体へ戻す。roundの文字列はASCII十進正整数に限り、別targetのstateを候補にしない。
2. 候補種別がちょうど1つならその種別へNを帰属する。0種別または2種別は帰属不能。時刻の新旧、今回kind、全種別合計、本文の説明から補わない。保存済みroundは旧来の混算値を含み得るので、帰属の手掛かりに限定する。
3. 帰属先種別の、同ノードと前身の**保存済みdistinct HEAD**だけを既存再帰/filterで数える。この検査には今回の未発注HEADを足さない。各Nの帰属が一意で同種実績がN以上なら裏付けあり。前身も個別に検査し、子孫の余剰や他種別で不足を埋めない。

全Nが裏付けられた場合は§2.1の今回種別の総巡を判定・表示・保存に使う。1つでも帰属不能または同種実績不足なら、発注全体を旧本体 `61b8fde:lib/round_gate.py` の計算に戻し、各ノードで全種別のdistinct HEADと前身の総巡を合算し、その値と当該本文の承認N最大値の大きい方を採る。rootの未登録HEAD加算、前身ごとの下限、既存 `decide`・特例・同HEAD本数上限を旧本体どおり適用し、その値を判定・表示・保存に一貫して使う。種別別の値と混ぜない。裏付けなし自体は停止理由にしない。state読取失敗、不正種別等の既存の信頼境界のエラーは握りつぶさない。承認候補のround欠落・不正やHEAD欠落は帰属の裏付けに使えず、旧計算への切替対象とするが、既存の独立した入力検査のエラーは維持する。共有祖先visitedの既存挙動は変更しない。

#37は、設計3 HEADの既存stateに保存済みround3・kind設計があり、round3がコードにも存在しない入力なら、N3を設計へ帰属し設計実績3で裏付ける。コードのpendingは1で通過する。記録欠落・種別競合なら旧本体の値で判定する。

レビュー再現のコード2 HEAD＋設計3 HEAD＋N5/cap5＋コード新HEADは、候補round5がコードでも設計でも同種実績不足、候補なし/競合なら帰属不能。旧本体の混算は今回込み6、承認下限5との最大も6であり、既存の6巡以上の裁定なしなら停止する。旧本体で止まる発注を通さない。

コード3保存後に設計round3とコードround3が共存すれば帰属は競合し、同HEAD再発注でも旧本体の数え方に戻す。

採らなかった案: 帰属不能・同種実績不足を停止するdesign3案は、実測でOPENの6件を新たに停止したため本人が採らなかった。Nを常に捨てる案も旧下限を失うため採らない。新台帳・種別付き承認は設けない。

### 2.3 公開前特例: 照合してから同種のHEADを数える

`prerelease.history` に今回種別を渡す。既存の節取得、dispatch_idの照合、同IDの異なる履歴行の矛盾検出、state/予約のキー重複・ID検査を残し、照合後に今回種別だけのdistinct HEADを数える。別種別の行を先に消して同IDの矛盾を隠さない。未対応の旧表行を推定で合流せず、既存のdispatch_id補完必須を維持する。

履歴節では**まずdispatch_idの有無を検査**し、ID付きの壊れた行はヘッダ・区切りに見えても拒否する。その後、IDのない空行・ヘッダ・区切り・**表以外の説明文は読み飛ばす**。一方、表のデータ行・dispatch_idを持つ行で形式が壊れているものは説明文として捨てず特例不成立。dispatch_id同士の矛盾を人間承認で特例内だけ握りつぶさない。通常経路へ特例historyを追加しない。

`parse_approval_rounds` は本文全体を検索し、説明文を読み飛ばさない。`説明例（承認ではない）: 巡3の人間承認、総上限: 3` も `[3]` と読み、`decide(3, body)` はpassになる。§2.2で選択した巡を使い、通常承認を先に評価するため特例historyには到達しない。これは現行からある承認パーサーの課題であり、Cの計数修正に承認書式の変更を混ぜないため今回は直さない。

HEADは既存stateの完全SHAを使い、本文・state・予約をdispatch_idで対応付けて同一発注を重複させない。予約には既存 `prerelease_evidence.record` のkind/head_shaがあるので再利用し、新しい予約方式は足さない。本文だけの行は完全SHAがあれば使い、短縮SHAなら同IDの既存記録等で完全SHAを一意に照合できる場合だけ使う。曖昧な短縮SHAや対応材料不足は特例不成立。旧stateの自動移行やGitHub書込みで補完しない。

`history` の実績数だけに常に1を足す方法も廃止する。今回HEADを渡す場合は既存と同じdistinct集合へ今回を入れた予測数を返し、`evaluate` はその値をgateの今回種別の総巡と照合する。同HEADへの2本目は加算せず、別HEADは1加算。stateと予約が同じIDなら1件、別IDでも同HEAD・同種なら1巡。特例は前身なしなので、種別別計数を使う場合は通常の種別別総巡と一致する。裏付け不能で旧本体に戻す場合は、特例の履歴計数・照合・最終判定も旧本体の経路を使い、種別別historyと混ぜない。

**変えない条件:** 2ファイルの既定枝blob一致、PJ実体登録、裁定ID・対象・kind・版・対象一覧の照合、巡3〜5と固定総上限、保存済み系列/固定上限の照合、blocking/前身なし、時刻・操作範囲、bypass併用禁止、送信前再照合・既存予約。§2.2で選択した巡による通常の人間承認を特例APIより先に判定する順序も維持する。固定上限照合を種別ごとに緩める変更は今回しない。

### 採らなかった大きな案

新台帳、round_id、series_idの新設、確定集合レコード、予約の通常経路への全面適用、旧state移行・全発注口統合は作らない。通常の二重計上・説明文停止は現物で再現せず、#37と特例の欠陥には既存filterとHEAD集合で足りる。トークン補完やDの振り分け配線も今回拡張しない。

## 3. 完成条件（実装時の受入条件）

1. **守る対象:** 種別別distinct HEAD、同種の前身継承、前置き/点検/state/判定の同値、3巡目の承認・固定上限。裏付け不能時は旧本体と同じ判定とし、旧本体で止まる発注を通さない。裏付けがあるとき、旧本体では停止する#37が通るのは意図した変更。特例のID照合・2blob・総上限・bypass禁止を弱めず、IDや承認文言を含まない履歴説明文だけでは止めない。
2. **信頼境界:** CLI種別、state/予約、GitHub本文・前身、特例の登録/規則/裁定・対象版。既存入力検査と読取失敗の停止を残す。旧承認の裏付け不足を新規1巡へ落とさない。
3. **対象外:** 新しい巡単位/台帳/移行/通常予約、D接続、トークン補完刷新、bypass権限刷新、AWS/DB・dev/stg/prod、レビュー本数の自動承認。
4. **blocking:** 裏付けありの場合の種別混算・前身filter漏れ・表示と保存の不一致、裏付け不能時に旧本体で停止する発注の送信、特例の過少/過大計数・説明文停止、安全条件の迂回。別系統設計レビュー1巡を受け、[Must]が残る間は製品実装へ着手しない。今回そのレビューは未実施。
5. **検証:** §5の正常通し→境界/既存安全策→全パッケージ→変異。欠陥を決定論チェックへ翻訳する。有効な変異の生存が1件でもあれば実装完了にしない。設計commitだけで実装済みとは扱わない。

## 4. 影響確認（design3の旧案の実測とdesign4の見込み）

以下は停止を選んだ旧案の実測であり、今回の案の実測ではない。今回の見込みは**新たに止まる0件**。これは未検証で、裏付けありの種別別判定や他の安全条件も含め実測で確かめる。実装後、`docs/design/round-count-c-REPORT.md` の同じ7日間の基準時刻・対象選択・現HEAD/新HEAD・通常経路を使い、同じ `.tmp/impact_c.py` の非送信方式で旧本体 `61b8fde` と実装後の実 `run_gate` を同一の隔離state・本文・HEAD・goal-cutで比較する。取得不能とOPEN/全対象を分け、通過→停止、停止→通過、同判定、未取得を集計し、6件それぞれの旧/新判定を記録する。再取得値の変動と基点SHAを記録し、必要なら同じ固定入力で再現する。特例は別途固定fixtureと実対象の実測を区別し、発注・予約・本文更新はしない。0件と異なれば原因を調べ完了としない。

前回と同じ選択基準 **2026-11-15 07:40:52.360285 JST**（UTC `2026-11-14T22:40:52.360285+00:00`）までの7日間。今回5173 stateを読取り、期間内890・issue/pr発注84・重複排除42対象。本文取得終了は **2026-11-15 08:14:27.710245 JST**（UTC `2026-11-14T23:14:27.710245+00:00`）。OPEN33・MERGED6・CLOSED2・取得不能1。design2の5169 stateのsnapshotとは異なる。auth switchなし、実台帳は読取りのみ。

「次の1本」は期間内最新stateと同じkind、通常経路、追加env前身なし・特例裁定IDなし、現在の本文/前身を使う。現HEADは最新stateのworkdirの `git rev-parse HEAD`、消失時はPR headRefOid、次に最終state HEADの仮定。未登録の新HEAD条件も別測定。閉じた8対象も仮想発注として残し、OPENとは分けた。

前回と同じ既存 `target_total_rounds/decide/same_head_dispatch_count` とメモリ内mockで計数・再帰・最終判定を比較した。候補の承認検査だけ§2.2に差し替えた。候補の種別計数と帰属先種別の保存済み計数はいずれも既存filter/再帰を呼ぶ。3本上限を最終判定へ含む。製品ファイルを編集した実装版の結果ではない。

| 範囲・今回HEAD | 対象 | 未取得 | 通過→停止 | 停止→通過 | 確定した巡減少 | 巡・判定とも同じ | 帰属/下限で巡未確定 | レビューと同じ形 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 全対象・現HEAD | 42 | 1 | 7 | 3 | 4 | 30 | 7 | 2 |
| OPEN・現HEAD | 33 | 0 | 6 | 3 | 4 | 23 | 6 | 2 |
| 全対象・新HEAD | 42 | 1 | 5 | 4 | 4 | 30 | 7 | 1 |
| OPEN・新HEAD | 33 | 0 | 4 | 4 | 4 | 23 | 6 | 1 |

「レビューと同じ形」は、各ノードの承認のいずれかNで **今回種別の台帳総巡 < N ≤ 全種別の台帳総巡**（ともに本文下限抜き、rootだけ今回HEADを含む）を満たす対象数。前身/複数Nが該当しても1対象。現HEADは `issue:min-sys/updater-index#2015`（コード2 < N4 ≤ 全種4）、`issue:todoroki-godai/codex-watch#38`（コード3 < N4 ≤ 全種4）の2件。新HEADは#2015だけ（コード3 < N4 ≤ 全種5）。この診断条件は§2.2の安全規則には使わない。

現HEADで通過→停止のOPEN6件は `issue:min-sys/updater-index#1564,#1596,#2015,#880`、`issue:todoroki-godai/codex-watch#38`、`pr:min-sys/updater-index#2007`。閉鎖済みの追加1件は `pr:min-sys/updater-index#2043`（MERGED）。帰属先の同種実績不足が全7件にあり、#1564は過去N3/N4の帰属不能もある。新HEADでは#2015と#38は現行でも停止するため、OPENの通過→停止は残り4件。候補の帰属/下限停止自体は現/新ともOPEN6件であり、「新たに停止」と混同しない。

現HEADで通過へ変わるOPEN3件は従来どおり `issue:min-sys/updater-index#1708,#2018,#2031`。巡の照合は現/新とも全対象 **4+30+7+1=42**、OPEN **4+23+6=33**。巡増加は0。未確定の暫定巡は確定した巡減少に含めない。未取得は `pr:min-sys/docs-platform#1057`、0件や同じ扱いにしない。

**未測定:** 公開前特例を指定した次発注の最終判定。現行historyにkind/pending引数がなく、登録blob・裁定内容・版/時刻の固定も必要。通常41件の結果を特例込みへ拡張しない。実装後は固定入力の隔離コピーで旧版/実装版run_gateを呼び、通常/特例・現/新HEADを別集計する。実予約・発注・本文更新はしない。

再現: 付録を `.tmp/round-count-c-design3/impact.py` に保存し、`PYTHONDONTWRITEBYTECODE=1 python3 .tmp/round-count-c-design3/impact.py`。結果は同ディレクトリの `impact.json`、実行ログは `impact.log`。資格情報・本文全量・state全量を保存しない。本文/全期間state/workdir HEADは固定保存していないため再取得で値は変わる。JSONのdecreasesは未確定の暫定巡も含むので、本表ではmissing_approval_floorを除外した。

## 5. 試験計画（正常系を先に。今回は試験追加なし）

| 入力 | 区分・境目／置く値 | 期待 | 期待の出所 | 大きさ／試験名案 |
|---|---|---|---|---|
| 発注全体 | 設計3 HEAD・round3候補は設計のみ＋旧承認N3/cap3→コード初回新HEAD | 通過、前置き/点検/state/本文/gateがコード1 | #37・本書§2 | fake CLI通し／design3_code1 |
| コード巡と承認 | 今回2/3、承認なし・capだけ | 2可、3停止 | #37 | 関数／code3_no_approval |
| 旧承認とcap | 帰属先と保存済み実績の検査を満たす状態で両種別の今回3/4、cap3あり | 3可、4停止 | #37・§2.2の互換選択 | 関数＋CLI／legacy_cap |
| 通常上限 | 4/5/6、cap5・承認、6は裁定なし/あり | 4/5可、6は既存裁定条件を維持 | 現行の維持指定・§2.1 | 関数／limit5 |
| HEAD集合 | 同target・同種・同HEADの2run、別HEAD、過去HEADへの再発注 | 1巡/2巡、過去HEADでも現在の総巡を表示 | 今回の依頼・§2.1 | 関数＋CLI／distinct_heads |
| 種別と前身 | 設計/コード混在、同種前身2＋今回1、復帰、循環/深さ超過 | 同種3、他種不算入、既存停止維持 | #37・§2.1 | 関数＋CLI／inherit_kind |
| 承認帰属と下限 | round=Nが同種だけ/なし/両種、帰属先の保存済み同種実績がN−1/N/N+1 | 一意かつ実績≥Nだけ種別計数、他は旧本体の巡・判定を使う | 本人決定・§2.2 | 関数＋CLI／approval_floor |
| 他種別による不足隠し | コード2 HEAD・設計3 HEAD・承認N5/cap5・コード新HEAD、round5候補はコード/設計/なし/競合 | 全て旧本体の6巡として裁定なしなら停止、コード3を採用しない | レビューMustの再現入力 | 関数＋CLI／approval_floor_cross_kind |
| pendingによる不足隠し | 帰属コード、保存済みコードN−1、今回新HEADでN | 今回未発注分を裏付けに使わず旧本体の巡・判定に戻す | §2.2の消化済み下限 | 関数／approval_floor_pending |
| 旧案で新規停止した6件 | REPORT記載のOPEN6件と同形、帰属不能/同種実績不足、旧本体pass | 旧本体と同じ巡・pass、前身や複数Nを含む | 本人決定・REPORT | 関数＋gate／legacy_six |
| 承認を含む説明 | 説明例中の巡3の人間承認・総上限3、帰属/実績は有効 | parse=[3]、decide(3)=pass、通常承認が先で特例history未到達 | 現行の限界を明記・Should | 関数＋CLI／approval_prose_existing |
| 文字・欠け | 種別なし/不正/空白、state読取不能、HEADなし、round欠落/0/非ASCII数字 | kind欠落コード・不正停止。HEADなしは旧計数どおり除外、承認候補のHEAD欠落やround欠落/不正は旧計算へ戻す。独立した既存入力エラーは停止 | §2.1 | 関数／kind_compat |
| 履歴の文字 | 正しい表＋説明文、非数値の壊れた表行、dispatch_id付き壊れ行、`\|---\| <!-- dispatch_id=forged -->` とID付きヘッダ | IDなし説明文は無視、ID付き偽区切り/ヘッダを捨てず拒否して特例不成立 | 今回の依頼・§2.3 | 関数＋特例通し／history_prose |
| 特例のIDとHEAD | 同ID重複/矛盾、別種別に同ID、別ID同HEAD、state/予約重複、短縮SHA曖昧 | 矛盾拒否後に今回種別distinct HEAD、曖昧なら不成立 | ID照合維持・§2.3 | 関数＋特例通し／history_identity |
| 特例の継ぎ目 | 今回HEADが既知/未知、設計履歴混在 | 無条件+1せずgateと同じ巡 | 今回の依頼・§2.3 | 関数＋CLI／history_pending |
| 安全策・操作不能 | blob2個一致/片方不一致、cap3/超過、bypass併用、保存済cap変更 | 一致かつ既存全条件内だけ通過 | 今回の維持指定 | 既存特例通し拡張／prerelease_contract |
| 時刻・合図 | 固定時刻、未来裁定、予約後の送信前再照合不一致 | 既存時刻検査/再照合で未送信、sleepで同期しない | 既存安全策維持 | 既存fake CLI／recheck |

design3の裏付け不足で停止する期待は撤回する。各Nのいずれかが帰属不能・同種実績不足・pendingでのみ充足なら、旧本体の全種別計数と各ノードの承認下限を適用する。design3_code1/legacy_capは裏付けに必要な保存済みroundとkindをfixtureへ明記する。これは試験計画の更新で、既存製品試験の期待値は今回変更しない。

同じ側の言い換えは増やさない。DB・画面は対象外で試さない。時刻は既存特例の固定時計を使い、種別計数へ時刻条件を追加しない。正常通しから書き、表の期待を実装出力から逆算しない。既存の通常経路2run/説明文試験も残す。

| 変異区分 | 最小案への変異 | 検出する試験と着弾証跡 |
|---|---|---|
| 陽性対照 | state列挙順だけを反転 | distinct_headsが緑、意味不変diffと実行trace |
| ①守る処理を消す | 前身へのkind伝播を消す | inherit_kindが赤、再帰の実行行trace |
| ②意味を壊す | 特例をdistinct HEADからrun数へ戻す（または無条件+1） | history_identity/history_pendingが赤、計数行trace |
| ③入れ替える | CLIで設計/コードのkindを交換 | design3_code1が赤、受渡し/保存行のシェルtrace |
| ④検査自体を無効化 | 裏付けられないときに旧本体の値に戻さず種別別の値を使う | approval_floor_cross_kindの旧6巡停止期待が赤、切替分岐trace。試験をskip/0件化しても収集・skip・期待試験IDの別照合で失敗にする |

別種の回避を2件以上: (a) 他種別の表行に同dispatch_idの矛盾を隠す（入力照合の回避）、(b) 初回判定後に保存済cap/版を変えて送信前再照合を通そうとする（時間差の回避）。kindを変えるだけの変異の言い換えにしない。2blob・cap・bypassの既存安全策の決定論チェックも残す。

実装/試験をcommitした基点から作業場所内の隔離コピーへ1件ずつ変異を当てる。(a)不変条件を壊すdiffと前後hash、(b)実際に分岐が実行されたPython標準trace/シェルtraceを別証跡に残す。構文エラー・未着弾・無関係の赤は成功にしない。既存 `tests/check_prerelease_fixA_mutations.py` 等の手順を再利用し、陽性1件・①〜④各1件以上・別種回避2件を確認する。緑の有効変異があれば未完了。隔離コピーの復元/削除後、原本の `git diff` とstatusが空か確認する。reset/checkout等は使わない。

全パッケージの試験コマンド（TMPDIRの親を先に作る）:

```sh
mkdir -p .tmp/round-count-c-design3/tmp
GIT_CEILING_DIRECTORIES="$PWD" TMPDIR="$PWD/.tmp/round-count-c-design3/tmp" PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider --basetemp="$PWD/.tmp/round-count-c-design3/pytest"
```

## 6. 影響箇所と7段

design4の事前探索 `git grep -n -E 'target_total_rounds|body_own_round|parse_approval_rounds|ledger_head_shas_for_target' -- lib bin tests` は44行。今回の製品関数変更は0件。stateの既存保存元 `bin/codex-review:335,341` と種別filter `lib/round_gate.py:444-473` も読み、保存済みround/kindを再利用できることを確認した。以下は§1のgrepから得た実装時の全製品参照（試験呼出しは同じ57行のgrepで再列挙し、新署名へ照合する）。本書の行番号は読取基点の実物。

| 変更候補・製品内呼出し元 | 実装時の壊れない条件 |
|---|---|
| HEAD列挙: `round_gate.py:483,617,653` | 既存ledger_own_round互換、総巡/前身にkind。filterの読取失敗を握りつぶさない |
| 前身own: `round_gate.py:651`、総巡: `:666,1269` | 再帰に同kind、pending加算は今回のみ、循環/深さ失敗維持 |
| 本文下限/承認: `round_gate.py:296,671,697,698`、state保存元 `bin/codex-review:335,341` | 許可/capと計数分離、既存round/kindで帰属、一意でないか同種実績が不足すれば旧本体へ切替。同種実績でのみ種別別への切替を裏付け、保存書式は増やさない |
| history: `prerelease.py:178` | kind・pending HEAD受渡し、ID照合と全安全条件維持 |
| CLI: `bin/codex-review:116-125,236-239,285,341` | gate totalを前置き/点検/stateへ渡し、種別と巡の取り違えなし |
| gate結果消費: `round_gate.py:1421-1441`、本文行 `:1334-1342` | 特例再照合・予約snapshot・記録が同じ総巡を使う |

将来の範囲外候補名: 説明文も承認と読む承認パーサー、巡番号だけによるトークン補完、共有祖先visited、6巡以上裁定/bypassの権限確認。今回は名前の報告だけで、修正しない。

| 足す仕組み・章・項目 | 7段で止まる段と理由 |
|---|---|
| §1の現状・参照 | ㋐明示依頼、㋑前回実測と既存grepで止まる |
| §2.1種別別計数/共通値 | ㋑既存filter・再帰・gate JSONを使う。新カウンタ基盤なし |
| §2.2旧承認互換/旧本体への切替 | ㋑既存承認/cap・stateのround/kind_label・種別filter/再帰を再利用。㋒標準setで一意性を判定し、同種下限を検査し、裏付け不能時は旧本体の計算を利用。新記録/形式は㋐不要で作らない |
| §2.3特例 | ㋑既存ID照合・state/予約・HEAD計数を再利用、㋒標準set/辞書で足りる。別種別filter・説明文の読み飛ばしを追加し、依存は足さない |
| §3受入条件 | ㋐削減不可・明示依頼、㋑既存安全条件を維持して止まる |
| §4影響・付録 | ㋑既存関数を呼ぶ、㋒標準mock/Counter/pathlib、㋓gh読取で止まる。製品のコピー実装なし |
| §5試験/変異 | ㋐削減不可、㋑既存pytest/fake/変異手順、㋒標準traceで止まる |
| §6呼出し元・7段、§7記録/次回 | ㋐明示依頼、㋑既存git grep・試験結果の記録で止まる |
| design4: §2.2の切替と再現入力 | ㋐本人の明示決定、㋑既存state・承認parser・旧本体の計算を再利用して止まる |
| design4: §3の受入条件 | ㋐明示依頼、㋑既存の守る対象を補足して止まる |
| design4: §4の見込みと実測手順 | ㋐明示依頼、㋑REPORTの非送信比較と対象選択を再利用して止まる |
| design4: §5の入力区分・変異計画 | ㋐明示依頼、㋑既存fixture・変異手順を再利用して止まる |
| 新台帳/ID/通常予約/移行 | ㋐今回の再現欠陥に不要なので作らない |

㋓プラットフォーム・㋔導入済み依存・㋕1行・㋖最小コードまで下る新製品機構はない。信頼境界・データ消失防止・安全策・別系統レビュー1巡・[Must]残存中の着手禁止・決定論チェック・変異は削減しない。

## 7. 前回の検証・環境差・次回

以下の試験・commitに関する記録はdesign3当時の履歴であり、design4の実行結果ではない。

パッケージ全体729件を実行し、**724 passed・0 failed・5 skipped、317.53秒**。`git diff --check` は成功。ログは `.tmp/round-count-c-design3/pytest.log`。設計のみの変更で実装検査を新設していないため、今回の変異は計画のみ。新規製品試験/製品変更は0件。候補の正常/変異試験、特例込み影響、実発注、DB試験は未実行。既存試験の緑をC実装の成功とはしない。本線では測っていないので「前からある赤」とは呼ばない。

| 環境 | 経路・設定・データの違い／今回の扱い |
|---|---|
| ローカル | 共通state・GitHub本文/前身を読取り、mockで非送信比較、fakeによる既存試験 |
| dev | 巡数コードの環境別分岐は無し。接続・読取・書込なし |
| stg | 巡数コードの環境別分岐は無し。接続・書込なし |
| prod | 巡数コードの環境別分岐は無し。接続・操作なし |

指定の結果/次回ファイルの親 `/Users/matsukaze-takashi/updater/updater-index/_work/notes/codex-queue/` はsandboxの書込許可外。権限追加もできず、指定先2ファイルは未作成。選択肢は指定先への転記/作業場所内の転記用ファイル。今回の既定案は後者とし、指定先への作成が済んだとは扱わない。

commit対象は本設計文書1ファイルだけ。製品の呼出し元の変更はなく、既存関数を呼ぶ影響計測と全パッケージ試験で現行への影響を確認する。commitはPreToolUseの名義確認hookがコマンド実行前に拒否した（期待todoroki-godai、検出matsukaze-minden）。名義変更/hook迂回はせず、依頼の例外指定に従って文書差分を残す。新commit SHAは無し、読取基点は2f6e92d。依頼元がcommitする。最終diff状態は転記用resultに記録する。

次の起動用「今回の作業」:

> ## 今回の作業
> run名: round-count-c-design3-review。作業場所: `/Users/matsukaze-takashi/matsukaze-utils/codex-watch/_wt.noindex/round-count-c`（feat/round-count-c）。製品コードを変更せず、依頼元が別系統設計レビュー1巡を手配し、`docs/design/round-count-c.md` の承認帰属/同種下限・#37の保存済み記録条件・Must再現停止・OPEN影響6件/4件・偽区切り拒否の期待を確認する。この窓で他LLMは呼ばない。終わりの条件: 受領照合とMust一覧を記録し、Mustが0になるまで実装着手しない。次run名: round-count-c-impl（Must0確認後のみ）。

## 付録: design3旧案の通常経路の非送信比較（履歴・再現用）

このコードは裏付け不足で停止する旧案の比較であり、design4の実装後実測にはそのまま使わない。

標準ライブラリとgh読取りのみ。次のコードを `.tmp/round-count-c-design3/impact.py` に保存し、親ディレクトリ作成後 `PYTHONDONTWRITEBYTECODE=1 python3 .tmp/round-count-c-design3/impact.py` で実行する。既存関数の再帰/HEAD列挙/判定を呼び、候補の帰属チェックだけメモリ内で追加する。本文・資格情報・state全量は保存しない。

```python
import sys
sys.dont_write_bytecode = True
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import json, subprocess, os
sys.path.insert(0, str(Path.cwd()/'lib'))
import round_gate as rg
OUT = Path('.tmp/round-count-c-design3')
SD = Path.home()/'.codex-watch'
END = datetime.fromisoformat('2026-11-14T22:40:52.360285+00:00').timestamp()
records = {}
selected = {}; scanned=0; recent=0; dispatch=0
for p in sorted(SD.glob('*.state')):
    scanned += 1
    d = rg.read_state_file(p, strict=True)
    records.setdefault(d.get('review_target',''), []).append({k:d[k] for k in ('round','kind_label','head_sha') if k in d})
    try: started = float(d.get('started_at','nan'))
    except ValueError: continue
    if not END-7*86400 <= started <= END: continue
    recent += 1
    key = d.get('review_target','')
    if not key.startswith(('pr:','issue:')): continue
    dispatch += 1
    if key not in selected or started > float(selected[key].get('started_at','0')):
        selected[key] = {k:d.get(k,'') for k in ('started_at','workdir','head_sha','kind_label','github_account')}
cache={}
def fetch_one(pair):
    key, latest = pair; t=rg.parse_target(key); env=os.environ.copy()
    account = latest.get('github_account')
    if account:
        env['GH_CONFIG_DIR']=str(SD/'gh-account'/account)
        for k in ('GH_TOKEN','GITHUB_TOKEN','GH_ENTERPRISE_TOKEN','GITHUB_ENTERPRISE_TOKEN'): env.pop(k,None)
    fields = 'state,body,url' + (',headRefOid' if t.kind=='pr' else '')
    try:
        p=subprocess.run(['gh',t.kind,'view',str(t.number),'-R',t.repo_slug(),'--json',fields], env=env,capture_output=True,text=True,timeout=35)
        data=json.loads(p.stdout) if p.returncode==0 else {'error':'read failed'}
    except Exception: data={'error':'read failed'}
    return key,data
with ThreadPoolExecutor(max_workers=6) as ex:
    cache.update(ex.map(fetch_one, selected.items()))
fetch_time=datetime.now(timezone.utc).isoformat()
from functools import lru_cache
head_original=rg.ledger_head_shas_for_target
@lru_cache(None)
def head_fn(sd, key, *, kind_label=None):
    return head_original(sd, key, kind_label=kind_label)
rg.ledger_head_shas_for_target=head_fn
body_fn=rg.body_own_round
results=[]
for key, latest in sorted(selected.items()):
    t=rg.parse_target(key); data=cache[key]
    if 'error' in data:
        results.append({'target':key,'state':'UNKNOWN','error':data['error']});continue
    def fetch(target):
        k=target.key()
        if k not in cache: cache.update([fetch_one((k, latest))])
        if 'error' in cache[k]: raise rg.Indeterminate('body read failed')
        return cache[k]['body']
    workdir=latest['workdir']; head=''
    if Path(workdir).is_dir():
        p=subprocess.run(['git','-C',workdir,'rev-parse','HEAD'],capture_output=True,text=True)
        if p.returncode==0: head=p.stdout.strip()
    source='workdir HEAD'
    if not head:
        head=data.get('headRefOid') or latest['head_sha'] or 'unmanaged'
        source='PR HEAD' if data.get('headRefOid') else 'last state HEAD (assumed)'
    row={'target':key,'state':data['state'],'kind':latest['kind_label'] or 'コード','head_source':source,'modes':{}}
    for mode,pending in [('current',head),('fresh','design3-unseen-head')]:
        bodies={};old_counts={}
        def tracked_fetch(target):
            b=fetch(target); bodies[target.key()]=b;return b
        try:
            old=rg.target_total_rounds(t,SD,tracked_fetch,[],pending)
            old_dec=rg.decide(old,data['body'])
            # Existing recursion/HEAD counting, no copied count implementation.
            with patch.object(rg,'body_own_round',lambda body:0):
                unfiltered=rg.target_total_rounds(t,SD,fetch,[],pending)
                for k,b in list(bodies.items()):
                    old_counts[k]=rg.target_total_rounds(rg.parse_target(k),SD,fetch,[],pending if k==key else None)
                with patch.object(rg,'ledger_head_shas_for_target',lambda sd,k,**kw:head_fn(sd,k,kind_label=row['kind'])):
                    candidate=rg.target_total_rounds(t,SD,fetch,[],pending)
            failures=[]; shapes=[]; attribution=[]
            for k,b in bodies.items():
                approvals=rg.parse_approval_rounds(b)
                if not approvals: continue
                for n in sorted(set(approvals)):
                    matches=set(); invalid=False
                    for record in records.get(k,[]):
                        saved=record.get('round','')
                        if not saved.isascii() or not saved.isdecimal() or int(saved)<1:
                            invalid=True; continue
                        if int(saved)!=n: continue
                        kind=record.get('kind_label','コード')
                        if kind not in ('設計','コード') or not record.get('head_sha'):
                            invalid=True; continue
                        matches.add(kind)
                    reason=''
                    attributed=next(iter(matches)) if len(matches)==1 else None
                    if invalid or attributed is None: reason='unattributable'
                    with patch.object(rg,'body_own_round',lambda body:0):
                        # Prior design diagnostic includes pending only at root.
                        with patch.object(rg,'ledger_head_shas_for_target',lambda sd,key,**kw:head_fn(sd,key,kind_label=row['kind'])):
                            kind_pending=rg.target_total_rounds(rg.parse_target(k),SD,fetch,[],pending if k==key else None)
                        if kind_pending < n <= old_counts[k]: shapes.append(k)
                        if attributed:
                            with patch.object(rg,'ledger_head_shas_for_target',lambda sd,key,**kw:head_fn(sd,key,kind_label=attributed)):
                                completed=rg.target_total_rounds(rg.parse_target(k),SD,fetch,[],None)
                            if not reason and completed<n: reason='same_kind_deficit'
                    if reason: failures.append({'target':k,'N':n,'reason':reason})
                    attribution.append({'target':k,'N':n,'kind':attributed})
            missing=failures
            new_dec=rg.decide(candidate,data['body'])
            count=rg.same_head_dispatch_count(SD,key,pending)
            row['modes'][mode]={'old_round':old,'new_round':candidate,'old_status':'blocked' if count>=3 else old_dec.status,'new_status':'blocked' if count>=3 else ('indeterminate' if missing else new_dec.status),'missing_approval_floor':bool(missing),'same_head_cap':count>=3,'review_shape':bool(shapes),'failures':failures,'attribution':attribution}
        except Exception as e:
            row['modes'][mode]={'error':type(e).__name__}
    results.append(row)
summary={'selected_baseline_utc':'2026-11-14T22:40:52.360285+00:00','fetch_end_utc':fetch_time,'states':scanned,'recent':recent,'dispatches':dispatch,'targets':len(selected),'states_now':dict(Counter(r['state'] for r in results))}
for scope in ('all','OPEN'):
    for mode in ('current','fresh'):
        c=Counter()
        for r in results:
            if scope=='OPEN' and r['state']!='OPEN': continue
            c['scope']+=1
            m=r.get('modes',{}).get(mode,{})
            if not m or 'error' in m: c['unknown']+=1;continue
            c['measured']+=1
            o,n=m['old_status'],m['new_status']
            if o=='pass' and n!='pass': c['stops']+=1
            if o!='pass' and n=='pass': c['passes']+=1
            if m['new_round']>m['old_round']: c['increases']+=1
            if m['new_round']<m['old_round']: c['decreases']+=1
            if m['new_round']==m['old_round'] and o==n: c['same']+=1
            if m['missing_approval_floor']: c['missing_floor']+=1
            if m['review_shape']: c['review_shape']+=1
        summary[scope+'_'+mode]=dict(c)
(OUT/'impact.json').write_text(json.dumps({'summary':summary,'results':results},ensure_ascii=False,indent=2))
# No credentials, no raw state or complete issue body is persisted.
print(json.dumps(summary,ensure_ascii=False,indent=2))
```
