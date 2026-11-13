codex-watch#38 A 実装: 試験0件成功（未実行）／陰性試験0件（未実行）／陽性対照0件緑（未実行）— 入力不足で実装前停止・未完了

## 判断

今回の依頼の「参照物が無い・指示が足りないときは、選択肢と既定案を結果に書いて止まる」と「取得口の範囲が決められない部分は止まる側に倒し、報告に書く」を適用した。A の実装・README の使い方の追加は行っていない。公開前特例が利用可能になったとは報告しない。

開始版は `b2c6e479d40c3bc13a1b141e99b79dead2b244cb`、ローカル `origin/main` は `bdb4d62f80e32eae37be8fcf8d3d11e11e339bae`。開始時の status は空。fetch はしていない。

## 停止理由と再開に必要な材料

1. **履歴の取得範囲が未確定。** 設計3.2は state 外の Agent/Task 発注も正本から照合することを要求する。一方、現行 `ledger_head_shas_for_target()` は指定 state-dir の `*.state` を読むだけで、`find_rollout_jsonl()` は既知 session ID に対応するトークン計測資料の探索である。これを全発注履歴の取得に代用できない。設計レビュー [Should] 2 も「対象セッションの範囲・補完レコードの照合方法が未確定」と指摘している。対象系列の全セッションを列挙する保存先、欠けの検出方法、正本取得担当、補完の出所を固定する契約が必要。`complete=true` と自己申告した JSON や試験スタブだけで完全性を作らない。
2. **レビュー済み固定登録の実物が未提示。** 設計2.1は repo slug・Git common directory・規則パス・既知blob hash をレビュー済みの固定登録へ結ぶ。製品コードにはその入口がなく、設計に値一式はない。規則のローカル実物を読めることと、その版・登録を裁定の正本として採用済みであることは区別する。登録を誰がどの追跡ファイルへ固定するかと、照合対象版を再開材料にする。

選択肢は、(a) 取得担当が履歴の正本・列挙範囲・照合契約と固定登録を提示してから A を再開する、(b) まずそれらを確定する設計補足を同じ作業場所で作る。**既定案は (b)**。追加の人間承認そのものを必須にする提案ではなく、実装入力を具体化する作業である。今回これを勝手に確定して実装済みと扱わない。履歴が不明なとき自動特例を通さないこと、通常承認のレビューは公開状態APIの失敗だけで止めないことを再開条件に残す。

「補完後の巡3判定→前置き→予約→保存」は現行の `bin/codex-review:116` の前置き用再集計と `:254` の送信後の state 保存にも関わる。予約は設計3.3（C）の事項であり、Aで必要な最小範囲を補足時に明示する。C全体の計数変更とDの接続は今回へ広げない。

## 読んだもの

| 必須参照 | 確認したもの |
|---|---|
| 段取り表 | 独立したT番号の行は無し（指定なし）。担当の出所として updater-index `_work/notes/rev9-review-history.md:275` を確認 |
| 本人の決定 | 今回の依頼の中継原文 A・C・D、受領時刻 2026-11-13 16:22:03 JST。新しい承認を推定しない |
| 見本HTML | 無し（発注の関門で画面変更なし） |
| 前身と巡 | `docs/design/review-complete.md`、`~/.codex-watch/review-complete-d1-20261113-163337-8555.report`（実装着手可、Must 0 / Should 2） |
| 現行コード・説明 | `lib/round_gate.py`、`bin/codex-review`、`README.md`。`tests/test_round_gate.py`・`tests/test_codex_review_cli.py` の関連箇所、`tests/conftest.py` |
| PJ規則 | rev9-audit の `.claude/rules/pre-release-proceed-with-recommendation.md` と `dev-standing-approval.md`（ローカル資料。GitHub最新公開状態は未確認） |
| 試験手順 | rev9-audit の `.claude/skills/test-design/SKILL.md`（設計に指定された所在。`~/.claude/skills/test-design` は存在しない）、`~/.claude/rules/verify-checks-by-breaking.md`、`~/.claude/refs/verify-checks-by-breaking.md` |

## 再利用の探索と7段

実行した探索は次のとおり。第1式の出力は0件（終了1）。これだけで類似処理の不存在全般を主張せず、関数本体も確認した。第2式は7件。

```sh
git grep -n -E 'project_prerelease|policy_blob|common_dir|history_complete|REVIEW_GATE_RECORD' -- lib bin tests README.md
git grep -n -E 'def (target_total_rounds|ledger_head_shas_for_target|find_rollout_jsonl)|def run_gate|PROMPT_ROUND=|nohup codex' -- lib/round_gate.py bin/codex-review
```

| 項目 | 7段の結果 |
|---|---|
| 通常承認 | ㋐必要、㋑既存 `decide()` と承認・上限解析を再利用できる。変更なし |
| 規則・裁定の照合 | ㋐必要、㋑既存Git/ghを利用する設計あり。固定登録の入力確定前で停止。追加コード・依存なし |
| 履歴完全性 | ㋐必要、㋑台帳とトークン取得処理はあるが全履歴の保証にはならない。取得範囲の確定前で停止。㋒以降の手段選定で出所不足を代替しない |
| 報告 | ㋐明示依頼、㋑指定のMarkdown報告へ記録。新しい仕組みなし |

製品の関数・値の変更は0件なので、変更した関数の呼出し元の検証は該当なし。

## 入力の区分表（再開時用・試験未作成）

期待の出所は設計2.1〜2.3・6章と今回の [Should] 2件。取得口が定まってから、正常通しを先に書く。

| 入力 | 区分・境目／置く値 | 期待 | 大きさ／予定試験 |
|---|---|---|---|
| 発注一式 | 正常通し、正本で補完したAgent発注2件・公開前・総上限3 | 今回は巡3、前置き・予約・保存が一致 | fake送信CLI通し／prerelease_round3_dispatch（取得口未確定） |
| 通常承認 | 履歴完全・巡3・人間承認・総上限3、公開状態APIだけ失敗 | 通常経路を許可 | CLI通し／human_path_unchanged |
| 権限と対象 | 別PJ・公開後・既定枝に決めなし・申告だけ | 自動特例は不成立 | 関数＋CLI／設計6章の①〜④ |
| 数字 | 巡2/3/5/6、総上限2/3/5/6、bool・文字列 | 通常経路と特例上限を区別、整数3〜5のみ | 関数／境界 |
| 時刻 | timezoneなし・未来・同一瞬間のUTC表記 | 前2つ拒否、UTCは同じ裁定 | 関数／時刻と陽性対照 |
| 文字・欠け | 必須欄ごとの欠落、空白のみ、欠落と空集合 | 不足は不成立、明示の空集合は仕様に従う | 関数／欠落 |
| 合図と継ぎ目 | 取得成功でもセッション欠落、送信前に版変更 | 完全性を推定せず停止、再確認 | 取得口＋CLI／取得契約確定後 |

変異①〜④・異種回避2件・陽性対照はすべて未実行。追加した検査は0件。実装がないため変異対象のcommitもない。緑残存0件や変異の成功を主張しない。再現コマンド・trace・変異logは未作成。

## 試験と環境差

パッケージ全体試験は未実行（実装前の入力不足で停止、文書のみ）。passed/failed/skipped/collected はいずれも未計測。「前からある赤」は未確認。AWS・DB・LLM接続なし、DB試験は未実行。READMEへ未実装の使い方は追加していない。

| 環境 | 経路・設定・データの差／今回 |
|---|---|
| ローカル | Gitと指定資料の読み取り、今回の報告文書だけ作成 |
| dev | PJ常時承認は別規則。今回は接続・読み書きなし |
| stg | 操作別の関門。今回は接続・読み書きなし |
| prod | 専用窓の関門。今回は接続・読み書きなし |

## 引渡し

指定の updater-index `codex-queue` への2ファイルは未作成。その領域は今回の依頼で読み取り専用、実行環境も書き込み許可外。作業場所の `docs/design/refactor-result-review-complete-implA.md`（10行以内）と `refactor-next-review-complete-implA.md` に引渡し用の内容を保存する。指定先への転記は書き込み可能な依頼元が行う。自動承認レビューの拒否による停止ではない。

commit を含むコマンドは PreToolUse フックが実行前に拒否した。理由は `owner='todoroki-godai'` が期待する gh 名義と、write時点の `matsukaze-minden` の不一致。今回禁止された `gh auth switch` やフックの迂回は行わない。今回のcommit SHAは無し。文書3ファイルは未追跡のまま引き渡す。`git diff` が空でも未追跡文書があるため clean と報告しない。
