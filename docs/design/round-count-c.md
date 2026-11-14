C の設計: 最小案 既存の種別別 distinct HEAD を再利用／影響確認 通常・現HEADで止まるようになる3件・通るようになる3件（42対象中1件と公開前特例は未測定）

作成: 2026-11-15 JST。run: `round-count-c-design2`。対象: #38 C・#37。
作業場所: `/Users/matsukaze-takashi/matsukaze-utils/codex-watch/_wt.noindex/round-count-c`、枝 `feat/round-count-c`、読取基点 `e7d8cf1`。
本書は設計案。製品コード・試験・設定・実台帳は変更しない。別系統レビュー済み・実装着手可とは扱わない。

## 1. 読んだもの・縮める根拠

| 必須参照 | 出所・今回の扱い |
|---|---|
| 段取り表の該当行（パス:行） | 無し（今回の割当てはT番号ではなく #38 C と #37）。別PJの段取り表は更新しない |
| 本人の決定の出所 | 今回の依頼「頭の判断（理由つき）」と `gh issue view 37 -R todoroki-godai/codex-watch`（取得成功）。#37の「旧承認を両カウンタへ」も選択肢として明記されている |
| 見本HTML | 無し（画面変更なし） |
| 前身の設計・巡 | `e7d8cf1:docs/design/round-count-c.md`、特に§1.2の実測。`docs/design/review-complete.md` §3、`docs/review-preface-kind-rounds.md`。前回の巨大案を今回の依頼で置き換える |
| 指定実装 | `lib/round_gate.py:279-297,444-489,614-674,688-729,1246-1302,1406-1441`、`lib/prerelease.py:41-98,148-178`（以降の固定上限・版照合も確認）、`bin/codex-review:115-123,236-239,285,341` |
| 試験設計 | 作業場所の `.claude/skills/test-design/` は無し。前回の出所 `/Users/matsukaze-takashi/updater/updater-index/_wt.noindex/rev9-audit/.claude/skills/test-design/SKILL.md` を読み直して§5へ適用 |
| 既存試験・計測 | `tests/test_round_gate.py:191-269`、`tests/test_prerelease.py` のfixture、`tests/test_prerelease_fixA.py`、既存変異実行器の参照とAの `.tmp/impact/compare.py`（旧A版の比較値は使わない） |

skill欠落への選択肢は「補充まで停止／前回の同じskillを読む」、既定案は後者で進めた。今回の規則は本依頼を優先する。別系統レビュー1巡は後続の受入条件として残し、他のLLMは呼ばない。

前回§1.2の実測: (a) 設計state3 HEAD＋承認cap3→コード新HEADは混算4で停止、(b) 同一HEADコード2run→新HEADは通常経路では2巡・説明文があっても通過、(c) 特例historyはその2runを2と数え、説明文では例外を投げる。今回はこの観察を根拠に縮小し、(b)の通常経路を直す対象にはしない。前回の観察を新仕様の成功試験とは呼ばない。

追加前に `git grep -n -E 'target_total_rounds|ledger_head_shas_for_target|ledger_own_round_for_predecessor|body_own_round|parse_approval_rounds|parse_total_cap|history\(' -- lib bin tests` を実施し、**57行**を確認。既存filter・再帰・承認パース・特例照合・変異実行器を再利用する。「既存の道具が無い」という主張はしない。

## 2. 最小案

### 2.1 通常経路: 種別を通し、結果を1つ使う

巡の単位は既存の **同じtarget・同じ種別のdistinct HEAD**。同HEADの複数runは1巡、異なるHEADは別巡。内容hash・集合・時刻から新しい単位を作らない。

- `target_total_rounds` と `ledger_own_round_for_predecessor` に今回の `kind_label` を渡し、既存 `ledger_head_shas_for_target(..., kind_label=...)` を使う。前身の再帰にも同じ種別を渡す。今回HEADが今回種別に未登録なら1加算、登録済みならdistinct数のまま。前身には加算しない。
- `kind_label` 欠落stateは既存filterどおりコード、不正種別・読取失敗は既存filterどおり停止。HEAD欠落の旧stateは既存の除外を維持し、移行機構は作らない。循環・深さ上限・本文取得失敗の停止も維持する。
- gateの `total_round` を唯一の今回巡とし、CLIの前置き・点検・stateの `round`・本文追記にその値を渡す。前置きで `ledger_own_round` を再計算しない。前身込み総巡を使うため、前身2巡＋今回1巡は全箇所3。過去HEADへの再発注でも先頭からの序数へ戻さない。
- 同一target×HEADの3本上限は別の安全策であり、現在どおり全種別の本数で判定する。通常1〜2巡、3〜5巡の承認、6以上の既存裁定経路、none/bypassの既存分岐は作り替えない。

### 2.2 種別なし承認: 両方の許可・上限へ適用し、消化数へコピーしない

**選ぶ規則は1つ:** 既存「巡Nの人間承認」と「総上限: M」を、設計・コード両カウンタへの承認の存在と固定capとして適用する。Nを両カウンタの消化数にしない。capの既存パース（複数は最大値）を維持し、3〜5巡の `decide` を再利用する。承認行の真正性や新たな本人決定を機械が作るものではない。

| 条件 | 期待 |
|---|---|
| 設計3 HEAD＋種別なし承認「巡3・総上限3」、コード初回新HEAD | 設計3を保持しコード1で通過。承認はコード1の必須条件ではない |
| コード3巡目、承認行なし | 停止。capだけあっても承認にはならない |
| 設計4巡目、上のcap3あり | 停止 |
| コード3巡目、上の承認・cap3が残る | 両カウンタへ適用する互換規則により通過。種別別の本人承認が新たにあったという意味ではない |

**承認による旧下限の安全性:** 現行 `max(台帳総巡, body_own_round)` は台帳消失でも小さな巡で再開させない。これを無条件に削除しない。各target・前身ノードで、既存と同じ「全種別の台帳distinct HEAD＋前身、今回だけpending HEADを含む」を承認下限抜きで算出し、承認Nがこれを超える場合は **種別への配分不能としてindeterminate（送信不可）** にする。それ以外はNによるかさ上げを行わず、今回種別の台帳総巡を使う。各前身でも検査し、子孫の余剰で前身の不足を隠さない。

これは既存下限が台帳を持ち上げた場合に限る保守的な互換処理で、新台帳・補完・移行ではない。失われた件数の正確な種別は復元できないため、その場合は巡数を確定したと表示しない。承認行を削って再開させる手順も採らない。既存の全種別台帳で裏付け可能なら通すが、stateの完全性を新たに保証する仕組みではない。前身の共有祖先に対する現行visitedの挙動も今回変更しない。

採らなかった案: Nを両方の下限へ適用するとコード初回が3以上になり#37に反する。Nを常に捨てると台帳消失時の安全策を失う。種別を推測して承認へ書き足す案は帰属が不明な場合を解消しない。新たな種別付き承認形式は、今回の両カウンタ互換で満たせない必須の実例が提示されていないため足さない。将来「設計cap3とコードcap5を別承認する」需要が確定したら別課題とする。

### 2.3 公開前特例: 照合してから同種のHEADを数える

`prerelease.history` に今回種別を渡す。既存の節取得、dispatch_idの照合、同IDの異なる履歴行の矛盾検出、state/予約のキー重複・ID検査を残し、照合後に今回種別だけのdistinct HEADを数える。別種別の行を先に消して同IDの矛盾を隠さない。未対応の旧表行を推定で合流せず、既存のdispatch_id補完必須を維持する。

履歴節の空行・ヘッダ・区切り・**表以外の説明文は読み飛ばす**。一方、表のデータ行・dispatch_idを持つ行で形式が壊れているものは説明文として捨てず特例不成立。dispatch_id同士の矛盾を人間承認で特例内だけ握りつぶさない。通常経路へ特例historyを追加しない。

HEADは既存stateの完全SHAを使い、本文・state・予約をdispatch_idで対応付けて同一発注を重複させない。予約には既存 `prerelease_evidence.record` のkind/head_shaがあるので再利用し、新しい予約方式は足さない。本文だけの行は完全SHAがあれば使い、短縮SHAなら同IDの既存記録等で完全SHAを一意に照合できる場合だけ使う。曖昧な短縮SHAや対応材料不足は特例不成立。旧stateの自動移行やGitHub書込みで補完しない。

`history` の実績数だけに常に1を足す方法も廃止する。今回HEADを渡す場合は既存と同じdistinct集合へ今回を入れた予測数を返し、`evaluate` はその値をgateの今回種別の総巡と照合する。同HEADへの2本目は加算せず、別HEADは1加算。stateと予約が同じIDなら1件、別IDでも同HEAD・同種なら1巡。特例は前身なしなので、通常の種別別総巡と一致する。

**変えない条件:** 2ファイルの既定枝blob一致、PJ実体登録、裁定ID・対象・kind・版・対象一覧の照合、巡3〜5と固定総上限、保存済み系列/固定上限の照合、blocking/前身なし、時刻・操作範囲、bypass併用禁止、送信前再照合・既存予約。通常の有効な人間承認を特例APIより先に判定する順序も維持する。固定上限照合を種別ごとに緩める変更は今回しない。

### 採らなかった大きな案

新台帳、round_id、series_idの新設、確定集合レコード、予約の通常経路への全面適用、旧state移行・全発注口統合は作らない。通常の二重計上・説明文停止は現物で再現せず、#37と特例の欠陥には既存filterとHEAD集合で足りる。トークン補完やDの振り分け配線も今回拡張しない。

## 3. 完成条件（実装時の受入条件）

1. **守る対象:** 種別別distinct HEAD、同種の前身継承、前置き/点検/state/判定の同値、3巡目の承認・固定上限。特例のID照合・2blob・総上限・bypass禁止を弱めず、説明文だけでは止めない。
2. **信頼境界:** CLI種別、state/予約、GitHub本文・前身、特例の登録/規則/裁定・対象版。既存入力検査と読取失敗の停止を残す。旧承認の裏付け不足を新規1巡へ落とさない。
3. **対象外:** 新しい巡単位/台帳/移行/通常予約、D接続、トークン補完刷新、bypass権限刷新、AWS/DB・dev/stg/prod、レビュー本数の自動承認。
4. **blocking:** 種別混算・前身filter漏れ・表示と保存の不一致、旧下限不足での送信、特例の過少/過大計数・説明文停止、安全条件の迂回。別系統設計レビュー1巡を受け、[Must]が残る間は製品実装へ着手しない。今回そのレビューは未実施。
5. **検証:** §5の正常通し→境界/既存安全策→全パッケージ→変異。欠陥を決定論チェックへ翻訳する。有効な変異の生存が1件でもあれば実装完了にしない。設計commitだけで実装済みとは扱わない。

## 4. 影響確認

選択基準は前回と同じ **2026-11-15 07:40:52.360285 JST**（UTC `2026-11-14T22:40:52.360285+00:00`）までの7日間。今回は5169 stateを読取り、期間内890・issue/pr発注84・重複排除**42対象**を再確認。前回5164から全期間のstateが5件増えているので前回snapshotの再現とは呼ばない。本文取得終了は **2026-11-15 08:02:13.748799 JST**、OPEN33・MERGED6・CLOSED2・取得不能1で前回の内訳と一致した。auth switchなし、実台帳は読むだけ。

「次の1本」は各対象の期間内最新stateと同じ種別、通常経路、追加env前身なし・特例裁定IDなし、同じ本文/前身を使う。現在HEADは最新stateのworkdirで `git rev-parse HEAD`、消失時はPRのheadRefOid、次に最終state HEADを仮定する。併せて未登録の新HEAD条件を測った。閉じた8対象も仮想の次発注として集計し、OPENとは分ける。

製品ファイルを変更せず、既存 `target_total_rounds/decide/same_head_dispatch_count` を呼んだ。候補だけ `unittest.mock.patch` で既存HEAD列挙へkind filterを渡し、承認の計数下限を外す。全種別・下限抜きの既存再帰も呼び、§2.2の不足条件を各ノードで検査した。計数・再帰・上限判定を写した実装ではない。3本上限も最終判定へ含めた。

| 範囲・今回HEAD | 対象 | 本文未取得 | 止まるようになる | 通るようになる | 巡増加 | 巡減少（確定分） | 巡・判定とも同じ | 下限不足で巡未確定 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 全対象・現HEAD | 42 | 1 | 3 | 3 | 0 | 7 | 31 | 3 |
| OPEN・現HEAD | 33 | 0 | 2 | 3 | 0 | 7 | 24 | 2 |
| 全対象・新HEAD | 42 | 1 | 2 | 6 | 0 | 7 | 32 | 2 |
| OPEN・新HEAD | 33 | 0 | 1 | 6 | 0 | 7 | 25 | 1 |

「止まる」はpass→blocked/indeterminate、「通る」は逆。判定変化は巡増減と重複する。巡の照合は現HEADで **7+31+3+1=42**、OPENは **7+24+2=33**。下限不足の候補台帳値は減るが、確定した巡減少へ含めない。

現HEADで通るようになる3件は `issue:min-sys/updater-index#1708,#2018,#2031`（各3→2）。下限不足でpass→indeterminateになる3件は `issue:min-sys/updater-index#1564`、`pr:min-sys/updater-index#2007`、`pr:min-sys/updater-index#2043`（最後はMERGED）。正確な種別巡を失った記録を小さく扱わないための停止で、混算修正の逆効果として隠さない。本文未取得は `pr:min-sys/docs-platform#1057`、同じ/0件には含めない。

**未測定:** 特例裁定IDを指定した次発注の最終判定。現行 `history(body,state_dir,target,*,strict)` にkind/pending HEADの引数はなく、引数変更だけでは候補を実行できない。登録blob・裁定内容・版/時刻の固定も必要なので、通常41件の比較を特例込み結果へ拡張しない。前回の「集合ID不足で全面未測定」という理由は撤回する。今回の通常経路は既存関数で測れた。実装後、同じ42対象・固定本文/前身・state入力の隔離コピーで旧版と実装版 `run_gate` を呼び、通常/特例・現/新HEADを別集計する。実予約・発注・本文更新はせず、取得不能と下限不足を別欄で照合する。

再現コマンド: 下の付録を `.tmp/round-count-c-design2/impact.py` に保存し、`PYTHONDONTWRITEBYTECODE=1 python3 .tmp/round-count-c-design2/impact.py`。標準ライブラリとgh読取のみ。入力を保存していないため再取得時の本文・全期間state・workdir HEADの変化で値は変わる。結果の `impact.json` は資格情報/本文全量を含まない。付録summaryのdecreasesは不足時の暫定台帳値も含むため、本表は `missing_approval_floor` を除いて集計した。

## 5. 試験計画（正常系を先に。今回は試験追加なし）

| 入力 | 区分・境目／置く値 | 期待 | 期待の出所 | 大きさ／試験名案 |
|---|---|---|---|---|
| 発注全体 | 設計3 HEAD＋旧承認cap3→コード初回新HEAD | 通過、前置き/点検/state/本文/gateがコード1 | #37・本書§2 | fake CLI通し／design3_code1 |
| コード巡と承認 | 今回2/3、承認なし・capだけ | 2可、3停止 | #37 | 関数／code3_no_approval |
| 旧承認とcap | 両種別で3/4、cap3あり | 3可、4停止 | #37・§2.2の互換選択 | 関数＋CLI／legacy_cap |
| 通常上限 | 4/5/6、cap5・承認、6は裁定なし/あり | 4/5可、6は既存裁定条件を維持 | 現行の維持指定・§2.1 | 関数／limit5 |
| HEAD集合 | 同target・同種・同HEADの2run、別HEAD、過去HEADへの再発注 | 1巡/2巡、過去HEADでも現在の総巡を表示 | 今回の依頼・§2.1 | 関数＋CLI／distinct_heads |
| 種別と前身 | 設計/コード混在、同種前身2＋今回1、復帰、循環/深さ超過 | 同種3、他種不算入、既存停止維持 | #37・§2.1 | 関数＋CLI／inherit_kind |
| 承認下限 | Nが各ノードの全種台帳値以下/1大、台帳消失 | 以下は種別計数、大は判定不能で未送信 | 既存安全策維持・§2.2 | 関数＋CLI／approval_floor |
| 文字・欠け | 種別なし/不正/空白、state読取不能、HEADなし | 既存filter互換（欠落コード・不正停止・HEADなし除外） | §2.1 | 関数／kind_compat |
| 履歴の文字 | 正しい表＋説明文、非数値の壊れた表行、dispatch_id付き壊れ行 | 説明文は無視、不正イベントは特例不成立 | 今回の依頼・§2.3 | 関数＋特例通し／history_prose |
| 特例のIDとHEAD | 同ID重複/矛盾、別種別に同ID、別ID同HEAD、state/予約重複、短縮SHA曖昧 | 矛盾拒否後に今回種別distinct HEAD、曖昧なら不成立 | ID照合維持・§2.3 | 関数＋特例通し／history_identity |
| 特例の継ぎ目 | 今回HEADが既知/未知、設計履歴混在 | 無条件+1せずgateと同じ巡 | 今回の依頼・§2.3 | 関数＋CLI／history_pending |
| 安全策・操作不能 | blob2個一致/片方不一致、cap3/超過、bypass併用、保存済cap変更 | 一致かつ既存全条件内だけ通過 | 今回の維持指定 | 既存特例通し拡張／prerelease_contract |
| 時刻・合図 | 固定時刻、未来裁定、予約後の送信前再照合不一致 | 既存時刻検査/再照合で未送信、sleepで同期しない | 既存安全策維持 | 既存fake CLI／recheck |

同じ側の言い換えは増やさない。DB・画面は対象外で試さない。時刻は既存特例の固定時計を使い、種別計数へ時刻条件を追加しない。正常通しから書き、表の期待を実装出力から逆算しない。既存の通常経路2run/説明文試験も残す。

| 変異区分 | 最小案への変異 | 検出する試験と着弾証跡 |
|---|---|---|
| 陽性対照 | state列挙順だけを反転 | distinct_headsが緑、意味不変diffと実行trace |
| ①守る処理を消す | 前身へのkind伝播を消す | inherit_kindが赤、再帰の実行行trace |
| ②意味を壊す | 特例をdistinct HEADからrun数へ戻す（または無条件+1） | history_identity/history_pendingが赤、計数行trace |
| ③入れ替える | CLIで設計/コードのkindを交換 | design3_code1が赤、受渡し/保存行のシェルtrace |
| ④検査自体を無効化 | 旧下限不足の停止を常時成功化 | approval_floorの未送信期待が赤、停止分岐trace。試験をskip/0件化しても収集・skip・期待試験IDの別照合で失敗にする |

別種の回避を2件以上: (a) 他種別の表行に同dispatch_idの矛盾を隠す（入力照合の回避）、(b) 初回判定後に保存済cap/版を変えて送信前再照合を通そうとする（時間差の回避）。kindを変えるだけの変異の言い換えにしない。2blob・cap・bypassの既存安全策の決定論チェックも残す。

実装/試験をcommitした基点から作業場所内の隔離コピーへ1件ずつ変異を当てる。(a)不変条件を壊すdiffと前後hash、(b)実際に分岐が実行されたPython標準trace/シェルtraceを別証跡に残す。構文エラー・未着弾・無関係の赤は成功にしない。既存 `tests/check_prerelease_fixA_mutations.py` 等の手順を再利用し、陽性1件・①〜④各1件以上・別種回避2件を確認する。緑の有効変異があれば未完了。隔離コピーの復元/削除後、原本の `git diff` とstatusが空か確認する。reset/checkout等は使わない。

全パッケージの試験コマンド（TMPDIRの親を先に作る）:

```sh
mkdir -p .tmp/round-count-c-design2/tmp
GIT_CEILING_DIRECTORIES="$PWD" TMPDIR="$PWD/.tmp/round-count-c-design2/tmp" PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider --basetemp="$PWD/.tmp/round-count-c-design2/pytest"
```

## 6. 影響箇所と7段

今回の製品関数変更は0件。以下は§1のgrepから得た実装時の全製品参照（試験呼出しは同じ57行のgrepで再列挙し、新署名へ照合する）。本書の行番号は読取基点の実物。

| 変更候補・製品内呼出し元 | 実装時の壊れない条件 |
|---|---|
| HEAD列挙: `round_gate.py:483,617,653` | 既存ledger_own_round互換、総巡/前身にkind。filterの読取失敗を握りつぶさない |
| 前身own: `round_gate.py:651`、総巡: `:666,1269` | 再帰に同kind、pending加算は今回のみ、循環/深さ失敗維持 |
| 本文下限/承認: `round_gate.py:296,671,697,698` | 許可/capと計数分離、下限不足で停止、capだけでは承認なし |
| history: `prerelease.py:178` | kind・pending HEAD受渡し、ID照合と全安全条件維持 |
| CLI: `bin/codex-review:116-125,236-239,285,341` | gate totalを前置き/点検/stateへ渡し、種別と巡の取り違えなし |
| gate結果消費: `round_gate.py:1421-1441`、本文行 `:1334-1342` | 特例再照合・予約snapshot・記録が同じ総巡を使う |

将来の範囲外候補名: 巡番号だけによるトークン補完、共有祖先visited、6巡以上裁定/bypassの権限確認。今回は名前の報告だけで、修正しない。

| 足す仕組み・章・項目 | 7段で止まる段と理由 |
|---|---|
| §1の現状・参照 | ㋐明示依頼、㋑前回実測と既存grepで止まる |
| §2.1種別別計数/共通値 | ㋑既存filter・再帰・gate JSONを使う。新カウンタ基盤なし |
| §2.2旧承認互換/不足停止 | ㋑既存承認/capと全種別計数を使う。失われた下限を捨てない最小の分岐だけ。新形式は㋐需要未提示で作らない |
| §2.3特例 | ㋑既存ID照合・state/予約・HEAD計数を再利用、㋒標準set/辞書で足りる。別種別filter・説明文の読み飛ばしを追加し、依存は足さない |
| §3受入条件 | ㋐削減不可・明示依頼、㋑既存安全条件を維持して止まる |
| §4影響・付録 | ㋑既存関数を呼ぶ、㋒標準mock/Counter/pathlib、㋓gh読取で止まる。製品のコピー実装なし |
| §5試験/変異 | ㋐削減不可、㋑既存pytest/fake/変異手順、㋒標準traceで止まる |
| §6呼出し元・7段、§7記録/次回 | ㋐明示依頼、㋑既存git grep・試験結果の記録で止まる |
| 新台帳/ID/通常予約/移行 | ㋐今回の再現欠陥に不要なので作らない |

㋓プラットフォーム・㋔導入済み依存・㋕1行・㋖最小コードまで下る新製品機構はない。信頼境界・データ消失防止・安全策・別系統レビュー1巡・[Must]残存中の着手禁止・決定論チェック・変異は削減しない。

## 7. 今回の検証・環境差・次回

上記コマンドでパッケージ全体（pytest自動収集729件）を実行し、**724 passed・0 failed・5 skipped、279.41秒**。ログは作業場所内 `.tmp/round-count-c-design2/pytest.log`。`git diff --check` は成功。実装検査を新設していないため、今回の変異は計画のみ。commitは名義確認hookでコマンド実行前に拒否された（期待 `todoroki-godai`、検出 `matsukaze-minden`）。auth switch・hook迂回は行わず、依頼の例外指定どおり文書変更を残す。新commit SHAは無し、基点は `e7d8cf1`。調整役がcommitする。最終状態は文書1件のstage済み差分であり、作業木全体がcleanという意味ではない。

新規試験・製品変更は0件。候補の正常/変異試験、特例込み影響、実発注、DB試験は未実行。既存試験の緑をC実装の成功とはしない。本線では測っていないので「前からある赤」という主張はしない。

| 環境 | 経路・設定・データの違い／今回の扱い |
|---|---|
| ローカル | 共通state・GitHub本文/前身が入力。実台帳読取とmockによる非送信比較、fakeによる既存試験 |
| dev | 巡数コードの環境別分岐は無し。接続・読取・書込なし |
| stg | 巡数コードの環境別分岐は無し。接続・書込なし |
| prod | 巡数コードの環境別分岐は無し。接続・操作なし |

指定の結果/次回ファイルの親 `/Users/matsukaze-takashi/updater/updater-index/_work/notes/codex-queue/` は今回のsandboxの書込許可外。権限追加もできないため、`refactor-result-round-count-c-design2.md` と `refactor-next-round-count-c-design2.md` は未作成。この点は最終報告にも残す。別置場にqueueを作って完了扱いにしない。

指定resultファイルへの転記用（10行以内）:

```text
済: C設計を既存の種別別distinct HEAD・旧承認互換・特例historyの修正へ縮小。
対象: docs/design/round-count-c.md、基点e7d8cf1、製品変更0。
commit SHA: 無し（名義確認hookが期待todoroki-godai/検出matsukaze-mindenで拒否）。
試験: パッケージ全体729件、724 passed・5 skipped・0 failed（279.41秒）。
影響: 現HEAD通常42対象中41件測定、停止へ3・通過へ3、OPEN33では停止へ2・通過へ3。
未実行: 1対象本文取得不能、特例込み影響、候補試験/変異、別系統レビュー、DB。
停止理由: commit拒否。指定queue2ファイルもsandbox書込許可外のため未作成。
次候補: 調整役のcommit、別系統設計レビュー1巡、[Must]0確認後に最小実装。
```

次の起動用「今回の作業」候補（依頼元が指定queueへ転記する内容）:

> ## 今回の作業
> run名: round-count-c-design2-review。作業場所: `/Users/matsukaze-takashi/matsukaze-utils/codex-watch/_wt.noindex/round-count-c`（feat/round-count-c）。製品コードは変更せず、依頼元が別系統設計レビュー1巡を手配し、`docs/design/round-count-c.md` の旧承認互換・台帳下限不足3件・特例のID/完全HEAD照合・表示保存の一致を確認する。今回窓で他LLMは呼ばない。終わりの条件: 受領照合と[Must]一覧を記録し、[Must]0になるまで実装着手を禁止する。次のrun名: round-count-c-impl（[Must]0確認後のみ）。

## 付録: 通常経路の非送信比較（再現用）

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
OUT = Path('.tmp/round-count-c-design2')
SD = Path.home()/'.codex-watch'
END = datetime.fromisoformat('2026-11-14T22:40:52.360285+00:00').timestamp()
selected = {}; scanned=0; recent=0; dispatch=0
for p in sorted(SD.glob('*.state')):
    scanned += 1
    d = rg.read_state_file(p, strict=True)
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
head_fn=rg.ledger_head_shas_for_target
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
    for mode,pending in [('current',head),('fresh','design2-unseen-head')]:
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
            missing=[k for k,b in bodies.items() if body_fn(b)>old_counts[k]]
            new_dec=rg.decide(candidate,data['body'])
            count=rg.same_head_dispatch_count(SD,key,pending)
            row['modes'][mode]={'old_round':old,'new_round':candidate,'old_status':'blocked' if count>=3 else old_dec.status,'new_status':'blocked' if count>=3 else ('indeterminate' if missing else new_dec.status),'missing_approval_floor':bool(missing),'same_head_cap':count>=3}
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
        summary[scope+'_'+mode]=dict(c)
(OUT/'impact.json').write_text(json.dumps({'summary':summary,'results':results},ensure_ascii=False,indent=2))
# No credentials, no raw state or complete issue body is persisted.
print(json.dumps(summary,ensure_ascii=False,indent=2))
```
