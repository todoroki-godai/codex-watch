C の設計: 最小案 種別別の確定集合を1巡にする／影響確認 未測定（旧stateに確定集合の識別材料が無く、正確な新計数を復元できない）

作成: 2026-11-15 JST。run: round-count-c-design。課題: todoroki-godai/codex-watch #38 C・#37。
作業場所: `/Users/matsukaze-takashi/matsukaze-utils/codex-watch/_wt.noindex/round-count-c`。
読取基点: `0f630c5`、枝 `feat/round-count-c`。製品・試験・設定は変更しない。以下は実装の仕様案で、導入済みの機能ではない。

## 1. 読んだものと現在の計数

| 必須参照 | 出所と扱い |
|---|---|
| 段取り表の該当行 | 無し（今回はT番号の指定なし）。対象は #38 の C と #37、順番は #38 の A→C→D |
| 本人の決定 | 今回の依頼と `gh issue view 38 -R todoroki-godai/codex-watch` の本文（2026-11-13 16:22 JST受領・調整役中継）。#37本文も取得。#38「巡4の人間承認」の通常経路維持はAへの指示として読み、Cで計数を変える了承と区別する |
| 見本HTML | 無し（画面変更なし） |
| 前身の設計・巡 | `docs/design/review-complete.md` 全体、特に §2.3・§3・§6、`docs/review-preface-kind-rounds.md`、#38本文の設計巡1・コード巡1〜4と承認節。旧設計の「同じHEADでも別runなら次巡」は確定集合内の複数runを区別できないため本書で具体化 |
| Aの影響資料 | `/Users/matsukaze-takashi/matsukaze-utils/codex-watch/_wt.noindex/review-complete/.tmp/impact/{REPORT.md,compare.py}`。過去の31件中13件停止はA旧版の測定で、Cの結果へ転用しない |
| 決まり | `~/.claude/rules/review.md:6`（種別別・系列継承・通常2巡・例外3〜5）、`~/.claude/skills/review-gate/SKILL.md:169-190`（確定集合を1巡、帰属固定、履歴）。読むだけ |
| 実装・説明 | `lib/round_gate.py`、`lib/prerelease.py`、`bin/codex-review`、`lib/history_backfill.py`、`README.md`。下記の行番号はすべて基点の実物 |
| 既存試験 | `tests/test_round_gate.py` の計数・承認・前身・本文更新、`tests/test_review_must_criteria.py` の種別別前置き、`tests/test_prerelease{,_fixA,_fixA2}.py`、`tests/test_history_backfill.py`、`tests/test_codex_review_cli.py`、`tests/conftest.py` |
| 試験設計スキル | 作業場所の `.claude/skills/test-design/` は存在しない。前身設計が参照する `/Users/matsukaze-takashi/updater/updater-index/_wt.noindex/rev9-audit/.claude/skills/test-design/SKILL.md` を読み、§5の区分表へ適用 |

参照物不足への選択肢: (1) 指定作業場所のskillが揃うまで試験計画も保留、(2) 前身が指定する既存skillを読む。既定案(2)で設計を進めた。追加のLLM・別系統レビューは起動せず、設計レビュー未実施のまま依頼元へ返す。

### 1.1 どこで巡が決まるか

| 段階 | 現在の実物と意味 |
|---|---|
| 種別の入力 | `bin/codex-review` は `CODEX_REVIEW_KIND_LABEL` を要求。stateには `kind_label` を保存（:341）。gate CLIも種別を受けるが通常の総巡数には渡さない |
| 本体の総巡 | `lib/round_gate.py:444-489` はstateのtargetとdistinct HEADを数える。種別filterは既にあるが、`:614-674 target_total_rounds` は使わず全種別のHEAD数＋前身を合算。今回HEADが既存なら加算せず、未知なら1加算 |
| 本文の下限 | `:279-297` の承認行「巡Nの人間承認」の最大Nを、`:674` で台帳総巡数とのmaxにする。本文の履歴表は通常経路では数えない。総上限は本文全体から最大値（:284） |
| 判定 | `run_gate:1256-1275` は同一target×HEADの3本上限を先に判定し、総巡数を `decide:688` へ渡す。1〜2通過、3〜5は承認とcap、6以上は裁定行を要求 |
| 前置き・保存の不一致 | `bin/codex-review:115-123` は種別別の `ledger_own_round` を再計算。stateの `round`（:335）はgateの混算値。前置きだけ種別別に直ってもgateは直らない |
| 公開前特例 | 通常判定が停止し裁定IDがあるときだけ `run_gate:1279`→`prerelease.evaluate:148`。`:178` で `history(..., strict=True)+1 == total` を照合。`history:41-98` はrun_idの和集合で、全種別を混算し、説明文を拒否する |
| 本文更新 | `record_round:1306`→`render_round_row:740`。dispatch_idは特例だけ付く（:1342）。`backfill_measuring_row:811` は巡番号だけで最初の行を更新。`history_backfill.py:14` は既存表行とstateを5項目の1対1で対応させIDを提案する。集合IDは補えない |

### 1.2 指摘3件を現在の実物で確認した結果

Python標準 `tempfile` の作業場所内ディレクトリに架空stateを置き、HEAD/remoteと本文取得だけを固定し、現在の `run_gate()`・`prerelease.history()` を直接呼んだ。ネットワーク・実発注・実台帳への書込みはない。製品の判定関数を写した計算ではない。

| 入力 | 実測 | 結論 |
|---|---|---|
| 設計state3本（異なるHEAD）、承認「巡3・総上限3」、次はコードで新HEAD | `blocked / total_round=4 / 承認済み総上限（3）を超えています` | #37は現在も再現 |
| 同一HEADのコードstate2本、次は新HEAD、履歴節に説明文 | `pass / total_round=2` | Aで見つかった二重計上・説明文停止は現在の通常経路で再現しない。既存 `test_ordinary_parallel_round2`・`test_ordinary_prose_round2` と整合 |
| 上のstate2本を `history(strict=True)` へ渡す（履歴節は空） | `2` | 特例内は依然run単位。実際の集合材料が無いため、これだけで誤計数と断定はしない |
| 上の履歴節に説明文を入れて同じhistoryを呼ぶ | `ValueError: 巡の履歴に解釈できない行があります` | 説明文停止は特例の照合内には残る。特例全体の通過を確認した実験ではない |

再現手順: `PYTHONDONTWRITEBYTECODE=1 python3` で `sys.path.insert(0,'lib')`、上表の `run_id/review_target/kind_label/head_sha/started_at` のstateを作り、`run_gate(target,'.',state,'','',fetch_body=lambda _: body,goal_cut='1件 | 根拠: 設計調査 | 取得日: 2026-11-15',kind_label='コード')` を呼ぶ。`git_remote_repo=lambda _:('example','repo')`、`git_head_sha=lambda _:'new-head'`、target=`issue:example/repo#1`。実験は基点上の挙動観察で、新規検査・C仕様の成功試験ではない。

## 2. 揃えた後の最小案

### 2.1 種別と発注1回

カウンタは変更系列ごとの `設計` と `コード` の2つ。発注時に固定し、コードから設計へ戻っても継続する。issue→PR・切り出し・別枝・名称変更で初期化しない。巡のキーは `(series_id, kind_label, round_id)`。個々の実行は既存 `run_id` のまま区別する。`round_id` は以下の記録を束ねるIDで、任意の同じ文字列だけでは合流させない。

| 発注時に固定する材料 | 現stateに実在するか | 最小の扱い |
|---|---|---|
| target、種別、run_id | ある（`bin/codex-review:318-341`） | そのまま再利用。IDの形式・キー重複・読み取り失敗を検査 |
| 版 | head_sha、content_hashはある。ただしcontent_hashは発注後に計算 | 判定前にSHA＋対象ファイルの実内容hash＋対象一覧hashを固定。未commit差分・対象の入替を識別。送信前に同一性を再確認 |
| 確定したレビュアー集合と構成員 | 無し。reviewerは各runのlabelだけ | round_idごとに構成員IDと各runの割当を送信前に記録。集合は閉じてから送信。順序・秒差で推定しない |
| 系列・前身 | 通常stateの明示series_idは無し。本文とenvの前身、特例裁定にはある | 既存前身グラフを出所に系列を結ぶ。新記録にはseries_idと前身参照を固定 |
| 予約 | A専用 `.reservation` と `fcntl.flock` が既にある（`round_gate.py:1406-1432`） | ロック・予約の既存手段を通常発注にも適用。新サービスを足さない |

同じ対象・同じ版・同じ種別・送信前に確定した同じ集合への複数runは、並行でも逐次でも1巡。確定後の追加、集合の入替、別の版への発注は新しいround_idで次巡。同じSHAでも未commit内容や対象一覧が変われば別版。SHAは出所の固定と送信前照合に使い、加算単位にしない。amendでSHAだけ変わっても、未送信なら0巡のまま対象を確定し直す。送信済み集合への参加は固定した版と照合し、不一致を黙って新巡として送らない。独立した新集合を発注するなら内容が不変でも次巡であり、別版への2発注は当然2巡となる。

起動口の最小インターフェース案: 最初の発注前に共有台帳内へ確定集合レコードを作成し、各起動へそのround_idとmember_idを渡す。レコードは上表の系列/種別/target/版/対象一覧/構成員、固定時刻、状態を持つ。既存の一人発注はsingleton集合を起動口が作る。複数人へ同時発注する場合だけ同じレコードを参照し、通常の別起動を自動合流させない。送信前に構成員ごとのrun_idを予約し、同じmemberの二重送信を拒否する。集合確定をレビュー本数の承認に代用しない。新しい環境変数やCLI引数の名前は実装時に既存口と照合して選び、単なるID文字列を許可根拠にはしない。

新しい集合の最初の予約で1加算し、後続構成員はその巡を使う。確定集合を過去のround_idへ後付けできない。予約→送信→state保存→本文追記の状態を既存台帳内に対応させ、同一系列の再集計と予約はロック内で行う。通常の同時2集合は連番、同一集合は同じ番号。ロックや永続化に失敗したら送信しない。送信した集合は結果ゼロ・timeout・受領拒否でも消費、未送信が証明できた集合だけ取消可能。クラッシュで送信不明なら予約を残し照合まで停止する。

台帳の正規置場は同じ系列で固定し、別state-dirで履歴を空にして新規扱いできないようにする。既存3本上限は安全策として維持し、種別分離に便乗して撤去・拡大しない。これは巡上限と別の発注本数制限である。

### 2.2 読取り・移行・説明文

共通計算は今回種別の総巡、種別別内訳、今回round_id、既知の下限、完全性、不足理由、前身内訳を返す。gate、前置き、点検、stateのround、本文、公開前特例に同じ結果を渡す。前置きだけで再計算しない。

履歴の説明文・空行・表ヘッダは読み飛ばす。数値行やdispatch_id/round_idを持つ行の不正・同IDの版/種別/target矛盾は説明文扱いで捨てず停止する。説明文から承認・発注を生成しない。自由文しかない旧履歴も0巡にはせず、台帳との照合不能を明示する。stateと本文の同じrunは1件、そのrunが属する同じroundは1巡。stateだけに残る発注も消さず、本文だけの外部レビューも照合する。

旧stateは上書きしない。`history_backfill.backfill` の1対1照合を再利用してdispatch_idを補う候補を作り、集合は正本の発注時記録で確定できるものだけ対応表へ追記する。同じSHA、同じ旧round、近い時刻だけでまとめない。集合不明の複数runには1〜run数の幅が残る。正確な新計数は判定不能とし、暫定に各runを1巡とする保守的上限も「確定値」と呼ばない。通常1本だった記録も、state外の構成員が無かった証拠を確認する。

種別欠落は現行の既定「コード」で確定せず、正本行との1対1照合で補う。欠損state、壊れた行、state外のAgent発注、失われた台帳は完全性不足として止め、承認文字列を置いただけで解除しない。新規0巡は履歴なし・前身なしを照合できた系列だけ。これらは移行の停止であり、人間の3巡承認による停止と理由を分ける。

前身は種別別のイベント集合を継承する。本文の継承済み累計を同じ実イベントへ再加算しない。同じ祖先は1回、再帰中の循環と全体の既訪問は分ける。深さ上限・取得失敗の停止を維持。対象を変えても系列を辿れないなら不完全であり0巡にしない。

### 2.3 人間承認の互換と上限

新形式案は同じ承認節に `種別: 設計` または `種別: コード` を記載し、承認巡・未解決blocking・不変条件・残る検証・固定総上限を結び付ける。承認対象種別の総巡にだけ適用。別種別のcapを本文全体のmaxで流用しない。2巡終了時の一括承認を維持し、後続の1本ごとに自動延長しない。

種別なしの既存承認は、#37が許容する互換案のうち「capと承認の存在を両カウンタに適用」を既定案とする。新しい人間の決定が既にあるとは記録しない。選択肢は「旧承認を種別へ補完してから使用」であり、実装レビューで変更されたら承認正規化と試験行を直す。旧承認の原文は保持し、compatibility由来を判定結果に残す。cap3なら各種別の4巡目は止まる。設計3巡の後のコード1巡目を総上限3で止めない。

承認行の「巡N」は総上限ではなく消化数の下限の材料でもある。このNを無条件に両種別へコピーしない。正本履歴/stateにより帰属種別を特定してそのカウンタの下限にする。特定不能なら移行の不足として停止し、下限を黙って捨てない。これにより設計巡3承認がコード巡1を巡3へ持ち上げる再発を防ぐ。これはcap互換とは別の処理。

3巡目以降の人間承認、5巡の上限、前身継承は各カウンタに効く。現行 `decide(6, '裁定: ...')` の通過分岐は既存の別経路として残すが、通常レビュー6巡目の自動許可には使わない。縮小・切り出し（継承）・撤回の人間裁定は既存運用を維持。bypassの権限設計をCで作り替えない。

### 2.4 公開前特例との照合

`prerelease.history()` を別のrun総数計算のまま残すと、種別別gateとの差で特例が不成立になる。Cでは説明文の読み飛ばしとrun→round対応を共通正規化へ寄せ、通常計数と特例の履歴照合へ同じ種別の集合を渡す。厳密照合では全runのID・構成員・版の矛盾を検出し、その上で同じroundを1回とする。`history+1` は新集合開始だけに適用し、同じ集合の後続runでは加算しない。予約とstateの重複も同じrunとして扱う。

既存の `record.kind` を今回種別と照合し、total_capはその種別の固定総上限。旧特例レコードもkind必須なので、保存済みの「同じ系列・固定上限」照合は同じ種別の記録同士に限定し、別種別のcapで拒否/延長しない。kind不明の予約は新正規化で補完できるまで特例不成立。

2ファイルの既定枝blob一致、登録PJ実体、対象版/対象一覧hash、3〜5かつ固定総上限内、blocking無し・前身無し、時刻・操作範囲、bypass併用禁止、送信前再照合は変更しない。通常の有効な人間承認は特例APIより先に判定する。種別も集合も確定できた通常履歴は説明文で停止させない。特例の矛盾は特例不成立として通常判定へ戻し、公開後や別PJを通さない。

本文には各runのdispatch_idとround_idを残し、巡番号が同じ設計/コードや同じ集合内の複数runを区別する。トークン補完は巡番号だけでなくdispatch_id＋種別で行う。旧行の一意対応ができなければ補完せず理由を返す。集合として1巡と表示する場合でも、各runの入力トークンを失わない。

## 3. 完成条件（実装の受入条件）

1. **守る対象**: 同一系列の設計/コード別計数と確定集合による1巡。3巡目以降の人の承認・5巡の上限・変更系列の継承がカウンタごとに効く。公開前特例の条件（2ファイルのblob一致・総上限・bypass併用禁止）を変えない。前置き/保存/判定/履歴/トークン補完が同じrunと巡を指す。
2. **信頼境界**: 発注口の入力・stateと予約・GitHub本文/前身・実対象版/対象一覧・規則取得。自己申告の集合IDや種別だけで過去の消化巡を減らさない。欠落/矛盾/読取失敗/ロック失敗は送信前停止。
3. **対象外**: Dの振り分け配線、AWS/DB、dev/stg/prod操作、bypass権限の刷新、レビュー本数の自動承認、結果の意味の自動裁定、全Agent発注口の新規統合。CLI外の記録は入力の照合対象として残す。
4. **blocking**: 上記①②を破る実行経路、または既存承認が範囲外へ流用される経路。説明文だけを不正入力にして止めることも対象の欠陥。移行に必要な材料不足は判定不能として区別し、根拠なく完了にしない。別系統設計レビュー1巡・[Must]残存中の着手禁止を維持。
5. **検証方法**: §5の正常系通し→境界→状態遷移→パッケージ全体→変異。欠陥を決定論チェックへ翻訳し、陽性対照・陰性①〜④・別種の回避2件を実施。影響は§4の同じsnapshotで新旧を比較。緑のままの有効な変異が1件でもあれば未完了。

## 4. 影響確認と開いている対象への暫定影響

基準時刻は **2026-11-15 07:40:52.360285 JST**（UTC `2026-11-14T22:40:52.360285+00:00`）。7日前の同時刻から基準まで、started_atが両端を含むstateを対象とした。実台帳は読むだけ、設定/資格情報/本文の全量コピーは作らない。

読取5164 state、期間内890、うちissue/pr発注84、target文字列の重複排除42。84件すべてにkind_label/run_id/head_shaがあり、content_hashは83件。round_id/dispatch_group/reviewer_set/series_idは84件すべてで非空値0件。これはキー探索の集計で、既存発注の集合が存在しなかったという意味ではない。

42対象の開閉取得結果は **OPEN 33・MERGED 6・CLOSED 2・取得不能1**。取得終了はUTC `2026-11-14T22:42:01.640644+00:00`（JST 07:42:01）。既存の発注名義の読取設定を使い、auth switchなし。取得不能はOPENへ含めない。

新計数の「止まるようになる／通るようになる／巡が増える／減る／同じ」は**全て未測定**。不明を同じや0件と数えない。製品コードを変えず計数を写すことはできても、欠けた確定集合の出所は作れない。#37の設計→コードは通る方向、同HEADへの後付け集合は増える方向、説明文だけの特例不成立は解消する方向と予想するが、実在のOPEN対象への件数とはしない。

### 再現コマンドと実装後の測り方

対象列挙の再現コマンド（値は必要なキーだけ読む。出力は件数だけ）:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from pathlib import Path
from collections import Counter
from datetime import datetime
end = datetime.fromisoformat('2026-11-14T22:40:52.360285+00:00').timestamp()
c = Counter(); targets = set(); fields = Counter()
for path in (Path.home()/'.codex-watch').glob('*.state'):
    c['all'] += 1
    d = dict(s.split('=',1) for s in path.read_text().splitlines() if '=' in s)
    try: t = float(d.get('started_at','nan'))
    except ValueError: continue
    if not end-7*86400 <= t <= end: continue
    c['recent'] += 1
    target = d.get('review_target','')
    if not target.startswith(('pr:','issue:')): continue
    c['dispatches'] += 1; targets.add(target)
    for k in ('kind_label','run_id','head_sha','content_hash','round_id',
              'dispatch_group','reviewer_set','series_id'):
        fields[k] += bool(d.get(k))
print(dict(c), 'targets',len(targets), dict(fields))
PY
```

これは将来stateが追加/削除されれば変わる。今回の取得は基準時刻と件数を固定した観察で、入力snapshotを保存した完全再現実験ではない。

1. 各targetの期間内最新stateから既存 `github_account` の設定場所を読取用環境へ指定し、`gh issue view N -R OWNER/REPO --json state,body,url` または `gh pr view ... --json state,body,url,headRefOid` でOPENと本文を固定。auth switchや資格情報の表示/コピーはしない。取得不能は別枠。前身も取得する。
2. 選択窓は7日、巡数の入力は全期間のstate・本文・前身・予約。既存impact/compare.pyのtarget重複排除・現在HEAD/新HEADの2条件・fetch_body注入を再利用し、A旧版をロードする部分は使わない。旧=本基点、候補=実装commitを隔離入力で呼ぶ。実 `run_gate` の判定と純粋比較の結果を突き合わせる。
3. 対象ごとの「次の1本」の種別/対象集合は直近runと同じと仮定し、**新しい確定集合への発注**で比較する（既存集合への追加かは別条件）。HEADは最新state作業場所の実HEAD、消失ならPR headRefOid、issueは最終state HEADと明記。未commit内容・対象ファイルが不明なら未知として別枠。新HEAD条件も併記する。
4. 正本の発注開始時記録から各run→集合の対応を補完。復元できないtargetはunknown、仮定で合流しない。確定した対象だけ「止まる=pass→blocked/indeterminate」「通る=逆」「増減=今回種別の巡番号の大小」「同じ=巡と判定が一致」で集計。増減と通過差は重複可、blocked→indeterminate等の残りも別記して総数を照合する。旧は混算、新は今回種別なので比較列に種別も書く。
5. goal-cut/repo照合の条件を揃える。既存3本上限は別理由として含めた最終判定も比較。通常承認と特例利用条件を別列にし、特例の規則読取りは固定証拠へ注入、実発注・本文追記・実予約作成はしない。旧IDの補完も提案ファイルだけ。影響を測り直してから配布判断へ渡す。

## 5. 試験計画（実施は実装の手番）

入力の区分表。期待の出所は今回の依頼・#37・review.md:6とreview-gate:169以降。案の期待は「本設計」と明示し、現在の実装値を正解へ転記しない。全試験は隔離state/偽gh/偽codexで、実LLM・GitHub書込・AWS・DBを呼ばない。

| 入力 | 区分・境目／置く値 | 期待 | 期待の出所 | 大きさ | 試験名案 |
|---|---|---|---|---|---|
| 発注全体 | 正常通し: 設計3巡＋種別なし旧承認cap3→コード新集合1巡 | 発注可、gate/前置き/state/本文がコード1、設計3を保持 | #37・本設計の互換案 | CLI通し（外部fake） | design3_then_code1 |
| コード巡 | 2/3、承認なし | 2は通過、3は停止 | review.md:6 | 関数＋CLI | code3_requires_approval |
| 設計巡・cap | 今回3/4、設計cap3 | 3は通過、4は停止 | 今回の依頼 | 関数 | design_cap3 |
| ハード上限 | 今回4/5/6、cap5・通常承認 | 4/5可、6は通常発注不可 | review.md:6 | 関数＋CLI | per_kind_hard_cap |
| 確定集合 | 同対象・同版・同種別の集合に2runを並行/逐次送信 | 1巡、runは2件 | review-gate:169 | ロックを通すCLI | parallel_fixed_set |
| 版 | 別版への2集合、同SHAで異なる内容hash、異なる対象一覧 | 2巡。古い集合への参加は停止 | 今回の依頼・本設計 | 関数＋CLI | distinct_versions |
| SHAだけの変更 | 内容不変amend、未送信/送信済み | 未送信は再確定して0巡、送信済みは版照合。SHA変更だけで自動加算しない | review-gate:169・本設計 | 関数＋CLI | sha_is_not_round |
| 集合の状態 | 確定後の構成員追加/差替、同版で別round_id | 次巡。旧集合の枠を再利用しない | review-gate:169 | CLI | late_member |
| 履歴の文字 | 正しい行＋説明文・空行・表ヘッダ | 説明文を飛ばし計数可。通常/特例とも一致 | 今回の依頼 | 関数＋特例通し | prose_history |
| 不正な行 | 数値巡行の欠け・同ID別版/別種別 | 説明文として捨てず停止 | 本設計・AのID矛盾防止 | 関数 | malformed_event |
| 承認の種別 | 設計cap3/コードcap5、旧種別なしcap3 | 種別付きは他方へ流用せず、旧capは各カウンタへ互換適用 | #37の選択肢・本設計既定案 | 関数＋CLI | approval_kind_compat |
| 承認の下限 | 設計巡3承認、コード0／承認だけ残り帰属不明 | 前者コード次1、後者移行判定不能 | 本設計 | 関数 | approval_floor_kind |
| 欠け | kind/run/group/版/対象の空・全角空白・改行注入・重複キー | 各必須欄の不正を起動前に拒否 | 信頼境界・本設計 | パラメータ関数＋CLI | missing_identity |
| 継承 | 同種前身2巡＋新1、設計→コード→設計、共通祖先・循環 | 同種3、復帰して継続、祖先1回、循環停止 | #37・本設計 | 関数＋CLI | inherited_counters |
| 時刻 | 固定時刻、7日前の直前/ちょうど/直後、未来/非有限値 | 影響対象の窓のみ変更、巡は全期間。時刻で集合を推定しない | 本設計§4 | 測定器の関数 | impact_window |
| できない操作・合図 | 予約後クラッシュ、state/本文失敗、同時別集合、別state-dir | 未知予約は占有、巡を消さず、二重番号/台帳初期化不可 | 本設計 | プロセス通し・障害注入 | reservation_crash |
| 表示/補完 | 設計1とコード1、同集合2runの異なるtoken値 | 同じ巡でも該当runだけを更新 | 本設計 | backfill関数＋CLI | backfill_by_dispatch |
| 公開前特例 | blob2個一致/片方不一致、cap超過、bypass併用、公開後/別PJ | 一致＋範囲内だけ特例可。全種別で安全策維持 | #38承認不変条件 | 特例通し | prerelease_contract |
| 特例の混在 | 設計/コード各履歴、同集合2run＋state/予約重複 | 今回種別の集合数と判定巡が一致 | 本設計 | 特例通し | prerelease_round_union |

同じ判定側の説明文の言い換えは代表1件。画面・実DB・環境接続の試験は対象外のため足さない。時刻試験は集合判定ではなく測定窓と既存の裁定時刻へ当てる。試験のfixtureはsleepで並行を推測せず、予約確定の合図で順序を制御する。

### 変異の計画

| 種類 | 不変条件を壊す変更案 | 赤にする試験／必要な着弾証跡 |
|---|---|---|
| ①守る処理を消す | 集合のmember照合を削除、または前身加算を消す | late_member / inherited_counters。変更箇所の行traceと実入力IDを記録 |
| ②意味を壊す | kindを無視して混算、集合キーをrun_idにする、capの `>` を `>=` にする | design3_then_code1 / parallel_fixed_set / design_cap3。該当カウンタ/比較の行trace |
| ③入れ替える | 設計/コードのcap、またはbackfill対象runをswap | approval_kind_compat / backfill_by_dispatch。読まれた種別と更新runのtrace |
| ④検査そのものを無効化 | validatorを常時成功、または試験をskip/常時緑化 | 不正入力の期待失敗と、期待試験ID・収集件数・skip差分を照合する実行器で欠落を検出。0件実行を成功扱いしない |
| 陽性対照 | state列挙順、集合memberの記載順だけ変更 | 同じ結果で緑。ID/集合の意味が不変である差分とtraceを残す |

別種の回避を少なくとも2件試す: (a) 未commit内容/対象一覧だけ変えて同じround_idを再利用する「対象のすり替え」、(b) 予約後クラッシュと別state-dir起動を組み合わせる「永続化・競合」。上表と異なる失敗の種類として実経路へ当てる。blob片方の不一致、bypass併用、下限だけ残る旧承認も安全策ごとに変異を追加する。

実装と試験をcommitした状態から、作業場所内の隔離コピーで1変異ずつ行う。(a) 不変条件を壊すdiffと前後hash、(b) 実際にその分岐が読まれた標準 `trace` / シェルtraceを**別々の証跡**にする。構文エラー・無関係な赤・未着弾は検出成功と数えない。陽性対照1件以上、①〜④各1件以上、回避2件以上を満たし、有効な変異が緑なら未完了。元へ戻す操作は隔離ファイルのバイト復元だけ（reset/checkout等なし）。最後に原本の `git diff` とstatusの空を確認する。

既存 `tests/check_prerelease_fixA_mutations.py` のarchive、diff保存、実行行trace、終了値照合を再利用する。過去版の未commit overlayや古い文字列アンカーは使わず、Cのcommitと試験IDへ合わせる。skip/収集件数の検証はこの実行器の不足分として足し、別の試験基盤は作らない。

試験は `.tmp/round-count-c/tmp` を作り、`GIT_CEILING_DIRECTORIES="$PWD" TMPDIR="$PWD/.tmp/round-count-c/tmp" PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider --basetemp="$PWD/.tmp/round-count-c/pytest"` でパッケージ全体。Git管理外を想定するfixtureから親の実リポジトリを探索させない。収集/成功/失敗/skip件数とscopeを記録し、依存不足ならinstallせず未実行。赤を「前から」と呼ぶのは指定本線で同じ試験を実行できた場合だけ。今回の設計完了はC実装や変異検証の完了ではない。

## 6. 影響箇所・7段・任意追加

追加前の探索: `git grep -n -E 'round_id|dispatch_group|reviewer_set' -- lib bin tests` は **0行**。state実物の非空件数は§4。`git grep -n -E 'reservation|fcntl|flock' -- lib bin tests` でAの予約/lockが見つかったため再利用する。既存の `kind_label` filter、前身走査、行render、補完も使う。

今回変えた製品関数・値は0件。実装時の呼出し元確認は `git grep -n -E 'ledger_head_shas_for_target|target_total_rounds|parse_approval_rounds|parse_total_cap|render_round_row|backfill_measuring_row|prerelease\.history|pre\.history' -- lib bin tests`（基点63行）で全参照を列挙し直す。主要な本番経路と必要な確認は以下。

| 呼出し元 | 実装時に確かめること |
|---|---|
| `round_gate.py:484,617,655,657,666,1269` | own/前身/再帰が同じ種別の集合を数え、祖先重複と真の循環を区別 |
| `bin/codex-review:122` | 前置き/点検がgate結果を使い、再計算の食い違いなし |
| `round_gate.py:295,697,698` | 承認の下限とcapを分離し、種別/旧互換を照合 |
| `prerelease.py:178` | history+1固定を集合開始/継続へ分け、安全条件は維持 |
| `round_gate.py:1334` | renderへ種別とrun/集合ID、本文の重複追記を抑止 |
| `round_gate.py:1041,1389` | retry/backfillとも同じrunを更新。旧行曖昧時は更新しない |
| `history_backfill.py:14` と `bin/codex-history-backfill` | 読取だけの候補出力を維持。集合を推定で発行しない |
| `round_gate.py:1406-1432`、`bin/codex-review:259-344` | 判定/予約/起動/stateの順序、実LLMを使わないCLI通しで競合/クラッシュを検証 |

直接呼出し試験は上記grep結果を試験名へ突き合わせる。特に `test_review_must_criteria.py:113` の「総上限は混算2」という期待、同HEADの全runを束ねる `test_round_gate.py:163-178,209` は旧仕様であり、Cでは確定集合のfixtureへ変更する。単に件数を合わせるassert更新にしない。

7段は項目ごとに必要性→既存→標準ライブラリ→プラットフォーム→既存依存→1行→最小コードの順。新依存は不要。

| 仕組み/章/項目 | 止まる段と理由 |
|---|---|
| §1現状・再現 | ㋐明示依頼、㋑既存run_gate/history/試験とA影響資料で止まる。新しい製品検査なし |
| §2.1種別計数 | ㋐#37再現、㋑既存kind filter/台帳/前身を再利用。㋒標準集合で表現、㋓〜㋔既存手段だけ、㋕1行では境界を保てず、㋖共通正規化と計数の最小変更 |
| §2.1集合ID/確定 | ㋐明示の1巡単位、㋑記録0件のため既存run_idだけでは不足、㋒JSONと集合で止まる。個別runと集合の対応だけ追加し汎用workflowを作らない |
| §2.1予約/競合 | ㋐並行時の過少計数防止、㋑Aのflock/予約、㋒fcntl/osの既存手段で止まる。分散ロックなし |
| §2.2移行/説明文/継承 | ㋐明示依頼と安全境界、㋑history_backfill/既存前身/履歴を再利用、㋒辞書・集合・正規表現で止まる。推測による集合復元なし |
| §2.3承認互換 | ㋐明示依頼、㋑承認とcap既存関数を改修、㋒節と種別の関連付けで止まる。承認の真正性を認証する新制度なし |
| §2.4特例/補完 | ㋐安全条件維持、㋑既存evaluate/ID提案/backfillを再利用して止まる。規則取得/特例を再実装しない |
| §3完成条件 | ㋐明示依頼、㋑前身§6と今回の不変条件を具体化して止まる。ゲートを削らない |
| §4影響 | ㋐明示依頼、㋑既存compare.pyの方式、㋒標準pathlib/datetime/Counter、㋓gh読取で止まる。欠損材料を作らない |
| §5試験/変異 | ㋐削減不可、㋑既存pytest/fake/変異手順、㋒標準traceで止まる。新試験基盤は作らない |
| §6影響先/7段・§7報告 | ㋐明示依頼、㋑git grepと既存手順の記録で止まる |
| 任意追加 | ㋐推測需要なので作らない: 独立した集合の内容類似による自動合流、旧集合の時刻推定、全Agent発注口の統合、自動承認、ダッシュボード。必要が実証されれば別課題で扱う |

最小案にも信頼境界検査、予約のデータ消失防止、安全策、別系統設計レビュー1巡、[Must]残存中の着手禁止、欠陥の決定論チェックへの翻訳、変異確認を含む。任意追加へ追い出さない。

## 7. 今回の検証記録・環境差・引継ぎ

パッケージ全体の初回: 上記コマンドから `GIT_CEILING_DIRECTORIES` と `TMPDIR` を省いた実行は **629 passed・95 failed・5 skipped、729件、315.08秒**。親repo探索によりGit管理外fixtureが実repoと認識され、名義宣言を拾ったことやoutside条件の崩れを失敗出力と `prepare_codex_github_account` の経路で確認した。前身の `docs/review-preface-kind-rounds.md` にある探索上限を付けた条件で再実行し、その結果を後記する。本線との比較は行っておらず「前からある赤」ではない。

§5のコマンドでの再実行は **724 passed・0 failed・5 skipped、729件、284.96秒**。範囲は `tests/` を含むパッケージ全体の自動収集。製品・試験の変更なしで試験環境の探索上限だけを修正した。ログは作業場所内 `.tmp/round-count-c/{pytest.log,pytest-isolated.log}`。試験用生成ディレクトリは実行後に削除し、文書だけをcommit対象とする。`git diff --cached --check` は成功。

commitは **未作成**。`docs(rounds): design per-kind review round counting`（本文 `#38 #37`）を試みたが、PreToolUseの名義確認hookが期待 `todoroki-godai` に対し検出 `matsukaze-minden` としてコマンド実行前に拒否した。auth switch・hook迂回は行わず、依頼の例外どおり文書を残して調整役のcommitへ引き継ぐ。実装の着手許可やレビュー済みを意味しない。

新規試験0件、製品変更0件。C実装の変異・実環境発注・DB試験は未実行（設計手番、DB接続なし）。別系統レビューも未実施。今回の実物確認と既存試験成功をC実装済みの証拠にしない。

| 環境 | 経路・設定・データの違い／今回の扱い |
|---|---|
| ローカル | PJ共通stateとGitHub本文が入力。作業場所内の架空台帳で関数を実行。実台帳は読取のみ |
| dev | 巡数の環境固有分岐は無し。今回接続・読取・書込なし |
| stg | 巡数の環境固有分岐は無し。今回接続・書込なし |
| prod | 巡数の環境固有分岐は無し。今回接続・操作なし |

範囲外の候補名: 6巡以上の裁定文字列の権限確認、bypass権限の見直し、CLI外発注の全口接続。今回直さない。

指定queue置場 `/Users/matsukaze-takashi/updater/updater-index/_work/notes/codex-queue/` は実行環境の書込み許可外。結果/次回依頼の2ファイルは作成できない。権限変更や別名のqueueファイルを作らず、以下の引継ぎ内容を本書に残す。最終報告にも未作成を明記する。

次回の「今回の作業」候補:

> run名: round-count-c-design-review。作業場所: `/Users/matsukaze-takashi/matsukaze-utils/codex-watch/_wt.noindex/round-count-c`。`docs/design/round-count-c.md` の別系統設計レビュー1巡を、依頼元が既存の承認範囲を確認して手配する。集合の確定/旧承認の互換/公開前特例/移行未知/計数と保存の一致を確認し、指摘ごとに基点とfile:lineを記録する。製品コードを変更しない。終了条件: 受領照合と[Must]の記録、実装着手可否の判定。次のrun名: round-count-c-impl（設計[Must]0確認後のみ）。
