# codex-watch

`codex exec` を「投げっぱなしにしない」ための小さなラッパー群。

`codex exec` を直接起動すると、呼び出し元の都合でプロセスが刈られて判定行が出ないまま無言で死んだり、
進行中なのか固まっているのか区別できなかったりする。ここにあるのはそれを観測可能にするための最小限の道具。

## コマンド

| コマンド | 用途 |
|---|---|
| `codex-review <対象dir> <promptfile> [ラベル]` | レビュー発注（`-s read-only`）。detach して run id を返す |
| `codex-impl <worktree> <promptfile> [ラベル]` | 実装発注（専用権限プロファイル）。linked worktree でなければ拒否 |
| `codex-watch <run id>` | STALL / VERDICT / EXIT / TIMEOUT の4事象を報告する見張り |
| `codex-status <run id>` | 生存・経過・無音時間・判定行・ログ末尾を1画面で表示 |

状態は `~/.codex-watch/<run id>.{log,report,state}` に残る。

## 設計の要点

- **完了判定はプロセス終了で行う。**ログの中身で判定しない — `tokens used` は回答本文より先に出るため、
  grep が当たった時点では回答が書き終わっていないことがある。
- **無音時間を測る。**プロセスが生きていることは、進んでいることを意味しない。
  既定の無音閾値は 180 秒（`CODEX_WATCH_STALL_SEC`）。
- **沈黙を成功と読み違えない。**見張りは失敗側の事象も必ず出す。
- **スキル定義の読み込みを抑止する。**`codex-review` は発注プロンプトの先頭に、
  グローバルなスキル定義を読まないよう指示する前置きを自動で足す（対象リポジトリ内のファイルは読んでよい）。
  外すときは `CODEX_REVIEW_ALLOW_SKILLS=1`。
- **Codex にブラウザを使わせるときは `templates/browser-cdp.md` の定型を使う**（囲いを外さない。頭が先に Chromium を起こし、Codex は localhost の CDP に繋ぐだけ。2026-10-27 実測）。囲いを外す起動口は作らない。
- **`codex-review` に画像を渡すには `CODEX_REVIEW_IMAGES` に画像の絶対パスを1行1件で書く**（絶対パスで渡す。相対パスは拒否される）（見本と実画面の見比べ用）。1件ずつ `codex exec -i <パス>` になり、与えた順に付く。
  未設定・空なら起動の行は従来と同一。受理は実在する普通のファイルで拡張子が png/jpg/jpeg/webp のものだけ。
  外れが1件でもあれば、巡数ゲートの記録・状態ファイルより前に理由を出して exit 2 で止める（先頭が `-` のパスと `,` を含むパスも拒否。空白を含むパスは可）。
  モデルは既存の `CODEX_REVIEW_MODEL`（例: `gpt-6.1-terra`）で指定する。新しい口は無い。
- **`codex-impl` は共有 checkout への書き込みを拒否する**（未レビューのコードがそのまま動く状態を作らないため）。
  例外口は `CODEX_IMPL_ALLOW_MAIN=1`。
- AWS は stg プロファイルで口座 `669126230735` を照合した場合だけ一時鍵を環境へ渡し、失敗時は `aws=none`。
  `~/.aws` を拒否し、秘密なしの `codex-dev` 設定と空の credentials を指定するため、共有設定の prod プロファイルへ届かない。
  鍵は更新せず、`aws_expiration` の期限で長い作業は途中から AWS を使えなくなる。
- `codex-impl` は起動前に Python 3.11 以上の `tomllib` で `~/.codex/config.toml`、設定時の `$CODEX_HOME/config.toml`、作業場所と祖先の `.codex/config.toml` を検査する。
  トップレベルと全 profiles の `shell_environment_policy.set` に `AWS_PROFILE` 以外の `AWS_` キーがあれば拒否する。読取・解析不能も拒否し、値は表示しない。存在しない任意設定は許容する。
  `AWS_PROFILE` は CLI で `codex-dev` に上書きする。継承の絞り込み（Should）は既存の環境継承契約への影響があるため今回は範囲外。
- **`codex-impl` の既定モデルは `gpt-6.1-sol`。** `CODEX_IMPL_MODEL` で上書きできる。
  `CODEX_IMPL_MODEL=` と空文字を明示すると `-m` を付けず、config.toml の既定に従う。
- `gpt-6.1-sol` は codex-cli 0.159.1 の `codex debug models` に掲載（visibility=list）を確認済み（2026-09-30）。前任の `gpt-6-sol` は 0.156.1 で受理・0.154.0 では 400 で即終了した。古い CLI では codex-watch が「報告ファイルが空」と表示する。対処は CLI の更新か `CODEX_IMPL_MODEL=`。
- `codex-impl` の effort 既定は `medium`。`CODEX_IMPL_EFFORT=` と空文字を明示すると `-c model_reasoning_effort` を付けず config.toml の既定に従う。レビューの既定は変更しない。
- **`codex-review` は発注前に `REVIEW_GOAL_CUT` を必須で検査する**（`pr:`/`issue:` の実発注のみ。
  `none:` 発注と `CODEX_REVIEW_NO_GATE` bypass は対象外）。なぜ要るか — 「目的への寄与がゼロの
  成果物がレビュー巡を費やして最後に撤去される」事故（2026-09-03。denylist 型 lint に
  5巡＋実装6回を費やして撤去した）が、文章のルールだけでは読み飛ばされて発火しなかったため、
  発注口1つで機械的に fail-closed にした。受理形式（厳密一致）:
  ```
  <数値><単位> | 根拠: <再現手段または出所> | 取得日: YYYY-MM-DD
  ```
  例: `REVIEW_GOAL_CUT="30.04分/周 | 根拠: pitfall #588 の実測（2026-08-26 cider-power-lp） | 取得日: 2026-08-26"`
  未記入・形式不一致・数値部が 0・取得日が不正な日付は、いずれも発注をブロックする。

## PJ ごとの GitHub 名義

対象作業場所の git 最上位に `.claude/codex-github-account` を置き、
`matsukaze-minden` などの login を1行で宣言する（資格情報は書かない）。
前後の空白は無視する。宣言がない場合は既存の起動経路を使う。

宣言がある場合、状態ディレクトリ内の常設 `gh-account/<login>/` を使い、
保管庫から得た `gh api user` の login が一致するまで起動しない。
中身は宣言名義だけの hosts.yml（トークンなし）と固定値 `version: "1"\n` の config.yml。
起動ごとに一時ファイルへ書き、rename で置き換える。終了後も残し、review の巡の記録に使う。
`codex-review` の巡の記録（PR・課題の本文の GET・PATCH）も宣言した名義で行う。
共有 `hosts.yml` は変更しない。環境の認証上書きも除去し、Codex の子シェルには
`-c shell_environment_policy.set.GH_CONFIG_DIR=...` で同じ設定を渡す。
状態ファイルに `github_account=` の行が無ければ宣言なし、値があれば宣言・検証済み。
状態の PID は Codex プロセスを指す。

宣言した名義が保管庫に無く、しかも現在の共有名義と同じ場合は、事前の照合では見分けられない（前回確認時の該当は0件）。
宣言ファイルは git に commit しないと worktree に届かず、宣言なしに戻る。

検証手順と実測は [tests/github-account-verification.md](tests/github-account-verification.md)。

## 必要なもの

- `codex` CLI
- bash 3.2 以上（macOS 既定で動く）
- python3（レビュー巡数ゲートを使う場合）

## レビュー受付の条件

`codex-review` は毎回、[依頼文のひな形](templates/review-request.md)の5つの完成条件と
「追加変更」「修正した族」を検査する。見出しは `##` と正確な名称を使い、各欄は非空にする。
コードブロック内の見出し・重複欄は受け付けない。既存の巡数ゲートの例外でもこの受付は省略しない。

族は A（根拠・状態・保護）、B（入力・境界・接続）、C（検出力・検査データ）、
D（範囲・決定・巡管理）の4つから選び、小分類は作らない。複数なら `A,B`、初回など修正なしは `なし`。
前巡の指摘族は全て記載する。設計からコードへ移っても族を引き継ぐ。
直近2回の発注の修正族に共通の族があれば、それ以上の発注を止める。

返答には次の機械可読行を1つ含める（発注時にも自動指示する）。指摘数は配列の長さで数える。

```text
review_findings=[{"severity":"Must","family":"A"},{"severity":"Should","family":"C"}]
```

0件は `review_findings=[]`。前巡0件の後は「追加変更」に `あり: 内容と理由` が必要。
既存の `.state` と `.report` を再利用し、前巡は対象・前身・同一作業ディレクトリで特定する。
前巡が実行中、旧形式、未受領、読み取り不能なら理由を1行出して非0で止める。
逐次出力で `.report` が部分的なら、既存の `codex-status` による本文再構築と受領確認を先に行う。
同じ作業先の無関係な系列・同秒の発注・PID再利用を誤って止める場合がある。
none:/bypassやGit管理外で既存のSHA/ハッシュが空なら、初回の後は受領情報不足で止まる。
意味による族の付け替え、
台帳削除、別作業先への未申告の系列移動、同時受付の競合に対する保証はない。
