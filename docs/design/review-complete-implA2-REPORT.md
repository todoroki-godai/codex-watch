codex-watch#38 A 実装: 試験647件成功（tests全体・652件収集／5件skip）／陰性試験0件（未実行）／陽性対照3件緑 — 未完了（commit拒否）

## 入力の区分表（試験を書く前）
期待の出所: docs/design/review-complete.md 2.1〜2.3、6章、および今回の頭の決め1〜5・Should①②。
|入力|区分・境目|置く値|期待|出所|大きさ|試験|
|---|---|---|---|---|---|---|
|発注一式|正常通し|state空、本文にAgent2件、裁定、cap3|判定・前置き・予約・保存すべて3|Should②|fake CLI|補完再開|
|通常承認|公開API失敗|完全履歴、巡3、人間承認、cap3|送信可能、特例API不要|Should①|fake CLI/関数|通常承認|
|巡とcap|2/3/5/6、cap2/3/5/6、bool/string|境界と型不正|3〜5かつcap内のみ特例|設計2.3|関数|境界|
|規則と実体|別PJ、origin偽装、公開後、既定枝に無し、未知blob|固定登録との差|通常承認へ戻す|設計2.1|Git fixture|出所|
|材料|必須欄個別欠け、空白、空集合、blocking有|空白に全角・tabも|欠落拒否、明示空集合可|設計2.2|関数|材料|
|時刻|timezone無し、未来、UTC同値|固定時計|前2者拒否、同値受理|設計2.2|関数|時刻|
|範囲|外向symlink、未追跡、別repo、対象集合不一致|実体とGit差分|特例停止|設計2.2|Git fixture|範囲|
|鮮度|gate後に本文・HEAD・規則変更、通信断|送信前再照合|未送信|設計2.1|CLI/関数|再確認|
|履歴|節無し、不正行、state読取不能、重複ID、補完行のみ|2正本の和集合|不明拒否、本文だけの行も計数|頭の決め1〜3|関数/CLI|履歴|
|申告|envだけ、本文の一語、bypass混在|出所無し|特例にならない|設計2.3|関数/CLI|申告|
|合図|予約後の送信失敗、同時予約|未完了予約|枠を消さない|設計3.3のA必要部分|関数|予約|
画面・DB・AWSは対象外のため未実行。C全体とDは実装しない。

## 実装の範囲・出所
- 開始HEAD `b96b8a9`、origin/main `bdb4d62`。前回の報告3ファイルは保持。設計AとShould①②を実装し、C全体・Dは未着手。
- 段取り表のT番号は無し（指定なし）。担当の出所として updater-index `_work/notes/rev9-review-history.md:275` の割当てを読んだ。
- 本人決定は今回の依頼のA・C・D中継原文と2026-11-13 16:43 JSTの頭の技術判断。見本HTMLは無し（画面変更なし）。
- 読んだ前身: `docs/design/review-complete.md`（A・試験区分・変異候補）、`review-complete-implA-REPORT.md`、`refactor-next-review-complete-implA.md`、指定設計レビュー `.report` 全文（Must0/Should2）。
- 現行の `lib/round_gate.py`、`bin/codex-review`、README、`tests/test_round_gate.py`・`test_codex_review_cli.py`・conftestと既存変異手順を参照した。
- test-design は前回REPORTにある rev9-audit `.claude/skills/test-design/SKILL.md` を使用（このPJ内には無い）。`~/.claude/rules/verify-checks-by-breaking.md` と `~/.claude/refs/verify-checks-by-breaking.md`、`~/.claude/rules/review.md` の補完規則も読んだ。
- updater-indexのローカルorigin/main上の2規則を読んだ。Git common dirの絶対実体と100644のblobを確認し登録。fetch・実環境のGitHub照合・配布は未実行。

## 既存の再利用と7段
変更前の `git grep -n -E 'project_prerelease|policy_blob|history_complete|dispatch_id|prerelease-projects' -- lib bin tests README.md` は0件。
既存の承認・上限・前身・state・内容hash・本文追記処理は現物を読んで再利用した。不存在をリポジトリ全体へ拡張しない。
|項目|止めた段と理由|
|---|---|
|通常承認|㋑ `decide()` と既存承認・総上限解析を利用。公開前APIを呼ぶ前に通す|
|登録・正本照合|㋐明示依頼、㋑既存Git・gh読み取り、㋒json/pathlib/subprocessで足りる。新依存無し|
|材料と範囲|㋐信頼境界、㋑既存content-hashとGit差分、㋒re/json/hashlibで足りる|
|履歴補完|㋐Should②、㋑既存state・本文表を利用、㋒ID集合と旧行の複合識別子の照合|
|送信前再確認・予約|㋐必要、㋑既存gate結果を再利用、㋓macOS標準fcntl排他・排他的ファイル作成|
|試験・変異|㋐削減不可、㋑既存fake CLI・独立line tracerの方法を再利用、㋒stdlibのarchive/diff/trace|
|説明と報告|㋐明示依頼、㋑READMEと指定REPORT。新しい仕組み無し|

## Aに必要なCとの最小重なり・制限
- bodyとstateの和集合の巡をgate・前置き・保存へ渡す。自動特例は全行ID必須。旧行は通常経路で日時/短SHA/種別/レビュアー/巡がstateと完全一致する1行だけ重複排除し、不一致の行を減らさない。
- 種別ごと・前身系列ごとの新計数はCまで行わない。Aの特例は前身ありを拒否し、全種別の合算上限を守る。履歴取得不能や旧行の識別不能は自動特例を通さない。
- 今回はPR/課題本文だけを裁定の正本に対応させた。追跡されたローカル作業記録への取得口は未対応で停止する。CLI外の発注は頭が本文に補完する契約で、Agent/Taskのセッションを自動探索した完全性保証ではない。
- JSONの意味（理由の正しさ、既決と矛盾しないこと）の認証は正本担当の責任。実体・版・対象一覧は照合し、`-s read-only`を固定した既存起動だけ許可する。自由な依頼文から操作の意味を推測して権限を付けない。
- 固定総上限・系列IDを保存済みの記録から変更する再裁定は未対応で停止する。巡5では3択の記録を要求する。送信後の本線更新との原子性は保証しない。
- 予約は特例だけ。通常の人間承認に公開状態の通信を追加しない。予約後の送信不明は枠を保持し、state/本文/予約の同一IDは1件にまとめる。

## 呼出し元の確認
`git grep -n -E '(decide\(|run_gate\(|record_round\(|prerelease_context|prerelease_evidence)' -- lib bin tests` の全結果を `.tmp/implA2-callers.log` に保存。
|変更関数・値|製品の全呼出し元|確認|
|---|---|---|
|decide任意文脈|run_gateの通常判定と特例判定|従来の直接試験とA境界試験|
|run_gate引数と返値|round_gate.main gate→bin/codex-review|CLIの通常承認、特例、bypass、前置き・保存|
|record_round行ID|round_gate.main record→bin/codex-review送信後記録|既存record試験と補完後の通し試験|
|gate CLI引数・予約分岐|bin/codex-reviewの初回判定と送信直前再確認|非送信点検、変更後未送信、同時予約|
|新prerelease各関数|command←git/evaluate、git←evaluate、section←history/record、record/validate_record/history←evaluate、history/evaluate←run_gate|関数区分とfake CLIで確認|
|state追加キー|read_state_fileと既存読み手は任意キーを保持/無視、record_roundはauthorityを読む|既存パッケージ試験|
既存のtarget_total_rounds・ledger・content_hashの本体は変更しない。Cへの全体移行は未実装。

## 環境ごとの差
|環境|経路・設定・データの違い／今回の実施|
|---|---|
|ローカル|登録PJ実体・既定枝規則・本文正本の取得境界。実測は一時Gitとfake gh/codexだけ|
|dev|常時承認の規則は別。今回は接続・読み書き無し|
|stg|書き込みは公開前特例の対象外。今回は接続・読み書き無し|
|prod|同じく対象外。今回は接続・読み書き無し|
DB試験は未実行（対象外）。資格情報の取得・表示・保存、LLM呼出し、gh書き込み・名義切替、push・枝操作は行っていない。

## 試験・変異
全パッケージの最終実測: `python3 -m pytest tests -q` → 647 passed, 5 skipped in 253.50s（652件収集）。Python 3.14.7、pytest 9.0.2。初回の失敗は今回の旧行二重計数・既存試験の保存anchor変更が原因で修正した。「前からある赤」とは呼ばない。
全出力は `.tmp/implA2-*.log`。変異は原本commit後のarchiveだけを変更する。陽性対照、独立diffと実行行traceを分けて確認する。

- 5件skipは実gh/keychainを使うopt-in4件とreview専用試験のimpl側1件。実物のGitHub・LLM・AWSへ届かない一時fixtureだけで検証した。
- 陽性対照3件は補完した本文だけの2発注からの巡3通し、通常の人間承認と公開API失敗、意味の同じtimezone表現への変更。これらは最終の全試験に含む（合計へ再加算しない）。
- Aの追加試験75件を含む。材料の個別欠落・Unicode空白・数値と型・時刻同値/未来・別PJ/origin偽装・公開後/規則欠落・対象一覧/内容の変更・symlink・未追跡・履歴補完/破損・予約の同時実行/保持・再照合・固定cap/系列変更を探索した。
- 変異の予定は `tests/check_prerelease_mutations.py` の8陰性と1意味保存変異。①PJ実体削除、②公開版の比較無効、①規則ループ削除、④申告の失敗を成功扱い、②本文イベントを捨てる、②未来時刻を受理、④鮮度の比較無効、③capと巡の入替え。本文イベント消失・時刻・鮮度・数値入替えは委譲側の4条件とは種類が違う回避候補。
- **ただし原本commitができず、変異は1件も適用していない。** 8件赤・実行分岐着弾・生存0を主張しない。意味保存のソース変異も未実行。runner自体は構文確認だけで未実測。
- 再現コマンド全文（commit可能な窓で、原本をcommitしstatusが空になった後）: `python3 tests/check_prerelease_mutations.py`。git archive HEADから作る独立コピーに1件ずつ変異し、各 `mutation.diff` と独立line traceの `executed.log`、全出力 `pytest.log`、集計 `results.json` を `.tmp/implA2-mutations/` に残す構成。ログをcommitしない。cap変異には式・比較時のcap/巡/比較結果をtraceする。
- 最終 `git diff --check` は成功。元の作業場所に変異は適用していないが、実装の未commit差分があるため `git diff` は空ではなく、cleanではない。

## commitと引渡しの停止理由
commitのSHAは無し。HEADは開始時の `b96b8a977e1f0c67706e94b61a763f668c0e2cb6` のまま。`git add ...; git diff --cached ...; git commit ...` を含むコマンド全体がPreToolUseフックに実行前拒否され、stageも未実施。
拒否理由の原文: `アカウント不整合ブロック: owner='todoroki-godai' の専用configは ghアカウント 'todoroki-godai' を期待しますが、write時点では 'matsukaze-minden' です。`
`.claude/codex-github-account` の実物は `todoroki-godai` だが、今回もフックの判定は変わらなかった。gh auth switch・別コマンドによる迂回・共有設定の変更はしていない。宣言があればcommitできるという見込みを成功扱いにしない。

指定のupdater-index `codex-queue/refactor-{result,next}-review-complete-implA2.md` は書き込み許可外であり、今回の個別指示もupdater-indexは読み取り専用。指定先へは未作成。作業場所の `docs/design/refactor-result-review-complete-implA2.md` と `refactor-next-review-complete-implA2.md` に転記用を保存した。

次は、書き込み名義のフックを扱える担当が通常の経路でcommit可能な状態を用意し、実装・README・区分表・試験を確認してcommitし、変異runnerを実測する。緑残存・未着弾があれば直し、原本commitから再試験する。C・Dや配布に進めない。今回の実装には独立したcold reviewもまだ無い。

未追跡の追加コードも含む最終呼出し元の列挙は `git grep --no-index -n -I -E 'decide\(|run_gate\(|record_round\(|pre\.(evaluate|history|validate_record)|(^|[^[:alnum:]_])(command|section|history|record|validate_record|evaluate)\(' -- lib/prerelease.py lib/round_gate.py bin/codex-review tests/test_prerelease.py`。全出力を `.tmp/implA2-all-callers.log` に保存。最終HEAD不変・index未変更・diffチェック成功を再確認した。
