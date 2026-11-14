# 公開前の裁定・発注単位の巡数・レビュー振り分けの接続設計

作成日: 2026-11-13。課題: todoroki-godai/codex-watch#38。run: review-complete-design。
対象基点: `bdb4d62f80e32eae37be8fcf8d3d11e11e339bae`（開始時の HEAD と origin/main が一致）。枝: `feat/review-gate-prerelease`。
本書は設計だけであり、製品コード・試験・配布先は変更しない。A → C → D の順に同じ枝へ積む。設計レビューは依頼元が別途手配し、今回 LLM を起動しない。

## 1. 読んだもの・決定の範囲

以下の `audit/` は `/Users/matsukaze-takashi/updater/updater-index/_wt.noindex/rev9-audit/`、`routing/` は `/Users/matsukaze-takashi/updater/updater-index/_wt.noindex/review-routing/_work/notes/review-routing/`、`共有/` は `/Users/matsukaze-takashi/updater/updater-index/_work/notes/` を指す。codex-watch の行番号は上記基点。

| 必須の参照 | 読んだ出所・扱い |
|---|---|
| 段取り表の該当行 | 無し（T番号の指定がなく、製品の段取り表を変更しない）。担当割当ては `共有/rev9-review-history.md:275`、作業順は #38 本文「順番」 |
| 本人の決定 | 今回の依頼にある中継原文「A 巡3の関門を公開前の決めに合わせる (Recommended), C 巡の数え方を揃える, D レビューの振り分けをつなぐ」。main-index への直接入力を中継、refactor 受領 2026-11-13 16:22:03 JST。#38 本文でも A・C・D の了承を確認。問いの全文は今回提示されていないため創作しない |
| 見本 HTML | 無し（発注の関門の設計で、画面を変更しない） |
| 前身の分析 | `audit/.tmp/review-analysis/REPORT.md`、特に食い違い表・A〜D・入力区分表（:118-134）・未確認事項。144発注・無駄6件は報告の分析値で、今回再集計していない |
| 前身の設計・巡 | `docs/review-preface-kind-rounds.md`、`routing/design.md`、`routing/skill-src/routing.md`、`routing/round3-record.md:47-65`。巡3の 0/0 と発注時ハッシュ照合未充足を分ける |
| PJの決め | `audit/.claude/rules/pre-release-proceed-with-recommendation.md:3-10`、`dev-standing-approval.md:7`。さらにローカル origin/main `c7c7772ec79806a82943e95bf247d6a85bc3af09` の両ファイルを `git show` で読んだ。fetchなしであり、リモート最新の公開状態を確認したとはしない |
| 通常運用 | `~/.claude/rules/review.md`、`~/.claude/skills/review-gate/SKILL.md`。本数・巡数・別系統・受領・人間承認の既存経路を維持 |
| 接続準備 | `共有/review-routing/{activation-3points.md,activation-prep-prompt.md,mutation-only-prompt.md}`、`routing/activation/REPORT.md`、適用・逆差分2組、`routing/skill-src/{adapter.py,route.mjs,limits.json}`。routing作業枝の読取時HEADは `7a7829f89c4d7e01eb257faf77c8ae298e7674fc`、statusは空 |
| 試験設計 | `audit/.claude/skills/test-design/SKILL.md`。正常系の通しを先頭にし、数字・継ぎ目・時刻・できない操作・文字と欠け・合図を区分する |
| 起動口 | `lib/round_gate.py`、`bin/codex-review`、README全体、`tests/conftest.py`、`tests/test_codex_review_cli.py` と既存の巡数・種別・受領試験の参照箇所 |
| GitHub | `gh issue view 38 -R todoroki-godai/codex-watch` は取得成功。`gh issue view 2006 -R min-sys/updater-index --comments` は repository 解決エラーで未取得。名義変更なし |

#2006 の最新本文・コメントは未確認。選択肢は (1) 依頼元が現在の本文とコメントを渡す (2) 既存の読み取り権限が復旧してから再取得する。既定案は、ローカル実物に基づく以下の設計までを残し、D の実装・配布・有効化へ進む前に取得版との差分を照合すること。資料に残る過去の試験成功を今回の実測にしない。

## 2. A: 公開前の裁定主体を既存判定へ渡す

### 2.1 信頼する出所

許可対象は当面 `min-sys/updater-index` のみ。発注対象の repo と実 workdir の Git repo を既存 `git_remote_repo()` で照合するだけでは、origin を付け替えた別PJを識別できない。導入側のレビュー済み固定登録に「repo slug・正規化した Git common directory・規則パス・解釈可能な規則blobのハッシュ」を結び付ける。worktree のパス名、package名、依頼文、環境変数だけでは登録を作成・変更できない。共有側の登録変更はこのPJの裁定の対象外で、通常の人間承認を受ける。

規則は作業枝のファイルでなく、GitHub の当該 repo の既定枝が指す commit を読み取りAPIで確認し、その固定commitの追跡blobを読む。既存 subprocess と Git の `show <固定SHA>:<固定パス>` を使い、commitがローカルに無ければ取得不能として止める。既定枝の名前を環境変数から採らない。ローカル origin/main だけで公開前と確定しない。API失敗・既定枝不明・規則未導入・削除・未知の規則版・通常ファイルでないblobは特例不成立。読み取ったSHAとblob hashを判定結果に残す。

既存Markdownを曖昧な語の一致で解釈しない。初回対応は既定枝上の2つの規則の既知blobを固定登録と照合し、その既知版の意味に限定する。変更された版は再確認するまで自動許可しない。新しい汎用ルール言語やLLM判定は作らない。公開終了は `dev-standing-approval.md:7` の「公開日・本人原文・受領時刻の追記PRが本線入り」で判定し、既知の公開前版から変わって読めない場合も通常承認へ戻す。過去の公開前blobを作業枝へコピーしても通らない。

判定直前と送信直前で既定枝先頭・対象版・裁定記録の同一性を再照合する。変わっていれば再判定し、通信不能なら送信しない。これは確認時点の保証であり、送信後の本線更新との完全な原子性は主張しない。受領結果にも判定時点を残す。

### 2.2 適用範囲と裁定記録

初回の自動許可範囲は、登録されたPJ内の成果物を対象にするローカルの読み取りレビュー発注に絞る。`-s read-only` の起動、実際の対象ファイル集合と実体パス、系列の基点からの変更一覧を照合する。外向きsymlink・別repo・共有物の変更を含む集合は対象外。`scope=local` や `reversible=true` という申告だけを証明にしない。指定範囲が依頼文と矛盾する、対象が列挙できない、操作に可逆性の根拠がない場合は止める。dev操作自体への常時承認やstg/prod操作への許可は発行しない。本番向けソースを読むことと本番へ接続することは区別する。

採用案・理由は既存のPR/issue本文、PR/issueがない場合はPJ規則が許す追跡可能な作業記録から取得する。新しい環境変数は記録の参照先を渡すだけで、許可そのものを渡さない。対象が `none:` のprobe・既存bypassはこの特例の対象にしない。

最低限の裁定レコード（新規JSON欄は実装案。PJ規則の意味を厳密に受け渡すための表現）:

| 項目 | 確認する条件 |
|---|---|
| 対象 | repo、系列ID、target、設計/コード、対象SHA、内容ハッシュ、対象一覧ハッシュ、前身ID、今回の発注IDが現在の発注と一致 |
| 権限の出所 | `authority=project_prerelease`、規則パス、既定枝commit、blob hash、取得時刻。`human` と偽記しない |
| 採用案 | 何を追加確認するか、採用理由、戻し先と費用、発注理由と既存の巡の履歴への参照。空白だけを不可とする |
| 判断時刻 | timezone必須のISO 8601（例 `2026-11-13T16:22:03+09:00`）。UTCへ正規化。無効日・timezone欠落・未来時刻を拒否。判断時刻 ≤ 判定時刻 ≤ 送信前再確認時刻 |
| 一括材料 | 未解決blocking欠陥（無しも明記）・不変条件・残る検証項目・総上限を同じ裁定へ結び付ける。欠落と空集合を区別 |
| 総上限 | 整数で3〜5、今回巡数以上。2巡終了時の一括裁定で固定し、毎回の「もう1巡」へ読み替えない。期限や範囲を変える場合は再裁定の履歴を残す |

構造の検査は「理由の正しさ」「人間の承認が本物であること」を認証しない。規則を読む導入側と正本取得担当が信頼境界。記録は正本URL/commit・取得時刻・本文ハッシュを固定し、渡されたJSONと取得した実体の一致も検査する。ローカル記録も追跡blobと取得元を要求し、書きかけの自己申告ファイルを権限の根拠にしない。

### 2.3 判定の分岐

既存 `decide()` に検証済みの裁定文脈を任意引数として渡す。文脈なしの呼出しは既存の人間承認経路のままとする。API/Git/ファイルI/Oは `run_gate()` 側、判定は純粋関数に分離する。

2026-11-13 本人決定（#38、18:46:32 JST受領）によるA直し: 通常経路の巡数は本体 `bdb4d62` の `target_total_rounds()` のままとする。同一HEADの並行発注は台帳で束ね、本文の承認巡・前身の既存判定を維持する。Aで足した「本文履歴とstateの和集合＋今回1」による上書きと、その解析失敗による通常経路の停止を外す。Aの目的には不要で、並行発注の二重計上・履歴節の説明文による停止を生むため、パーサの高機能化はしない。

履歴の厳密な照合は `prerelease_record` を指定し、通常判定が通らない場合の `prerelease.evaluate()` 内だけに残す。本文・state・予約を発注IDで照合し、同IDの食い違い行・壊れた行・ID欠落・判定巡との不一致によって巡を少なく数えて特例を許可しない。解析不能は特例不成立として元の通常判定を返す。既存の有効な人間承認は履歴解析や規則APIを呼ぶ前に通し、特例の不成立で停止させない。`history_round` は特例の通過時だけ設定し、通常の前置きは本体と同じ台帳計数に戻す。第3章のCは後続の別作業であり、このA直しで通常経路へ導入しない。

| 状態 | 判定 |
|---|---|
| 巡1〜2 | 既存経路。ただし種別・履歴不明などCの不成立を通過扱いにしない |
| 巡3〜5、通常の人間承認と総上限あり | 既存経路を維持。PJ裁定の利用に勝手に書き換えない |
| 巡3〜5、人間承認なし、2.1・2.2をすべて満たす | PJ裁定として通過し、採用案・理由・判断時刻・総上限・根拠版を同じ発注へ記録 |
| 別PJ・公開後・共有物変更・不可逆・本人の明示確認対象 | 特例を適用せず通常の人間承認を要求。承認がなければ blocked |
| 決め未導入、読取不能、未知版、証拠の欠落・矛盾 | 自動許可しない。既存の有効な人間承認があれば通常経路へ、なければ理由付き停止。Cの履歴不明は承認文字列だけで解除しない |
| 巡5到達後 | 縮小／前身継承で切り出し／撤回して再設計の3択を記録。blockingを押し込まない。マージは人間判断のまま |
| 巡6以上 | PJ特例では通常レビューを発注しない。既存の人間裁定経路は残すが、`裁定:` の語だけを自動特例へ流用しない |

既存 `CODEX_REVIEW_NO_GATE` は理由文字列だけで全巡数ゲートを迂回する（`run_gate:1157` 付近）。これをPJ許可の出所にしない。Aで有効になる自動特例の入口ではこの指定と同時利用を拒否し、bypassの返却を `project_prerelease` と記録できないようにする。既存の通常bypassそのものの廃止・権限強化は本設計外で、現状の限界として残す。

## 3. C: 発注イベントと設計／コードで数える

### 3.1 単位と共通の計算結果

同一変更系列・同一種別について、独立した発注1回を1巡とする。同じHEADでも別runなら次巡。結果の続きを受け取るだけなら同じ発注ID、同じレビュアーへの解消確認を新たに頼むなら別ID。前置き・点検・総上限・state・本文行に同じ計算結果を使い、前置きだけで再計算しない。

`series_id + kind + dispatch_id` を計数のキーとし、SHAを重複排除キーから外す。設計→コードの初回はコード巡1、同種の前身2発注＋今回1発注は巡3。issue→PR・改名・別枝・載せ替え・切り出しで新系列にしない。前身と対象の対応を取得した正本に固定し、envの前身指定は追加照合用とする。前身指定を省略しただけで継承を消せない。

発注前に拒否された試行・自己点検・進捗連絡は数えない。送信後の失敗・timeout・受領拒否は1巡を消費する。プロセスが生きている発注は結果未着でも予約済みとして上限を占める。空のreportだけで発注を取り消さない。既存 `dispatch_produced_nothing()` の「死亡＋出力なし」は別の同一HEAD発注抑制の既存仕様であり、Cの巡数を減らす根拠には使わない。

`target_total_rounds()` の結果を、種別ごとの「完了発注数・未確定/予約数・今回巡番号・既知の下限・完全性・前身内訳」にする。既存JSONの `total_round` は今回種別の総巡番号を維持し、別欄で `round_schema_version` と `kind_label` を明示する。前置きと本文も同じ `total_round` を参照する。

### 3.2 旧stateと前身の移行

旧stateを書き換えず、新読取り層で正規化する。既存のファイルstem/run_idを発注IDに利用し、同じstateと本文とセッション記録の重複をIDで束ねる。新stateは版・系列・種別・発注IDを明示。保存されている旧 `round` は消さず `legacy_round` 相当の出所として説明する。

| 旧記録 | 読み替えと停止条件 |
|---|---|
| 同じHEADに異なるrunが2件 | 2発注。旧distinct HEAD数が1でも縮めない |
| kind欠落 | 旧実装の「コード」既定を自動適用しない。本文の発注行・起動記録で当該runの種別を照合し、確認済み補完レコードを追記。判別不能なら種別不明として停止 |
| head欠落・不正な時刻・破損/読めないstate | 除外して0にしない。発注の存在を残し不完全として停止。承認番号だけで完全性を作らない |
| stateディレクトリ欠落/空 | 新規と記録消失を区別。正本の全履歴・セッション内発注・前身なしの明示を照合できた新系列だけ0発注から開始。取得失敗を空履歴にしない |
| 承認行が示す巡が台帳より多い | `max` による下限維持。種別や対応が不明ならその値を設計/コードへ勝手に配分せず、補完まで停止。過去の「総上限」と「消化済み巡数」を混同しない |
| 前身本文に設計K/コードMの継承行 | 種別別に取り込む。前身の実イベント集合と継承済み累計を足して二重計数しない。記録の下限を割る移行は禁止 |
| 複数前身・同じ祖先 | 全体の既訪問集合と再帰中の循環検出を分け、共有祖先は1回だけ数える。真の循環・MAX_CHAIN_DEPTH超・別PJ前身・取得失敗は停止 |
| state外のAgent/Task/再発注 | 取得した起動記録から発注ID付きで補完。続きを送るだけの記録は同じIDへ対応。対応不能は停止。CLIだけのstateで全レビューを数えたとはしない |

補完は元の出所・取得時刻・補完理由を残す追記とし、欠けを想像で埋めない。正本の前身グラフと発注履歴が完全と確認できるまで、新旧の曖昧な値の小さい方を選ばない。移行直後に止まる系列は、理由と不足IDを出して手動照合へ返す。

### 3.3 同時発注と記録

現状は gate後に起動し、その後でstateを書くため、同時の2発注が同じ次巡を見る余地がある。標準 `fcntl.flock` による系列単位のロックを、共有state置場の固定位置に置く。ロック下で種別の再集計・予約ID/巡番号の一時ファイルからのatomic renameを行い、送信と送信結果の確定まで対応付ける。別state-dirを指定しただけで同一系列の計数を分離しないよう、導入登録の正規台帳との一致を確認する。

予約は試行記録であり、未送信が確定した取消は巡にしない。クラッシュで送信済みか不明なら予約を占有したまま停止し、起動記録照合まで再送しない。送信後にstate更新・本文追記が失敗しても発注は消えない。ロック取得不能・書込み失敗・破損した予約は起動前に停止する。読み取り専用のgate-checkは予約せず予測を返し、実発注の予約時に再計算する。

本文行には発注IDを付け、`backfill_measuring_row()` の更新キーを巡番号だけから「発注ID＋種別」にする。設計巡1とコード巡1、同一秒の発注でも別行を更新する。旧行は種別・時刻・SHA・レビュアーから一意に対応できる場合だけ更新し、複数候補なら停止する。旧行を消して書き直さない。

`MAX_SAME_HEAD_DISPATCHES=3` の抑制は別の安全策として残す。巡数と同一HEAD本数は別欄・別理由で示す。HEADを進めても系列の巡数は戻らない。通常2巡・上限5巡・本数承認・別系統・未解決Mustの扱いは維持する。

## 4. D: 既存部品を段階的につなぐ

### 4.1 再利用と契約の衝突

`routing/skill-src/adapter.py:15` に全体30秒の監督があり、`route.mjs:246` が5段の判定、`ledger.mjs` が集計を担う。既存adapterは終了0・5段がすべてtrue・stopped_atなしを突き合わせる。新しい監督器や判定器をcodex-watchに複製しない。

ただし #2006 の `routing.md` は「固定した複数レビュアー集合を1イベント」と記すのに対し、Cは発注1回を1巡にする。接続時には **Cのdispatch_idを発注台帳、Dのevent_idを振り分けの評価イベントとして区別**し、各イベントへ対応するdispatch_id配列を記録する。個別発注をDの集合イベントで重複排除して巡を減らさない。同一イベントに複数の受領結果がある間は、族タグの和が確定するまで次の評価へ進めず、pendingをreceivedにしない。Dの語彙をCの巡数へそのまま流用しない。

`REVIEW_GATE_RECORD` は参照先であり認証ではない。CLIの実workdir・kind・固定版・前身・発注ID・正本の取得内容をCの結果と照合して作る。Cの内容ハッシュ（作業木全体の既存レシピ）とDの対象集合ハッシュは定義が違うため別欄で保持し、それぞれの既存関数で再計算する。文字列一致だけで相互代用しない。履歴の完全性をDのJSON申告だけで保証しない。

### 4.2 有効化の順序

| 段階 | やること | 次段へ進める条件 |
|---|---|---|
| D0 接続なし（既定） | 現状の発注口を維持し、配布候補と版だけ固定。登録空をdisabledスイッチにしない | #2006最新本文・コメント再取得とローカル版の照合、設計レビュー、C/DのID対応を確定 |
| D1 非送信の照合 | `activation/verify-activation.sh` と適用・逆差分を現在のA/C積上げ版に当て直す。送信命令を実行コードから除いたコピーで両口を確認 | 正常、必須不足、30秒timeout、追加呼出し解除後の復旧を両口で確認。旧ゲートを固定応答にする前身試験だけではA/C統合の成功にしない |
| D2 登録と実効検査の準備 | PJの追跡済み対応表・canonical_testをcommitし、登録hashを固定。本線起点worktreeにも届くことを確認 | PJ全体検査 `pnpm test` → record-run → turbo の全package展開と設定解決が接続済み。未対応ラッパーを部分緑へ読み替えない |
| D3 PJ限定の接続 | 配布先の部品・設定・説明を同じ版で揃えてから、登録されたPJだけCLIと既存対象hookへ接続 | 両口が同じ記録契約を使い、起動前に必須判定を行う。失敗・空出力・未知判定・時間切れは送信しない |
| D4 観測と復旧 | 正常なコードレビューの通過も確認し、停止理由と既存経路への戻し差分を記録 | 制御試験と実利用の証拠を分ける。実利用の効果を試験成功から推定しない |

有効化の状態は共有側のレビュー済み設定でPJの実体に結び付ける。環境変数によるoffや「登録が空なら全員通す」を作らない。非対象PJにはこの新しい呼出しを追加しない。対象PJで enabled とした後に部品や登録が欠けたら止める。D2未達ならD3へ進めない。設計だけ先に有効化してコードを後回しにすると同じ系列が途中で止まるため、原則は設計/コードを一組で準備する。

既存の登録空の挙動は、分岐3が通ってもコードの関門Bで緑なし/正規検査場所なしとして止まる（`route.mjs:299-319`）。設計の空greensが通ることを有効化準備完了の根拠にしない。`limits.json` を空に戻す・adapterだけ削除する復旧は禁止。呼出しと説明への追加参照を逆差分で外し、既存の関門を残す。履歴・裁定・巡数は消さない。

### 4.3 発注口と配布候補

CLIは `bin/codex-review:254` の送信直前、既存点検の後に既存adapterを呼ぶ。適用候補は `routing/activation/patches/codex-review.apply.patch`、逆差分も既存。A/Cで前後が変わるので現在の基点へ再生成し、無条件の1行追加をそのまま全PJへ配布しない。

もう一つは `~/.claude/hooks/guard-impl-worker-routing.py:251-254` の既存tacchi点検後。既存の対象分岐は :248-249。前身patchのhelperは例外をFalseへ閉じるが、既存hook外側の例外処理でfail-openに戻らないかも通しで確かめる。このhookはtacchi経路の接続であり、すべてのAgent/Taskに接続したとは言わない。Codexモードで使う他のセッション内発注口は所在を確定するまで未接続と記録する。

今回変更しないPJ外の候補一覧:

| 候補 | 後続担当の作業 |
|---|---|
| `~/.claude/skills/review-gate/{SKILL.md,routing.md,adapter.py,route.mjs,limits.json,route.test.mjs}` | 既存部品の配布・参照・固定版/登録の一致確認 |
| 同 `{ledger.mjs,ledger.md,ledger.test.mjs}` | 手動集計の配布。集計失敗を自動で発注許可にしない |
| `~/.claude/hooks/guard-impl-worker-routing.py` | 既存対象だけへの接続・逆差分 |
| `~/.claude/skills/review-gate/{design.md,code.md}`、共通review規則 | Aの権限出所とCの発注単位の説明を整合。本人承認経路は残す |
| updater-index `.claude/review-plugins/*.json` と全体検査の記録器/展開器 | 対応表とcanonical_testの準備。対象ファイルは後続の割当てで確定 |

## 5. 変更候補・呼出し元・重なり

### 5.1 積む順とファイル

| ファイル | A | C | D | 積み方 |
|---|---|---|---|---|
| `lib/round_gate.py` | 規則取得・裁定検証・decide接続・出所JSON | 種別/発注集計・移行・前身・行ID・予約 | 記録との一致確認で再利用 | A → C。Dに判定ロジックを複製しない |
| `bin/codex-review` | 文脈受渡し・送信前の再確認・出所保存 | 種別をgateへ渡す、同じ巡数を表示/保存、予約と起動の対応 | 送信直前のadapter呼出し | A → C → D。送信位置を各段で再確認 |
| `tests/test_round_gate.py` | 許可範囲と通常承認 | 発注集計・移行・前身・記録の対応 | C/D記録照合 | 同順で既存の試験を拡張 |
| `tests/test_codex_review_cli.py` | 実配線と未送信 | 同時発注/保存/前置きの一致 | adapter接続・復旧 | fakeの送信境界を使う |
| `tests/test_review_must_criteria.py`、`tests/test_preview_checks.py` | 既存ゲートを維持 | 同じHEADが同巡という旧期待と前置き契約を更新 | 点検前後の順序維持 | Cで変更。Must基準の内容は変更しない |
| `README.md`、`docs/review-preface-kind-rounds.md`、`docs/preview-checks.md` | 特例の範囲と通常経路 | 発注/種別/前身/移行の説明 | 導入段階・失敗/復旧 | 実装の最終挙動と同じ便で更新 |
| `evidence/check_review_preface_mutations.py` | 既存oracle再利用 | HEAD束ねを守る変異を、新しい不変条件に更新 | 統合証跡へ参照 | 過去JSONを新仕様の成功証拠にしない |
| PJ外の配布先・#2006の部品 | 登録だけ後続候補 | ID対応の契約整合 | 第4章の別手番 | 今回もA/C実装手番も無断で変更しない |

AのcommitだけではCの過小計数が残るため「仕組み完成」としない。Aを先にレビュー可能な単位で積み、Cの移行と通し試験まで終えてから配布候補とする。Dは登録・全体検査展開・二つの発注口の準備が揃うまで接続なし。

### 5.2 変える関数と製品内の呼出し元（基点の全箇所）

探索: `git grep -n -E 'ledger_head_shas_for_target\(|ledger_own_round\(|ledger_own_round_for_predecessor\(|target_total_rounds\(|decide\(|run_gate\(|record_round\(|render_round_row\(|backfill_measuring_row\(|body_own_round\(|parse_approval_rounds\(|build_arg_parser\(' -- lib bin`。
定義・コメントを除いた呼出しは下表。新規の規則ローダー/裁定validator/予約helperの呼出し元はrun_gateと送信前のCLIに限定する。

| 変更候補（定義） | 現在の呼出し元 | 壊さないための確認 |
|---|---|---|
| `ledger_head_shas_for_target:444` | `round_gate.py:483,617,653` | 新しい発注読取りへ集約し、旧distinct HEAD用途を取り残さない |
| `ledger_own_round:478` | `bin/codex-review:122` | 再計算を外しgateの種別別結果を使用 |
| `ledger_own_round_for_predecessor:614` | `round_gate.py:651` | 同種の発注ID集合へ変更 |
| `target_total_rounds:623` | 自身 `:666`、`run_gate:1257` | kindを再帰まで渡す。共有祖先・循環・深さの検査 |
| `body_own_round:294` / `parse_approval_rounds:279` | 前者 `:671`、後者 `:296,693` | 旧承認による下限を保ち、種別不明は停止 |
| `decide:688` | `run_gate:1260` | 文脈省略の人間承認を維持、PJ文脈は検証済みのみ |
| `run_gate:1106` | `main:1374` | CLIからkind/裁定参照を渡し、エラーのJSON/終了状態を維持 |
| `build_arg_parser:1055` | `main:1369` | gate引数追加。他のsubcommandは現契約を保つ |
| `render_round_row:736` | `record_round:1305` | 発注ID・種別を行へ固定 |
| `record_round:1278` | `main:1395`、シェル `bin/codex-review:340` | 起動済みの発注を同じ予約IDで追記、失敗でも発注を消さない |
| `backfill_measuring_row:807` | `retry_pending_backfills:1037`、`backfill_one:1359` | 両方で発注ID/種別を渡す。旧行曖昧時は更新しない |
| `retry_pending_backfills:1006` | `record_round:1329` | 同じtargetの別kindを誤更新しない |
| `backfill_one:1333` | `main:1407` | stateの版に応じた更新キーを渡す |
| `main:1368` | `round_gate.py:1447` のスクリプト入口 | gateの引数とJSON契約をCLI通しで確認 |
| `read_state_file:427`（本体変更なし） | 計数/記録/受領の共通読取り | 汎用parserは残し、計数側のstrict validatorで破損・重複キー・欠落を拒否。受領処理へ不要な互換破壊を広げない |

これは設計上の影響確認で、各呼出し元の動作試験は未実行。実装時は同じ `git grep` を再実行して追加された呼出し元も確認する。直接呼出し試験は `tests/test_round_gate.py:52-55,124-148,167-269,279-325,878-1218,1339` と `tests/test_review_must_criteria.py:155`。CLI配線は `tests/test_codex_review_cli.py`、点検は `tests/test_preview_checks.py`。基点の旧仕様に依存する試験を削除だけで緑にせず、区分表の期待に置き換える。

基点での再利用探索: `git grep -n -E 'pre-release|active_projects|route\.mjs|dispatch_id|flock' -- lib bin tests docs README.md` は **0件**。この範囲にA/D接続・発注ID・ロックの該当記述は無い。#2006側の既存adapterと正本取得・state/本文記録・既存純粋判定を再利用し、新依存は追加しない。

## 6. 試験の入力区分表（実装時の計画）

出所略号: PJ = 第1章の公開前規則:3-8、通常 = review.md:5-8、分析 = REPORT:118-134、D契約 = routing/skill-src/routing.md。テスト名は候補であり今回は追加しない。数値・表現の同値クラスは代表を使い、必須欄は1項目ずつ欠けたケースを表形式にする。

| 入力 | 区分・境目 | 置く値 | 期待 | 期待の出所 | 大きさ | 候補試験名 |
|---|---|---|---|---|---|---|
| 発注一式 | 正常系の通し（最初） | 登録PJ・既定枝の決め・コード既発注2件・採用案/理由/時刻/4材料・総上限3 | 巡3をPJ裁定で許可、同じID/巡/版を保存。人間承認とは書かない | PJ:6、分析 | fake送信のCLI通し | `prerelease_round3_dispatch` |
| 通常承認 | 特例対象外の陽性対照 | 別PJ・巡3の既存人間承認と総上限 | 通常経路で通る | 通常:6 | 関数＋CLI | `human_path_unchanged` |
| 巡数 | 2/3、5/6 | 2、3、5、6、上限5 | 2通常、3/5は有効裁定内、6はPJ特例で不可 | PJ:6、通常:6 | 関数 | `round_boundaries` |
| 総上限 | 不足/ちょうど/超過/不正 | 巡3にcap2/3/6、非整数 | cap3だけ特例通過、cap6でハード上限を広げない | PJ:6 | 関数 | `cap_boundaries` |
| 一括材料 | 欠落と明示の無し | blockingなし、各必須欄欠落、理由空、時刻空 | 明示の無しは受理、欠落は停止 | PJ:6、分析 | 関数 | `missing_materials` |
| PJ実体 | 別PJ/偽装 | 同じ規則をコピー、originだけ変更、envだけ許可PJ | 特例停止 | PJ:3、今回依頼A | 関数＋CLI | `other_project_cannot_claim` |
| 公開状態 | 公開前/終了/不明 | 公開終了の追記が既定枝入り、古いorigin/main、API失敗 | 公開後/不明を特例で通さない | PJ:5、dev規則:7 | Git/API fixture＋CLI | `release_switch` |
| 規則の所在 | 作業枝だけ/読取不能 | 既定枝に無し、未追跡の同名文書、未知blob | 特例停止 | 今回依頼A、分析 | Git fixture | `policy_only_on_topic_branch` |
| 対象操作 | できない操作 | 共有物変更、不可逆、stg/prod書込み、本人の明示確認 | 特例停止、通常承認対象を示す | PJ:3-4,7 | 関数＋CLI | `scope_restrictions` |
| 文字と時刻 | 空白/引用/境目 | 全角空白、改行注入、コード引用だけの裁定、無効日、tzなし、未来時刻 | 偽の許可行を作らず停止。時刻同値は正規化 | PJ:6、分析 | 関数 | `record_shape_and_time` |
| 鮮度の合図 | 判定後に変化 | 送信前に既定枝が公開終了版へ進む/対象hash変更 | 再判定し未送信、sleepで代用しない | PJ:5、今回依頼A | CLI通し | `recheck_before_send` |
| 自己申告 | bypassとの混在 | envに許可true、偽JSON、NO_GATE付きPJ特例 | PJ裁定の根拠にならず、同時利用拒否 | 今回依頼A | CLI通し | `claims_not_authority` |
| 発注と版 | 同じHEADで2回 | 別run ID、同じtarget/kind | 巡1/2。続きを返す同じIDは増やさない | 今回依頼C、分析 | 集計＋CLI | `dispatch_not_head` |
| 種別 | 設計→コード | 設計2発注後のコード初回 | コード巡1、前置き/保存/上限が一致 | 通常:6、今回依頼C | CLI通し | `kind_counter_shared_result` |
| 前身 | 継承と重複 | 同種2+1、別種2+1、共有祖先、issue→PR | 同種3/別種1、祖先は一回、別名でリセット不可 | 通常:7 | 関数＋記録 | `predecessor_events` |
| 旧state | 欠落/破損/消失 | kindなし、HEADなし、読取不能、重複キー、空ディレクトリ | 不明は停止、0へ縮めない。照合済み補完のみ受理 | 通常:5,7、今回依頼C | 関数 | `legacy_is_not_zero` |
| 待ち/失敗 | 発注済みと拒否 | 生存report空、送信後timeout、起動前拒否、予約不明 | 前2つは計数、拒否は不計数、予約不明は停止 | 分析の発注定義、D契約 | CLI通し | `dispatch_lifecycle` |
| 同時実行 | 巡2の残枠 | 同種2プロセス、片方予約後クラッシュ | 同じ巡3を二重予約しない。不明予約を消さない | Cの計数不変条件（本書3.3） | 並行CLI | `reservation_race` |
| 行の更新 | 種別の入替え | 設計巡1とコード巡1、旧行複数候補 | 指定IDだけ更新、曖昧なら停止 | 通常:5、今回依頼C | 記録関数 | `backfill_identity` |
| D登録 | 空/一致/不一致 | active_projects空、hash一致、不一致、未commit表 | 接続前は旧経路、enabled後の不一致は停止。空のまま有効化不可 | D契約、activation-3points | 両口非送信 | `activation_registry` |
| Dイベント | Cとの継ぎ目 | D一イベントにC二発注、片方pending | C二巡を維持、未着を受領済みにしない | 本書4.1、通常:5 | 変換＋CLI | `routing_dispatch_mapping` |
| D検査 | 全体/部分/未対応 | 正規複合経路、単体vitestのみ、設定欠落 | 接続済み正規全体だけ受理、部分や未対応は停止 | D契約:関門B | 既存route試験＋通し | `canonical_test_expansion` |
| D締切/復旧 | 30秒前/境界/後 | 固定単調時計、29.999/30/30.001、空/不正JSON、例外 | 締切以上と異常は停止、逆差分後は両口で送信直前へ | adapterの全体30秒契約 | 両口非送信 | `deadline_and_rollback` |
| 必須ゲート | 非充足 | 別系統なし、未解決Must、受領hash不一致、変異未確認 | PJ裁定だけで実装/マージ/完成を許可しない | PJ:8、通常:5,8 | 既存試験＋通し | `mandatory_gates_survive` |

DB・画面の行は試さない（レビュー起動のローカル制御であり、DB接続や画面変更をしないため）。この表は実装前に後続担当へそのまま渡し、実装差分に応じて試験名と件数を確定する。

### 6.1 陰性試験と変異の候補

不正入力を正しく拒否する通常試験は緑にする。以下はその検査対象の実装を壊したとき、試験が赤になることを確認する計画である。

| 分類 | A | C | D |
|---|---|---|---|
| ①守る処理を消す | PJ実体照合を削除し別PJが通る | kindによる分離を削除 | 有効化済みPJの登録照合を削除 |
| ②語を残し意味を壊す | 公開終了判定を逆転し公開後が通る | 別runでも同じHEADなら同巡へ戻す | 登録空を全通過として扱う |
| ③入れ替える | 既定枝blobを作業枝blobへ差し替え、決めの無い既定枝でも通る | 設計/コードの更新先または前身をswap | canonical argvと申告argvをswap |
| ④検査を無効化 | policy validatorを常に許可し申告だけで通る | 読取り例外を空履歴へ変換 | adapter呼出し削除/終了0固定/JSON不正を成功扱い |
| 陽性対照 | 同じ瞬間の時刻をUTC表記へ変更 | 入力stateの列挙順だけ変更 | JSONの意味を変えずキー順変更 |

Aの「別PJ／公開後／決めのない既定枝／申告だけ」の4不正許可をそれぞれ赤にする。少なくとも①〜④各1件と陽性対照1件を実行し、対象となる各検査を守る変異を増やす。追加の異種回避は最低2件: (a) 正規PJへのsymlinkとorigin偽装を組み合わせる実行文脈の差、(b) 判定から送信までに本線/対象版が変わる鮮度の差。さらにCの予約後クラッシュ・別state-dir指定、Dの空登録への戻し・古い非送信コピーの誤使用を探索する。

実装/試験をcommitした状態を基点とし、作業場所内の隔離コピーで1変異ずつ適用する。各件に (a) 不変条件を壊す差分と変更前後hash、(b) 実際に読まれた分岐/値のtraceを別の証跡に残す。Python標準の行traceとシェル実行traceを再利用し、判定用の実行結果とtrace採取を混同しない。compileエラー・未着弾・試験0件を検出成功にしない。④は試験側のskip/常時緑化も試し、収集件数・期待した試験ID・非0のassertion失敗を照合する実行器が欠落を検出することを確認する。

実装時の試験はパッケージ全体 `python3 -m pytest -q -p no:cacheprovider --basetemp=<作業場所内の一時dir>`。先に必要なローカル実行器/スタブを確認し、実LLM・実gh書込み・AWSに到達させない。D部品は既存のroute/ledger/activation全試験を追加で回す。各ファイルと passed/failed/skipped/collected を記録する。依存が無ければinstallせず未実行とする。新しい緑を得た後、変異の緑残存が1件でもあれば未完了。原本のバイト一致、最後の `git diff` と `git status --porcelain` の空を確認する。「前からある赤」はorigin/main上の同じ試験で確認できた場合だけ用い、測れなければ「前からあるかは未確認」とする。

## 7. 各項目へ7段を当てた結果

段は ㋐必要性 → ㋑既存 → ㋒標準ライブラリ → ㋓プラットフォーム標準 → ㋔導入済み依存 → ㋕1行 → ㋖最小コード。止まった段以降は採用しない。新依存は全項目で不要。

| 項目 | 判定と止まる段 |
|---|---|
| Aの通常承認 | ㋐必要、㋑ `decide`/既存approval/capで足りる。通常経路を再実装しない |
| Aの規則取得 | ㋐今日2件の食い違いへの対応が必要、㋑既存Git/gh呼出しを再利用、㋒標準subprocess/hashlib/datetime、㋓既定枝と追跡blobで止まる。ルールエンジンは足さない |
| Aの裁定照合 | ㋐範囲の誤許可防止に必要、㋑既存decideへ接続、㋒データ/時刻処理は標準、㋓だけでは権限と対象を照合できず、㋔新依存不要、㋕1行では不成立、㋖小さい純粋validatorと読取りhelperだけ |
| Cの計数/移行 | ㋐既存の過小計数修正に必要、㋑既存state/前身/本文記録を使う、㋒集合と標準JSON、㋓発注IDは既存run ID、㋔不要、㋕1行では種別/欠落/継承を扱えず、㋖正規化と共通集計の最小変更 |
| Cの排他・予約 | ㋐同時発注で上限を破らないため必要、㋑今回探索0件、㋒標準fcntlとos.replaceで止まる。外部ロックサービス不要 |
| Cの行更新 | ㋐種別別の同じ巡番号で誤更新しないため必要、㋑既存render/backfillへIDを通して止まる。別台帳への全面置換はしない |
| Dの判定/全体締切 | ㋐配線の失敗を閉じるため必要、㋑#2006のroute/adapter/逆差分が既にあるため止まる。監督器を重ねない |
| Dの段階導入 | ㋐空登録で正常発注を止めないため必要、㋑既存の未接続状態/非送信検査/対応表を再利用、㋓追跡設定と配布commitの単位で止まる。申告によるバイパスは足さない |
| DのCLI呼出し | ㋐接続に必要、㋑既存patchを再生成、㋒/㋓/㋔追加不要、㋕送信直前の既存adapter呼出し1行で止まる。対象PJの選択と記録照合は上流の責務 |
| Dの複合検査展開 | ㋐コード発注を通すため必要、㋑既存record-run/turboの実体を後続で照合、㋒〜㋖の採否は実体の再取得後。未確認の展開器を本書で完成扱いにしない |
| 試験/変異 | ㋐削減不可、㋑既存pytest/fake送信/変異証跡手順を再利用、㋒標準traceで止まる。過去の緑を新仕様の検証に代用しない |

## 8. 環境差・今回の到達点

| 環境/対象 | 経路・設定の差 | 本設計の許可と今回の接続 |
|---|---|---|
| ローカルの登録PJ | 既定枝の公開前規則と裁定を読み、可逆な読み取りレビューのみ | 設計対象。今回の外部操作は指定GitHubの読み取りだけ |
| dev | PJ規則自体は可逆判断を含むが、devの常時承認/例外が別にある | devの読み取り・書込み・DB/AWS接続は今回一切しない。Aの発注許可で代替しない |
| stg | 書込みはPJ公開前特例の例外 | 未接続、書込み許可なし |
| prod | 同上。本人確認・本番の各関門が残る | 未接続、書込み許可なし |
| 共有物/別PJ | PJの公開前裁定の適用外。通常の人間承認経路 | ファイル読取りのみ。配布候補の一覧に留める |

今回の検証は参照資料・基点・呼出し元・差分の静的確認。試験追加0件、実装の動作試験/パッケージ全試験/変異は未実行（設計だけのため）。DB試験も未実行、接続なし。赤の有無や変異の生存件数を0件と報告しない。

次の候補は、依頼元による本設計の設計レビュー1巡と受領確認、その後Aの実装。Dは#2006再取得・複合全体検査展開・記録契約整合が残る。別系統レビュー未充足を維持し、今回の設計commitを仕組み全体の完成・導入・効果の証明にしない。

指定の結果/次回依頼2ファイルの置き場 `共有/codex-queue/` はこの実行環境の書込み許可外で、今回個別依頼もupdater-indexを読むだけとしている。別の場所へ同名ファイルを増やさず、本書と最終報告で未作成を明記する。依頼元が書込み可能な窓で記録する際の次回run名候補は `review-complete-design-review`、対象作業場所は本書冒頭と同じ絶対パス、作業は本書だけの設計レビュー、終了条件は指摘と受領材料の記録（製品コード変更なし・他LLM呼出しなし）。

## 付録: 既存試験の直接呼出し全箇所

基点で上記探索式に `retry_pending_backfills\(|backfill_one\(` を加え、`-- tests` を指定した `git grep -n -E` の結果からコメントを除いたもの。間接的にCLIを実行する試験は第5章のファイル単位で別途確認する。各期待の更新方針は第6章。

```text
tests/test_review_must_criteria.py:155:    assert ledger_own_round(state, target, head, kind_label='コード') == (2 if scenario == 'duplicate-head' else 1)
tests/test_round_gate.py:52:    assert rg.parse_approval_rounds(BODY_563) == [3]
tests/test_round_gate.py:53:    assert rg.parse_approval_rounds(BODY_559) == []
tests/test_round_gate.py:54:    assert rg.parse_approval_rounds(BODY_560) == []
tests/test_round_gate.py:55:    assert rg.parse_approval_rounds(BODY_537) == []
tests/test_round_gate.py:124:    assert rg.decide(1, "").status == "pass"
tests/test_round_gate.py:125:    assert rg.decide(2, "").status == "pass"
tests/test_round_gate.py:130:    assert rg.decide(3, "本文になにもなし").status == "blocked"
tests/test_round_gate.py:132:    assert rg.decide(3, "巡3の人間承認をする").status == "blocked"
tests/test_round_gate.py:134:    assert rg.decide(3, "巡3の人間承認\n総上限: 5巡").status == "pass"
tests/test_round_gate.py:136:    assert rg.decide(6, "巡3の人間承認\n総上限: 5巡").status == "blocked"
tests/test_round_gate.py:141:    assert rg.decide(6, body_with_approval_only).status == "blocked"
tests/test_round_gate.py:143:    assert rg.decide(6, body_with_verdict).status == "pass"
tests/test_round_gate.py:148:    d = rg.decide(3, BODY_563)
tests/test_round_gate.py:167:    assert rg.ledger_own_round(tmp_path, "pr:o/r#1", "aaa111") == 1
tests/test_round_gate.py:173:    assert rg.ledger_own_round(tmp_path, "pr:o/r#1", "bbb222") == 2
tests/test_round_gate.py:178:    assert rg.ledger_own_round(tmp_path, "pr:o/r#1", "aaa111") == 1
tests/test_round_gate.py:205:    total = rg.target_total_rounds(t, tmp_path, fetch, [], pending_new_head="sha1")
tests/test_round_gate.py:213:    total = rg.target_total_rounds(t, tmp_path, fetch, [], pending_new_head="sha1")
tests/test_round_gate.py:223:    total = rg.target_total_rounds(t563, tmp_path, fetch, [], pending_new_head=None)
tests/test_round_gate.py:235:    total = rg.target_total_rounds(b, tmp_path, fetch, [a], pending_new_head="shaB1")
tests/test_round_gate.py:243:    total = rg.target_total_rounds(t, tmp_path, fetch, [], pending_new_head="shaX")
tests/test_round_gate.py:257:        rg.target_total_rounds(a, tmp_path, fetch, [], pending_new_head="shaA")
tests/test_round_gate.py:269:        rg.target_total_rounds(targets[0], tmp_path, fetch, [], pending_new_head="sha0")
tests/test_round_gate.py:279:    row = rg.render_round_row(1, "コード", "2026-08-25 10:00", "abc1234", "codex")
tests/test_round_gate.py:296:    row = rg.render_round_row(2, "コード", "2026-08-25", "def5678", "codex")
tests/test_round_gate.py:306:    row = rg.render_round_row(4, "コード", "2026-08-25 18:00", "abcdef1", "codex")
tests/test_round_gate.py:315:    row = rg.render_round_row(1, "コード", "2026-08-25", "abc1234", "codex")
tests/test_round_gate.py:317:    new_body, found = rg.backfill_measuring_row(body, 1, "65880")
tests/test_round_gate.py:325:    new_body, found = rg.backfill_measuring_row(body, 99, "123")
tests/test_round_gate.py:878:    result = rg.run_gate("", "/tmp", tmp_path, "", "")
tests/test_round_gate.py:883:    result = rg.run_gate("pr:o/r#1", "/tmp", tmp_path, "", "手動確認済み")
tests/test_round_gate.py:890:    result = rg.run_gate("not-a-valid-target", "/tmp", tmp_path, "", "probe")
tests/test_round_gate.py:897:    result = rg.run_gate("", "/tmp", tmp_path, "", "   ")
tests/test_round_gate.py:913:        r = rg.run_gate(f"none:probe{i}", wd, tmp_path, "", "")
tests/test_round_gate.py:916:    blocked = rg.run_gate("none:one-more", variants[-1], tmp_path, "", "")
tests/test_round_gate.py:947:        r = rg.run_gate(f"none:probe{i}", wd, state_dir, "", "")
tests/test_round_gate.py:951:    blocked_via_link = rg.run_gate("none:one-more", str(link_dir), state_dir, "", "")
tests/test_round_gate.py:976:        result = rg.run_gate("pr:o/r#1", "/tmp", tmp_path, "", "", fetch_body=fetch, goal_cut=VALID_GOAL_CUT)
tests/test_round_gate.py:982:    blocked = rg.run_gate("pr:o/r#1", "/tmp", tmp_path, "", "", fetch_body=fetch, goal_cut=VALID_GOAL_CUT)
tests/test_round_gate.py:994:    blocked = rg.run_gate("pr:o/r#1", "/tmp", tmp_path, "", "", fetch_body=fetch, goal_cut=VALID_GOAL_CUT)
tests/test_round_gate.py:999:    passed = rg.run_gate("pr:o/r#1", "/tmp", tmp_path, "", "", fetch_body=fetch, goal_cut=VALID_GOAL_CUT)
tests/test_round_gate.py:1008:    result = rg.run_gate("pr:Todoroki-Godai/Evolve-Anything#1", "/tmp", tmp_path, "", "")
tests/test_round_gate.py:1014:        r = rg.run_gate(f"none:probe{i}", "/w", tmp_path, "", "")
tests/test_round_gate.py:1017:    blocked = rg.run_gate("none:one-too-many", "/w", tmp_path, "", "")
tests/test_round_gate.py:1030:    result = rg.run_gate("pr:o/r#1", "/tmp", tmp_path, "", "", fetch_body=fetch)  # goal_cut 省略＝空
tests/test_round_gate.py:1039:    result = rg.run_gate(
tests/test_round_gate.py:1050:    result = rg.run_gate(
tests/test_round_gate.py:1060:    result = rg.run_gate("none:probe", "/w", tmp_path, "", "")
tests/test_round_gate.py:1067:    result = rg.run_gate("pr:o/r#1", "/tmp", tmp_path, "", "手動確認済み", goal_cut="raw-value-kept")
tests/test_round_gate.py:1078:    result = rg.run_gate("pr:o/r#1", "/tmp", tmp_path, "", "手動確認済み", goal_cut=malicious)
tests/test_round_gate.py:1087:    result = rg.run_gate("none:probe", "/w", tmp_path, "", "", goal_cut=malicious)
tests/test_round_gate.py:1094:    result = rg.run_gate("pr:todoroki-godai/evolve-anything#563", "/tmp", tmp_path, "", "")
tests/test_round_gate.py:1107:        rg.run_gate("pr:todoroki-godai/evolve-anything#563", "/tmp", tmp_path, "", "")
tests/test_round_gate.py:1119:    result = rg.run_gate(
tests/test_round_gate.py:1139:    result = rg.run_gate("pr:o/r#9", "/tmp", tmp_path, "", "", fetch_body=fetch, goal_cut=VALID_GOAL_CUT)
tests/test_round_gate.py:1154:        result = rg.record_round(sf, tmp_path)
tests/test_round_gate.py:1174:    result = rg.record_round(sf, tmp_path, fetch_body=fetch, patch_body=patch)
tests/test_round_gate.py:1191:    result = rg.record_round(sf, tmp_path, fetch_body=fetch, patch_body=patch)
tests/test_round_gate.py:1199:    result = rg.backfill_one(sf, tmp_path)
tests/test_round_gate.py:1218:        + rg.render_round_row(1, "コード", "2026-08-25", "abc1234", "codex")
tests/test_round_gate.py:1228:    result = rg.backfill_one(sf, tmp_path, fetch_body=fetch, patch_body=patch)
tests/test_round_gate.py:1339:        res = rg.run_gate(
```
