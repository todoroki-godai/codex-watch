履歴の補い（巡1の直し）: Must1・Should1 を直した／試験 724件成功／変異は頭の commit 後に回す

## 入力の区分表（試験作成前）

今回の追加分（出所: 今回の依頼・レビュー Must1 / Should1）。正常通しは下表の `test_real_history_gate`。

| 入力 | 区分・境目 | 置く値 | 期待 | 期待の出所 | 大きさ | 試験名 |
|---|---|---|---|---|---|---|
| stateと履歴 | 正常通し | 実例2行と対応state | 対応するIDのみ補完 | 今回の依頼 | CLI→特例 | test_real_history_gate |
| 必須値 | 種別・レビュアー欠落と既定値行 | 両方欠落／各々欠落、コード／codex行 | 未補完を警告 | Must1 | CLI | test_missing_values_do_not_default |
| 表以外 | 区切り・見出しの前方一致 | `|--- 説明文`／`| 巡 |`から始まる説明 | 維持して警告 | Should1 | CLI | test_table_like_description |
| 表形式 | 全体が見出し・区切り | 正常見出し／区切り | 警告しない | Should1 | CLI | test_real_history_gate |

数字・時刻は既存正常fixtureを使用。継ぎ目は CLI→特例、できない操作は欠落値からの補完、文字は欠落と前方一致、合図は終了1と警告で確認する。

期待の出所: 課題 todoroki-godai/codex-watch#40 と今回の本人指示1〜3。正常系は #2023 の実際の2行。

| 入力 | 区分・境目 | 置く値 | 期待 | 期待の出所 | 大きさ | 試験名 |
|---|---|---|---|---|---|---|
| 本文とstate | 正常通し・継ぎ目 | #2023の2行とstate写し | 正確なIDを補い特例判定通過 | 指示2 | CLI→特例判定 | test_real_history_gate |
| 候補数 | 0・1・2 | 欠落・正常・重複state | 1だけ補う、それ以外非0 | 指示1 | CLI | test_ambiguous |
| 履歴行 | 同じ複合キー2行 | 行重複 | 補わない・非0 | 1対1条件 | CLI | test_ambiguous |
| ID | 重複・使用済み・別run | 同じID/別行のID/別対象 | 補わない・非0 | 1対1条件 | CLI | test_ambiguous |
| 既存ID | 完了からの操作 | IDあり行 | バイト単位で保持・再実行不変 | 指示1 | CLI | test_existing |
| 説明文 | 表以外・空行 | 箇条書き/空行 | 説明文一覧警告・移動しない/空行許可 | 指示1 | CLI | test_description |
| 時刻・文字 | 正確な文字列・欠け | 時刻秒違い、5キー各欠落、空白付セル | 不一致は拒否・セル周囲空白は許可 | 1対1条件 | CLI | test_ambiguous/test_semantic |
| ID文字 | 長さ0/1/160/161・禁止文字 | 空/短/上限/超過/空白 | 有効IDのみ補完 | dispatch_id書式・指示1 | 関数 | test_id_boundary |
| 状態入力 | 壊れた行・キー重複・読取不可 | 不正state/不存在dir | 非0・本文出力なし | 1対1条件 | CLI | test_bad_state |
| 対象・節 | issue/pr・欠落・重複 | target/節の各形 | 読取だけ・欠落/重複非0 | 指示1 | CLI | test_target/test_section |
| 出力・合図 | stdout/ファイル・失敗終了 | 部分成功・state内出力 | 終了コードが全行成功を保証・stateへ書込拒否 | 指示1・共通制約 | CLI | test_output/test_output_protected |

6つの問い: 数字=候補数とID長、継ぎ目=CLIから特例判定、時刻=秒まで文字列一致、できない操作=曖昧補完と既存ID上書き禁止、文字と欠け=5キー・ID・空白、合図=未照合時の非0。時刻の現在値依存・DB・画面は無関係。

## 前回の実装と停止理由（当時の記録）

追加: `bin/codex-history-backfill`、`lib/history_backfill.py`、README Aの6行、実例fixture、CLI試験31件、コミットarchive用変異ランナー。
既存ID付き行は変更しない。説明文は位置を保って警告する。未補完・説明文があれば提案を出力して終了1、state破損・節欠落・I/O失敗は終了2。出力先が指定stateまたは本物の `~/.codex-watch` 内なら拒否。
CLI→GitHubの操作は既存 `gh_fetch_body` の `gh issue/pr view` のみ。stateは読むだけ。本人承認の文を生成する処理なし。

コミットを試みたが、PreToolUse hook がアカウント不整合でコマンド全体を拒否した。
期待 `todoroki-godai`、現在 `matsukaze-minden`。`git add` も実行されていない。アカウント切替・フック回避はしていない。
本人指示「名義の hook で拒否されたら変更を残して報告。頭が commit」に従い、変更は未コミットで残す。
基点/現在HEAD: `531a18e026a3dca16ac53c577293bd444105443f`。新規commit SHAなし。

## 前回の試験と変異（当時の記録）

追加試験: `python3 -m pytest tests/test_history_backfill.py -q` → 31 passed。
初回のfixture名衝突（stateディレクトリ）を修正して上記成功。製品の赤ではなく追加試験の準備不備。
`python3 -m pytest tests -q` → **719 passed, 5 skipped in 274.97s**（パッケージ全体724件）。失敗0件。DB試験は対象外。実GitHub本文の更新・実発注・実環境の特例判定は行っていない。
#2023 fixtureは実際の2行・選択した7フィールドだけのstate写し。`body.md` は説明文を含む原本の履歴節、`table.md` は説明文を除いた表。CLIが説明文を移したものではない。
特例への正常通しは、既存 `tests/test_prerelease.py::case` の固定PJ/GitHub fixtureに実履歴とstateを渡して `prerelease.evaluate` の全境界を通過させたもの。

変異は**未実行**。今回の変更がコミットできず、「変異はcommit済み状態から」の条件を満たせないため。生存0を確認したとは扱わず、未完了。
再開コマンド（頭が変更をコミットした後）: `python3 tests/check_history_backfill_mutations.py`。
ランナーは `git diff HEAD` が空であることを要求し、HEAD archive内だけで変更する。各非空diffを `mutation.diff` に、独立line tracerによる実行行と入力を `executed.jsonl` に別保存し、pytest終了コードと失敗を確認する。証拠は作業場所内 `.tmp/history-backfill-mutations/`。最終 `git diff` と `git diff HEAD` が空かも検査する。

| 変異 | 種類 | 当てる試験 | 現在 |
|---|---|---|---|
| N1 ID追加を除去 | ①守る処理を消す | real_history_gate | 未実行 |
| N2 another-runへ置換 | ②意味を壊す | real_history_gate | 未実行 |
| N3 先頭にも末尾stateのID | ③入れ替える | real_history_gate | 未実行 |
| N4 未照合/説明文でも0終了 | ④検査を無効化 | description/ambiguous | 未実行 |
| N5 最初の行だけ補完 | 部分補完 | real_history_gate | 未実行 |
| N6 target照合を無効化 | ID破壊と別種の回避1 | other-target | 未実行 |
| N7 state重複キーを許容 | ID破壊と別種の回避2 | duplicate-key | 未実行 |
| N8 使用済みIDの拒否を除去 | ID再利用 | used-id | 未実行 |
| P1 boolからintへの同義変換 | 陽性・意味不変 | 追加31件全部 | 未実行 |
| P2 state探索順を逆順 | 陽性・意味不変 | 追加31件全部 | 未実行 |

探索した入力クラス・変換は冒頭の区分表に記載。委譲はなし（本人の他LLM禁止に従った）。

## 7段と既存の道具

`git grep -n -i -E 'backfill|fingerprint|Counter' -- lib bin` で既存の履歴fingerprint（`lib/prerelease.py`）、トークン補完（`lib/round_gate.py`）を確認。後者はGitHub本文へ書き込むため今回のCLIには使用しない。
`git grep -n -E 'section\(|RE_ID|parse_target\(|gh_fetch_body\(|read_state_file\(' -- lib bin tests/test_prerelease.py` で既存の入力検査・節抽出・読取APIを確認して再利用した。「同等機能が無い」と件数を伴わず断定はしない。

| 足した項目 | 7段の停止点と理由 |
|---|---|
| CLI入口と照合 | ㋖。㋐明示依頼、㋑既存読取APIを使用、㋒argparse/Counter/re/Pathで十分、㋓gh viewを再利用、㋔新規依存不要、㋕1行で安全な1対1照合と一覧警告を表せないため小さな専用処理 |
| ID書式・節・state・target・GitHub読取 | ㋑既存 `RE_ID`, `section`, `read_state_file`, `parse_target`, `gh_fetch_body` |
| READMEとfixture | ㋐明示依頼・実例の出所確保 |
| 試験・変異ランナー | ㋑既存pytest fixtureとarchive/line trace手法を使用、㋖今回用の最小ケース一覧。変異実行は未完 |

## 呼び出し元と影響

既存関数・値の変更はなし。追加関数 `history_backfill.backfill` の呼び出し元は同モジュール `main`、`main` の呼び出し元は `bin/codex-history-backfill` とモジュールの `__main__`。CLI入口を通る31件で確認した。
追加分を含めた検索: `git grep --no-index -n -E 'backfill\(|from history_backfill import main' -- lib/history_backfill.py bin/codex-history-backfill tests/test_history_backfill.py`。
既存の依存先 `prerelease` と `round_gate` の呼び出し元への回帰はパッケージ全体719件成功で確認。skip 5件の実行証拠は無い。

## 読んだもの

- 段取り表の該当行: 無し（依頼の指定欄が空）。今回は課題#40と「今回の作業」の明示内容を対象にした。
- 本人の決定の出所: 本依頼の「入れる (Recommended)」・main-index経由・2026-11-15 07:04:09 JST、および `gh issue view 40 -R todoroki-godai/codex-watch`。
- 見本HTML: 無し（CLIとMarkdown本文が対象）。
- 前身の設計と巡の履歴: 指定 `.tmp/prerelease/backfill.py`, `REPORT.md`, `check_gate.py`, `body.md`, `body-new.md`（読み取り）。REPORTの当時の停止原因とbody-newの説明文移動も確認。
- README「公開前の巡3〜5（A）」、`lib/prerelease.py`、`lib/round_gate.py` のtarget/state/履歴/特例/本文取得・記録経路、`tests/test_prerelease.py`。
- test-design: 作業場所には無く、参照元作業場所 `/Users/matsukaze-takashi/updater/updater-index/_wt.noindex/2023-design/.claude/skills/test-design/SKILL.md` を発見して使用。
- 既存変異ランナー `tests/check_prerelease_implA3_mutations.py`、commitスキル（今回の明示的commit指示が承認要件に優先）。

| 環境 | 経路・設定・データの違い／今回の扱い |
|---|---|
| dev | 接続・読み書き無し |
| stg | 接続・読み書き無し |
| prod | 接続・読み書き無し |

環境ごとの実設定差は未調査（依頼外）。今回のCLI処理に環境別分岐は無し。

## 前回の次回と結果ファイル（当時の記録）

指定された外部キュー先 `/Users/matsukaze-takashi/updater/updater-index/_work/notes/codex-queue/` は、この実行環境の書込許可範囲外。2ファイルの内容を作業場所内 `.tmp/codex-queue/` に用意し、頭による転記用とする。外部の指定先に作成できたとは扱わない。
既定案: 頭が差分をレビューしてコミットし、この同じ作業場所で変異ランナーを実行、生存があれば試験/実装を修正し、全体試験を通して報告を更新する。
代案: アカウント整合した実行環境で同じ作業場所を再開する（この窓では切替しない）。

最終検査: `git diff --check` 成功。新規3 Pythonファイルの構文検査成功。`git diff` はREADMEの変更が残るため空ではなく、新規ファイルも未追跡のまま（hook拒否に従い保持）。終了条件のcommit済み変異検証・生存0・diff空は未達。

## history-backfill2 の実行結果（今回）

対象 HEAD `31b76e4e41c6cfcfe03cac390d47ca9874eb9a20`。開始時に `git diff HEAD` が空であることを確認。HEAD の runner を実行すると N1〜N3 は赤、N4 は実行行の証跡が空で停止した。トレーサーが `Target` を JSON 化できず CLI を異常終了させ、試験を見かけ上通していた。`json.dumps` に `default=repr` を追加して記録を修正し、HEAD archive を対象に再実行した。

N1〜N10 はすべて赤、P1・P2 は各31件緑、生存0件。各変異の非空差分と実行行は `.tmp/history-backfill-mutations/<変異名>/mutation.diff` と `executed.jsonl`、結果は同ディレクトリの `results.json`。N1〜N8・P1〜P2 は前回表の区分。追加 N9 は不正IDの書式検査を除去（invalid-id）、N10 は既存IDの保護を無効化（existing）；前回の対象照合除去・重複キー許容とは別種。入力区分と変換は冒頭の表および前回の変異表を参照。全変異はコミット済み HEAD archive 内に適用し、実行後に `git diff` と `git diff HEAD` が空であることを runner が確認した。その後、runner に記録の修正と N9・N10 を反映したため、現在は runner と本報告の差分が残る。再実行にはこの差分のコミットが必要。

7段: ㋐着弾確認と陽性対照は依頼上必要、㋑既存 runner と pytest のケースを使用、㋒標準ライブラリ `json.dumps(default=repr)` を利用、㋓既存 Python 実行環境、㋔導入済み pytest、㋕シリアライズ修正は1行、㋖追加は既存一覧の2行。既存の入力区分表を使用し、新規の試験関数は追加していない。runner の呼び出し元は手動実行のみ（`git grep -n 'check_history_backfill_mutations'` で報告書以外の呼び出し元なし）。

読んだもの: 今回指定の本報告と `tests/check_history_backfill_mutations.py`、`lib/history_backfill.py`、`tests/test_history_backfill.py`、前回記載の参照先 test-design。段取り表の該当行・本人の決定の出所・見本 HTML・前身の設計と巡の履歴は今回の指定欄が空のため無し（前回の参照履歴は上記「読んだもの」に記載）。環境差は上記の表どおり実設定未調査、dev/stg/prod には接続・読み書きなし。

指定の2つの結果ファイルの保存先は書込許可範囲外で作成できない。作業場所内 `.tmp/codex-queue/` に転記用を用意した。commit は今回の明示指示により行わない。

全体試験: `python3 -m pytest tests -q` → 719 passed、5 skipped、330.08秒（計724件）。skip は未実行。DB への接続・検証は未実行。

## history-backfill3 の修正

state の5項目に空・欠落がある候補は照合せず、対象の履歴行を未補完として警告する。ID重複の検査には欠落stateも残す。表見出しは既存 `ROUND_ROW_HEADER` と全体一致、区切りは行全体が Markdown の区切りの形である場合に限って除外する。

試験追加前に冒頭の区分表を追記。修正前 `python3 -m pytest tests/test_history_backfill.py -q -k 'missing_values_do_not_default or table_like_description'` は5 failed（欠落3・説明文2）を確認。変異 runner に N11〜N14 を追加したが、明示指示に従い今回の変異は未実行。前回の変異結果は今回の変更の検証にはならない。

修正後 `python3 -m pytest tests -q`: 724 passed、5 skipped、314.12秒（計729件）。DB 接続試験は未実行。runner の置換対象は各1か所と静的に確認したが、変異の成否は未確認。

7段: ㋐依頼と誤補完防止に必要、㋑`git grep -n -E 'kind_label|reviewer|^.*巡.*\\||history_backfill|separator' -- lib tests bin` で既存照合・表見出しを確認、㋒標準の `re.fullmatch`、㋓既存 Python、㋔既存 pytest、㋕既定値の除去と既存見出し使用、㋖不足する照合条件・区切り形式だけ追加。既存定数は `ROUND_ROW_HEADER` を再利用。

呼び出し元: `git grep -n -E 'backfill\\(|from history_backfill import main|check_history_backfill_mutations|ROUND_ROW_HEADER' -- lib bin tests docs/design/history-backfill-REPORT.md` で `backfill` は `history_backfill.main` のみ、`main` は `bin/codex-history-backfill` と同モジュールの `__main__`。CLI正常系・欠落・警告を試験し、全体試験で他の既存定数利用箇所を確認する。runner は手動実行であり今回は未実行。

読んだもの: 指定レビュー全文、`lib/history_backfill.py`、`tests/test_history_backfill.py`、既存 runner・fixture・本報告、参照元 `/Users/matsukaze-takashi/updater/updater-index/_wt.noindex/2023-design/.claude/skills/test-design/SKILL.md`。段取り表該当行・本人の決定の出所・見本HTML・前身の設計と巡の履歴: 無し（今回の必須欄が空）。

| 環境 | 経路・設定・データの違いと今回の扱い |
|---|---|
| dev | 接続・読み書きなし、実設定差は未調査 |
| stg | 接続・読み書きなし、実設定差は未調査 |
| prod | 接続・読み書きなし、実設定差は未調査 |

指定の queue 出力先は書込許可範囲外のため未作成。作業場所内 `.tmp/codex-queue/` に転記用を置く。commit は明示指示に従い行わない。次は頭が差分を確認・commit 後、変異 runner を回して全件の着弾と結果を確認する。
