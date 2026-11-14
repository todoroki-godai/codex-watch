履歴の補い: CLI codex-history-backfill／試験 719件成功（5件skip）／変異 陰性未実行・陽性未実行・生存未確認（commit拒否で停止）

## 入力の区分表（試験作成前）

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

## 実装と停止理由

追加: `bin/codex-history-backfill`、`lib/history_backfill.py`、README Aの6行、実例fixture、CLI試験31件、コミットarchive用変異ランナー。
既存ID付き行は変更しない。説明文は位置を保って警告する。未補完・説明文があれば提案を出力して終了1、state破損・節欠落・I/O失敗は終了2。出力先が指定stateまたは本物の `~/.codex-watch` 内なら拒否。
CLI→GitHubの操作は既存 `gh_fetch_body` の `gh issue/pr view` のみ。stateは読むだけ。本人承認の文を生成する処理なし。

コミットを試みたが、PreToolUse hook がアカウント不整合でコマンド全体を拒否した。
期待 `todoroki-godai`、現在 `matsukaze-minden`。`git add` も実行されていない。アカウント切替・フック回避はしていない。
本人指示「名義の hook で拒否されたら変更を残して報告。頭が commit」に従い、変更は未コミットで残す。
基点/現在HEAD: `531a18e026a3dca16ac53c577293bd444105443f`。新規commit SHAなし。

## 試験と変異

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

## 次回と結果ファイル

指定された外部キュー先 `/Users/matsukaze-takashi/updater/updater-index/_work/notes/codex-queue/` は、この実行環境の書込許可範囲外。2ファイルの内容を作業場所内 `.tmp/codex-queue/` に用意し、頭による転記用とする。外部の指定先に作成できたとは扱わない。
既定案: 頭が差分をレビューしてコミットし、この同じ作業場所で変異ランナーを実行、生存があれば試験/実装を修正し、全体試験を通して報告を更新する。
代案: アカウント整合した実行環境で同じ作業場所を再開する（この窓では切替しない）。

最終検査: `git diff --check` 成功。新規3 Pythonファイルの構文検査成功。`git diff` はREADMEの変更が残るため空ではなく、新規ファイルも未追跡のまま（hook拒否に従い保持）。終了条件のcommit済み変異検証・生存0・diff空は未達。
