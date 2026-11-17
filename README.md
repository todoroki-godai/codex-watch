# codex-watch

`codex exec` を「投げっぱなしにしない」ための小さなラッパー群。

`codex exec` を直接起動すると、呼び出し元の都合でプロセスが刈られて判定行が出ないまま無言で死んだり、
進行中なのか固まっているのか区別できなかったりする。ここにあるのはそれを観測可能にするための最小限の道具。

## コマンド

| コマンド | 用途 |
|---|---|
| `codex-review <対象dir> <promptfile> [ラベル]` | レビュー発注（`-s read-only`）。detach して run id を返す |
| `codex-impl <worktree> <promptfile> [ラベル]` | 実装発注（専用権限プロファイル）。linked worktree でなければ拒否 |
| `codex-watch <run id>` | STALL / VERDICT / FILTERED / EXIT / OVERDUE / TIMEOUTを報告する見張り |
| `codex-status <run id>` | 生存・経過・無音時間・判定行・ログ末尾を1画面で表示 |

状態は `~/.codex-watch/<run id>.{log,report,state}` に残る。

`CODEX_SUMMARY` の先頭60字以内に課題番号 `#N` を入れる（番号の無い仕事は `#0`）。無ければ起動しない。

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

`codex-impl` の依頼文には行頭（字下げなし・半角コロン）で出所を1行書きます。
レビューの直しなら、依頼前に `~/.claude/rules/review-receipt.md` の3手順を済ませ、次の4行をそれぞれ空でない値つきで書いてください（重複は拒否、違反は exit 2）。
```text
直しの出所: レビュー巡1（出所・対象版）
受領①累計: 起点abc123から1 commit・2ファイル・+10/-2、未追跡0件
受領②件数: M1=対象10件中2件（YYYY-MM-DD取得）
受領③7段: M1は㋑、既存の起動口を再利用
```
出所の値は `なし` か `レビュー` で始めてください。それ以外は exit 2。レビュー由来でなければ `直しの出所: なし（新規実装）` の1行で足ります。
既知の書き方だけを見る自己申告の検査です。書き忘れを捕まえますが、内容の真偽は確認できず迂回できます。
「なし」で始まる出所行より後ろの本文全体に `巡[0-9]|指摘を反映` があれば exit 2。出所を「レビュー…」に直し、受領の3行を書いてください。語で見ているだけ・言い換えは通る。`[Must]` は検査語に含めません（[計測](evidence/measurement.md)）。
語で止めるたび、止めた時点の依頼文を `~/.codex-watch/receipt-gate-stops/<時刻>-<依頼文のsha256先頭12桁>.md` に1ファイル保存します（元の改行を含むバイト列そのまま・権限0600・既存ファイルは上書きしない）。
`~/.codex-watch/receipt-gate-stops.log` の1行JSONには `time`（時刻）、`prompt`（元の絶対パス）、`match`（最初に当たった語）、`snapshot`（写しの絶対パス）、`sha256`（依頼文のSHA256全64桁）を記録します。元の依頼文を直して再起動しても、停止時の写しは残ります。
写しの保存・停止ログの記録に失敗した場合、および検査の異常（想定外の例外・python3 が無い）は起動しない側に倒れます。止めた起動は状態ファイルを作りません。

依頼文には完了の基準と見込みを次の2欄で書いてください。
```text
## 終わりの条件
実装と全試験の確認が済んだら報告して終える。
## 見込み: 45分
```
行頭の `## 見込み: N分` または `見込み: N分` の最初の欄を優先し、なければ本文で最初の `見込み: N分` を state の `estimate_min` に記録します。全角コロン・`約N分`・太字・末尾の句点も読めます。
`CODEX_IMPL_ESTIMATE_MIN` が定義されていれば（空でも）そちらが優先です。未指定・整数以外は空で記録し、警告1行で起動を続けます。
正の見込みの2倍を**超えて**プロセスが生存していれば、`codex-watch` は `OVERDUE` を1行出し exit 0 します。run 開始からの経過で判定し、自動では run を止めません。
OVERDUE を出すと見張りは終わります。その run の終了報告を受けるには、頭が同じ run id で見張りを張り直してください。頭は git log・status と出力を読んで継続を判断します。通知後は `<run>.overdue` が残るため、張り直した見張りは同じ run の OVERDUE を繰り返しません。
見込みなしの古い state は従来どおりです。`codex-status` は経過行に見込みを併記します。

### 測り直しの実行契約

- 起点: 2026-11-09 の導入commitの本線入り時刻。この作業場所でのcommit時刻ではなく、頭が本線入り時にその時刻を記録します。
- 分母: 起点以降の `mode=workspace-write` の状態ファイル数＋起点以降の停止ログの行数。止めた起動には状態ファイルがないため足します。同じ依頼文の再起動も別の1回です。
- 判定時点: 分母が30回に届いた時点、または2026-11-30の早い方。
- 実行者・判定者: 頭。止められた窓でその場の判定はせず、後で写しを読み、誤停止かを1件ずつ判定します。停止件数と誤停止件数を別に数えます。
- 結果の記録先: todoroki-godai/codex-watch#25（起点 2026-11-09 15:47:00 JST・判定の一覧もこの課題に残す）。
- 判定基準: 誤停止件数÷分母が5%を超えたら語の検査を外します（分母30なら2件以上）。
- 期限を過ぎても30回に届かなければ、その時点の件数で判定を出し、続けるか外すかをユーザーに諮ります。

### 戻し方

READMEの後続追記も先に戻すため、機能commit3個だけを戻す旧手順は使いません。
本修正の最終commitをHEADとした場合、次の並びを使い捨ての複製で `git revert --no-commit` し、衝突なし・起点 `efe4aad` の `bin/codex-impl` とREADMEへのバイト一致を確認しました。

```sh
git revert --no-commit $(git rev-list --first-parent efe4aad..HEAD)
```

新しい順に、本修正の文書commit → 写し保存commit → `3730450` → `43c4781` → `109cdfa` → `38a389a` → `0382463` → `99b2a7e` → `610a5c1` → `c3539e3` を戻します。
受領検査に関する試験・計測資料の追加と既存試験の調整も戻ります。後続commitがある場合は、範囲の `HEAD` を本修正の最終commitに置き換えます。
本線入り後に手で書いた導入時刻・課題番号などは、残れば手で消します。保存済みの写し・停止ログはGit管理外なので、この操作では消えません。

検証用の複製は `.tmp` 配下へ `git archive HEAD | tar -x -C <複製先>` で展開し、そこで `git init`・commitして作ります。履歴の参照は複製の `.git/objects/info/alternates` から元のobject directoryへ向けます（元のindex・枝は変更しません）。revertを試すのはその複製の中だけです。

- **`codex-impl` は共有 checkout への書き込みを拒否する**（未レビューのコードがそのまま動く状態を作らないため）。
  例外口は `CODEX_IMPL_ALLOW_MAIN=1`。
- AWS は PJ の git 最上位にある `.claude/codex-aws-account`（1行 `docs-ro`）で切り替える。宣言の不正値・読取不能は起動を拒否する。
  宣言なしの PJ は従来どおり dev（`669126230735`）の照合済み一時鍵だけを渡す。
  宣言した PJ は `codex-readonly` を assume し、口座 `670352692792` とロール ARN を照合した docs-platform の読み取り専用鍵1組だけを標準 `AWS_*` へ渡す。dev 鍵は取得しない。
  `AWS_PROFILE=…` と `--profile …` のどちらも `codex-dev`・`codex-docs-ro`・`aws-updater-bc-dev` は docs 鍵へ向き、`aws-updater-index-stg` は失敗する。
  照合失敗は `aws=none` で起動し、dev にフォールバックしない。期限は `aws_expiration`。鍵の更新は行わない。
  `~/.aws` は拒否し、専用設定と空の credentials を指定する。親環境の `AWS_*` と `CODEX_AWS_DOCS_*` は除去する。
  トップレベルと全 profiles の `shell_environment_policy.set` に `AWS_PROFILE` 以外の `AWS_` キーまたは `CODEX_AWS_DOCS_` キーがあれば拒否する。読取・解析不能も拒否し、値は表示しない。存在しない任意設定は許容する。
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

### レビュー報告の1行目

受領時（`round_gate.py receipt`・`codex-status` の受領表示・巡の履歴の受領集計）に、
1行目が `実装着手可` / `設計修正要` / `判定保留: <理由>` のどれかであることを検査します。
空行・別の言葉・装飾・理由のない保留は受領不可とし、形式を直して出し直すよう表示します。
保留の理由は同じ行に必要です。理由の内容や本文との意味の一致は判定しません。
新しい1行目検査の例外は通過させます。既存のSHA・内容ハッシュ照合は従来どおりです。
再構築・表示では過去の `マージ可` 等も引き続き読めますが、新たな受領判定では拒否します。
検証結果は [検証記録](docs/2026-11-17-verdict-line-validation.md) を参照してください。

### 内容ハッシュ手順の変更前に発注した run

旧手順の空入力ハッシュを記録した state は計算失敗と区別できないため受領不可とし、再発注します。旧手順の差分ありの値も、新手順で計算した申告値とは不一致となり受領不可です。state には手順の版がないため旧値を一般に識別できず、旧手順のまま申告した場合は一致してしまう可能性があります。手順変更前の run は再発注してください。既存 state は変更しません。

## 公開前の巡3〜5（A）

巡数は同じ対象・同じ種別（設計／コード）の distinct HEAD と同種の前身の合計です。判定・前置き・stateは同じ値を使います。
種別なしの `巡Nの人間承認` と総上限は両種別へ適用しますが、Nを両方の消化数にはしません。保存済みround=Nの種別が一意で、同種の保存済み実績がN以上であることを確認します。
未発注のN（3〜5）は、保存済みround=Nの候補がなく、今回種別の保存済み実績（同種の前身を含む）N−1と新規HEADの1巡が揃えば今回種別へ帰属します。それ以外の帰属不能・不足は従来の混算に戻します。承認なしの3巡目以上・総上限超過は通しません。
通常承認を先に判定するため、この経路は公開状態APIの失敗では止まりません。公開前特例の記録済み固定総上限の変更拒否は維持します。
人間承認が無い場合だけ、`REVIEW_PRERELEASE_RECORD=<裁定ID>` で対象PR/課題本文の
`## 公開前裁定` 節にある単一の JSON コードブロックを参照できます。環境変数は参照IDです。
裁定の権限は本文とレビュー済みの [固定登録](config/prerelease-projects.json) から取得します。

登録の追加・変更は codex-watch の変更としてレビューを通してください。最初の登録は
`min-sys/updater-index` の Git common directory と既知の2規則blobです。
GitHubの既定枝commitとローカルorigin/mainの両方でblobを照合します（fetchはしません）。
公開終了条件は、`dev-standing-approval.md` への「公開日・本人原文・受領時刻」の追記PRが本線に入ることです。
既知blobが変わる、規則が無い、APIが読めない場合も特例は使えず、通常の人間承認が必要と表示します。

本文の `## 巡の履歴` は既存の表形式を使い、CLI外の発注も1行ずつ補完し、行末に
`<!-- dispatch_id=Agent発注の一意ID -->` を付けます。stateと本文をIDで突き合わせ、本文だけの行も数えます。
旧行の補完案は `bin/codex-history-backfill issue:owner/repo#N --state-dir <state写し> --output <提案本文.md>`
で生成できます（`pr:owner/repo#N` も可、`--output` 省略時は標準出力）。GitHub本文・stateは変更しません。
巡・種別・発注日時・SHA先頭7桁・レビュアーがstateと1対1の行だけIDを補い、既存IDは保持します。
未照合行と履歴節内の説明文を標準エラーに一覧で出し、残る場合は非0終了します。
説明文は移動しません。提案を確認してから本文の更新を判断してください。

特例には両方の正本が読めることと全データ行のIDが必要です。ID照合後に同種のdistinct HEADを数え、説明文は読み飛ばします。ID付きの偽区切り・壊れた表は拒否します。本文だけの短縮SHAは完全SHAへ一意に照合できる場合だけ使います。
保存済みの系列ID・固定総上限は途中で変更できません。前身系列やIDの無い旧行は補完を要求して停止します。Dの振り分けは警告のみで接続し、発注を止めません（末尾の計数手順を参照）。

裁定JSONの必須欄は次のとおりです（`tests/test_prerelease.py` に実際に通る一式があります）。

- `id`, `authority: "project_prerelease"`, `target`, `series_id`, `kind`（今回の種別）
- `base_sha`, `head_sha`, `content_hash`（既存 `round_gate.py content-hash --workdir <dir>` の値）
- `files`（基点からのGit差分の全通常ファイル）、`files_hash`（ソートした一覧を `json.dumps(..., ensure_ascii=False, separators=(',', ':'))` してUTF-8のSHA256）
- `plan`, `reason`, `rollback`, `cost`, `dispatch_reason`, `history_ref: "## 巡の履歴"`
- `decided_at`（timezone付きISO8601、未来不可）、`total_cap`（整数3〜5、今回巡以上）
- `blocking`, `invariants`, `remaining_checks`, `predecessors`（明示の配列。blockingとpredecessorsは空のみ）
- `operation: "local-read-only-review"`, `explicit_confirmation: false`
- 巡5では `round5_options: ["縮小", "前身継承で切り出し", "撤回して再設計"]`

対象は登録PJ内のローカル読取レビューに限定します。未追跡・削除・symlink・別repo・対象一覧不一致は停止します。
共有物や環境操作の許可、本人の既決・明示確認の撤回には使えません。構造検査は理由の正しさや人間承認の真偽を認証しません。
採用案・理由の意味と既決との整合は正本を書く担当の責任です。実際の起動は `-s read-only` のままです。

判定・前置き・保存には補完後の同じ巡を使います。特例だけ送信直前に本文・対象版・既定枝を再確認し、
変化・通信失敗なら未送信で停止します。排他ロックの中で `<run id>.reservation` を保存し、送信失敗でも枠は残します。
state・本文行と同じIDなので予約と実績を二重計数しません。予約が残って止まる場合は消さず、発注履歴を確認してください。
送信後の本線更新まで原子的に止める保証はありません。`CODEX_REVIEW_NO_GATE` との併用は拒否します。
既存の別系統レビュー・受領照合・Must解消・変異確認・人間によるマージ判断は省略しません。

## D の振り分けを1週間、警告だけで数える

`codex-review` は既存の点検・A/C・公開前特例の再照合と予約の後、発注直前に
`lib/routing_warn.py` を呼びます。判定が停止相当でも、部品・出力・実行の異常でも発注を続けます。
標準エラーの `routing警告:` は正常通過を含め1発注1行です。既存ゲートの拒否はそのままです。
公開前特例の予約は作成・削除せず、既存処理の結果を保持します。

adapter の指定は `CODEX_REVIEW_ADAPTER=/absolute/path/adapter.py`、既定は
`$HOME/.claude/skills/review-gate/adapter.py` です。`REVIEW_GATE_RECORD` は既存adapterが読む
発注記録JSONのパスです。未指定なら正本本文・依頼文・state・gitから作れる項目を自動作成します。
`routing-record: series_id=系列 predecessor_ids=[] base_sha=40桁SHA family_tags=["族"]` を
依頼文または正本の行頭に書けます（文字列はJSON表記も可）。正本優先、キー重複・不正値は欠落扱いです。
履歴は巡番号＋種別で束ね、各発注の `.report` のSHA・作業木ハッシュ照合と、正本「巡の履歴」内の一意な受領行を全員分確認した巡だけ `received` として渡します。
受領行は `routing-receipt: {"dispatch_id":"発注ID","status":"received","finding_family_tags":["族またはnone"],"route_content_hash":"発注時の対象別SHA-256"}` です。
自動生成の対象別ハッシュは発注前に固定し、state の `route_content_hash` に控えます（受領照合用 `content_hash` とは別）。全員のSHA・対象別ハッシュ一致を要求し、族は和集合にします。
外部記録指定時・控えのない旧state・受領証拠の不足はpending・欠落のままで、過去値や指摘なしを推測しません。受領失敗の警告理由は固定分類です。
外部指定（空文字を含む）は保持し、自動記録だけを0700専用ディレクトリ・0600排他作成で用意し、監督側で回収します。
生成の失敗・正本との競合は固定分類で警告します。別PJも同じ警告経路です。
同じ利用者が読込前後の照合の間に記録を差し替えて戻すと、別の記録による判定が警告の記録に残り得ます。発注を止める関門には影響しません（[既知の限界](docs/design/routing-record.md#既知の限界)）。
adapterへの引数は記録パス、作業場所の順。生成・判定・記録・回収の持ち時間は共有の30秒です。超過時はプロセス群を打ち切り、
`時間切れ` と記録します。先に割込みで後始末を最大0.2秒待ち、それでも残るプロセス群を強制終了します。
生成付き経路は残り時間で監督し、後始末用に判定を0.25秒、監督待ちを0.05秒早く切り上げます。旧5引数APIは従来の31秒監督です。待ちで打ち切った記録・警告は欠落する場合があります。外部のtimeoutコマンドは使いません。
adapter起動前にSIGINTの無視継承を解除します。adapterが別sessionへ切り離した子はそのadapter側の終了処理にも依存します。

`$CODEX_WATCH_DIR/routing-warn.jsonl`（未設定なら `~/.codex-watch/routing-warn.jsonl`）へ1発注1行追記します。
欄は `dispatch_id / target / kind / time(UTC) / verdict / stopped_at / reasons`。
verdictは `pass / would_block / error / invalid / timeout / missing`、段は `A / 1 / 2 / 3 / B / null`。
理由は固定分類のみで、adapterの生出力・本文・資格情報は書きません。未知の理由は「その他の判定理由」です。
記録先へ書けない場合も発注は続け、同じ警告行に `記録失敗` を添えます。その場合は件数に欠落があります。
以下は直近7日分を理由ごとに数える読取専用のコマンド（破損行は件数を表示して飛ばす）です。

```sh
python3 - <<'PY'
import collections, datetime, json, os, pathlib
now = datetime.datetime.now(datetime.timezone.utc)
counts, broken = collections.Counter(), 0
path = pathlib.Path(os.environ.get("CODEX_WATCH_DIR", str(pathlib.Path.home()/".codex-watch")))/"routing-warn.jsonl"
for line in path.read_text().splitlines():
    try:
        row = json.loads(line)
        when = datetime.datetime.fromisoformat(row["time"])
        reasons = row["reasons"]
        if (not isinstance(reasons, list) or not all(isinstance(r, str) for r in reasons)
                or row["verdict"] not in ("pass", "would_block", "error", "invalid", "timeout", "missing")
                or row["stopped_at"] not in (None, "A", "1", "2", "3", "B")):
            raise ValueError("invalid row")
        if now-datetime.timedelta(days=7) <= when <= now:
            counts.update((row["verdict"], row["stopped_at"], reason) for reason in reasons)
    except (ValueError, TypeError, KeyError):
        broken += 1
print(counts)
print("破損行:", broken)
PY
```

戻す場合は `bin/codex-review` の `# D: observation only...` とその直後の `routing_warn.py` 呼出し行を消します。
これで接続は外れます。未使用となるhelper・専用試験・本節は今回の差分とともに削除可能です。
既存JSONLと予約を消す必要はありません。停止型への切替は1週間の件数と記録自動化を見て別途判断します。
