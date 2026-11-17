# レビュー報告の1行目の受領検査（claude-config#148）

起点: `origin/main` = `314904feefd347e66fdefb7a16d12325f365c033`。実装コミット: `12da51b`。

受領時に1行目の形式を検査し、不正な報告を受領不可とする。理由付きの保留は受領できる。

## 実装と既存方式

- `lib/round_gate.py:337` の `check_verdict_line()` が先頭の物理行だけを検査する。空白での前処理や本文からの結論探索はしない。許可するのは完全一致の `実装着手可`・`設計修正要`、および `判定保留: ` に続けて同じ行に空白以外の理由があるものだけ。
- `lib/round_gate.py:396` の既存の `check_receipt()` の成功出口へ接続。既存の `ReceiptCheck(status, reason)`・`rejected`・CLIのexit 4・JSONの `status/reason` を使い、形式を直して出し直すよう表示する。
- 既存の受領CLIを呼ぶ `bin/codex-status:100` と、同関数を使う履歴集計にも効く。受領不可の報告の内容は既存どおり確認できる。
- `bin/codex-review:214` の発注文を同じ3形式に統一。`lib/report_rebuild.sh:19` に理由付き保留の表示・再構築を追加。過去の判定語は再構築・表示の互換性を維持するが、新たな受領では拒否する。
- 判定の意味や保留理由の妥当性、本文との矛盾は検査しない。自動再発注は行わず、既存の受領不可の出口から出し直しを要求する。

## 入力の変異と陽性対照

`tests/test_verdict_line.py` を実行。陰性は受領CLIのexit 4と `rejected`、新しい検査単体の拒否を両方確認する。これにより、改行を加えた試験が既存ハッシュ照合だけで止まった結果に依存しない。

この表の赤は受領拒否、緑は受領可を意味する。期待する拒否を確認するpytest自体は成功する。

| クラス | 適用した入力・変換 | 結果 |
|---|---|---|
| 値 | `判定保留`（理由なし） | 赤 |
| 条件 | `マージ可` に置換 | 赤 |
| 枝 | 先頭空行／報告全体を空にする（2件） | 赤／赤 |
| 順序 | 1行目を `対象差分を確認中`、2行目に `実装着手可` を移動 | 赤 |
| 陽性1 | `実装着手可` | 緑 |
| 陽性2 | `設計修正要` | 緑 |
| 陽性3 | `判定保留: 前の回の内容と照合できないため` | 緑 |
| 追加・装飾 | `**実装着手可**` に変換 | 赤 |
| 追加・接尾辞 | `実装着手可（Must 0件）` に変換 | 赤 |
| 追加・空白クラス | 理由をTAB・全角空白・NBSPだけに置換 | 赤 |
| 追加・行境界 | `判定保留: ` の理由を次行へ移動 | 赤 |
| 追加・制御文字 | ANSI色制御列で結論を囲む | 赤 |
| 追加・エンコーディング印 | 結論の先頭にBOMを付加 | 赤 |
| 陽性・行末 | 理由付き保留をLF／CRLFに変換（2件） | 緑／緑 |

入力の探索クラスは値、語彙、空入力、順序、表示装飾、接尾辞、Unicode空白、行境界、端末制御、BOM、行末表現。

## 検査コード自体の変異

`python3 tests/check_verdict_line_mutations.py` で作業木内 `.tmp/verdict-line-mutations/` の隔離コピーだけを書き換えて実行。
変換元が1か所であること・元ソースの不変をassertし、構文・importエラーは赤の根拠にしない。
結果は `evidence/verdict-line-mutations.json`、詳細ログは各コピーの `pytest.log`。

この表の赤は欠陥を入れた検査をpytestが検出した結果。緑のまま残った欠陥は0件。

| 変異 | 変換 | 結果 |
|---|---|---|
| 値 | 保留の接頭辞から `: ` を削除 | 赤・2 failed |
| 条件 | 許可語に `マージ可` を追加 | 赤・1 failed |
| 枝 | 空報告の既定値を `実装着手可` に変更 | 赤・2 failed |
| 順序 | 先頭行から全行の結論探索に変更 | 赤・1 failed |
| 追加1・配線 | 受領側の検査結果の拒否分岐を無効化 | 赤・9 failed |
| 追加2・障害方針 | 新検査の例外を通過から拒否へ反転 | 赤・1 failed |
| 陽性対照 | 許可語のtupleを同じ要素のsetに変更 | 緑・18 passed |

追加の2件は、列挙した入力変換とは異なる、呼び出し配線と障害処理方針への変異を実際に適用した。

## 検査失敗時の通過

`test_fail_open_does_not_disable_existing_hash_check` で、新検査の `startswith()` の実行時だけ `RuntimeError` を注入。
SHA・内容ハッシュが一致していれば `check_receipt()` が `ok` を返すこと、一方SHA不一致は既存どおり `rejected` になることを確認した。
さらに例外時の戻り値を拒否に変える変異で、当該試験が赤くなることも確認した。

## 実行結果

- 関連6ファイルと新試験: 280 passed。
- 報告の再構築試験（理由付き保留追加後）: 15 passed。
- 新規契約試験: 18 passed（コード変異の陽性対照でも確認）。
- コード変異: 欠陥6件すべて赤、等価な陽性変換1件は緑。
- 最終の受領・履歴集計・再構築の関連試験: 260 passed。
- 最終の発注・プロンプト側試験: 35 passed。
- 全体回帰試験: **1007 passed, 5 skipped, 34 failed**（590.29秒）。失敗は既存の `test_progress_overdue.py::test_estimate_record` 34件のみ。今回の関連295件（260件＋35件）はすべて成功。
- 比較対照: `git archive origin/main bin lib templates tests` のコピーで `-k test_estimate_record` を実行し、同じ34件すべての失敗を再現（34 failed, 20 deselected）。`bin/codex-impl:233` の `CODEX_IMPL_AWS_STATE: unbound variable` が原因で、関連する本体・AWSヘルパー・当該テストに今回の差分はない。

試験データをworktree内の `.tmp/` に置いた最初の実行では、未初期化の試験用ディレクトリから親のGitリポジトリと `.claude/codex-github-account` を拾い、偽ghの対象外の名義照合で失敗した。
本体を変えず `GIT_CEILING_DIRECTORIES="$PWD/.tmp"` で親探索を止めて再実行する。
試験用Gitリポジトリ自身の探索は維持する。再実行のコマンド:

```sh
GIT_CEILING_DIRECTORIES="$PWD/.tmp" TMPDIR="$PWD/.tmp" \
  python3 -m pytest -q --basetemp=.tmp/verdict-full-isolated
```

実レビューの発注、push、PR作成、マージは行っていない。グローバルのrulesは読むだけとし、変更は本worktree内に限定した。

## コード巡1 Must: LF以外の行境界による回避の修正

2026-11-17、対象 `654f5f3` の `check_receipt()` へ指摘そのものの入力と一致する期待SHA・ハッシュを渡し、VT・FF・NELの3種類すべてで `ok` を再現した。今回の修正commitは `2f2b9da`。

### 修正箇所と7段

- `lib/round_gate.py:318`: `split_receipt_lines()` を追加。LFで分割し、LF直前のCRを1文字だけ取り除く。CR単独・重複CR・他の制御文字はそのまま残す。
- `lib/round_gate.py:327`・`:385`: 申告の読み取りと欠落時の表示も同じ分割を使う。
- `lib/round_gate.py:346`: 1行目の検査に加え、報告全体のC0（水平タブを除く）・DEL・C1・LS/PSを拒否する。LFとCRLFは分割時に除かれる。既存の検査例外時の `ok` は維持。
- `lib/round_gate.py:1582`・`lib/routing_record.py:129`: 受領CLIと履歴集計で `open(newline="")` を使い、読込時のCR単独→LF変換による回避を防ぐ。
- `tests/test_verdict_line.py`: 再現入力、制御文字の挿入、正常な改行、読込経路の確認を追加。既存の障害注入は使用する文字列操作に合わせて追従。履歴試験は期待ハッシュを一致させて確認する。

㋐は必須関門の回避を塞ぐため必要。㋑として先に `lib/`・`bin/`・`tests/` の行分割、単一行検査、制御文字処理を検索した。`lib/round_gate.py:165` の `is_single_line()` と `bin/_codex_common.sh` の利用箇所はあったが、前者は `splitlines()` に基づく単一値の検査であり、LF/CRLFだけで報告を分割する部品は無かった。`prerelease.py`・`routing_record.py`・`history_backfill.py` の既存分割も `splitlines()` だった。

**㋒で止めた**。`split("\n")`・文字コード比較・通常のファイル読込設定だけを使用。新依存・正規化の層・専用クラスは追加していない。

### 入力の変異・対照

この表の「赤」は不正入力が拒否されたこと、「緑」は正常入力が受領されたこと。pytest自体はその期待を確認して成功している。

| 分類 | 探索した入力クラスと実際の変換 | 結果 |
|---|---|---|
| 値 | 指摘の入力そのもの: `実装着手可<sep>read_sha=SHA<sep>content_hash=HASH\n設計修正要`。sepをVT・FF・NELへ置換 | 各赤・3件 |
| 条件 | C0からHT/LF/CRを除く29文字、DEL/C1の33文字、LS/PSの2文字。理由末尾・SHA申告末尾・本文へ各1文字挿入 | 64文字×3位置、全192件赤 |
| 枝 | 全改行をCR単独へ置換 | 赤（関数・CLI経由のstatus・履歴） |
| 順序 | 先頭を経過報告、2行目を結論にする（前回orderの再実行） | 赤 |
| 追加の入力探索 | 全改行をCRCRLFに置換／報告末尾にCRを追加／理由末尾をCRCRLFにする | 各赤・3件 |
| 陽性1 | `実装着手可` を先頭行にし、LF／CRLFで組み立てる | 両方緑 |
| 陽性2 | `設計修正要` を先頭行にし、LF／CRLFで組み立てる | 両方緑 |
| 陽性3 | `判定保留: 理由`（実試験は理由文あり）を先頭行にし、LF／CRLFで組み立てる | 両方緑 |
| 陽性追加 | 理由・申告末尾・本文に水平タブを含み、LFとCRLFを混在させる | 緑 |

3結論×2改行は関数・status（内部で受領CLIを実行）・履歴の3経路で確認。制御文字試験は `check_verdict_line()` 単体と、一致するSHA/ハッシュを渡す `check_receipt()` の双方で拒否を確認した。申告の不備だけで止まった結果には依存しない。VT/FF/NEL/CR区切りは申告パーサ単体でも `(None, None)` を確認。

### 前回の入力変異11種の再実行

| 前回の変異 | 今回の結果 |
|---|---|
| value: `判定保留` のみ | 赤 |
| condition: `マージ可` | 赤 |
| branch-blank: 空の1行目 | 赤 |
| branch-empty-report: 報告なし | 赤 |
| order: 結論が2行目 | 赤 |
| extra-decoration: `**実装着手可**` | 赤 |
| extra-suffix: 結論へMust件数を付記 | 赤 |
| extra-space-reason: タブ・全角空白・NBSPだけの保留理由 | 赤 |
| extra-cross-line-reason: 保留理由が次行 | 赤 |
| extra-control-prefix: ANSI装飾で結論を囲む | 赤 |
| extra-bom-prefix: BOMを結論の前に追加 | 赤 |

`-k negative_receipt_cli` を単独再実行して **11 passed**。各入力について受領CLIのexit 4・`rejected` と、判定行検査単体の拒否を確認。ログは `.tmp/verdict-control-old11.log`。

### 実装をわざと壊す変異

以下の赤は、隔離コピーの実装へ欠陥を適用してpytestがassertion failureになったこと。構文・importエラーは赤に数えない。既存runnerを拡張して実際に全変換を適用し、製品2ファイルの元バイト列が不変であることも検査した。差分とログは `.tmp/verdict-line-mutations/<name>/mutation.diff`・`pytest.log`。集計・変換文字列・ファイルハッシュは `evidence/verdict-line-mutations.json`。

| 変換 | 結果 |
|---|---|
| 前回value: 保留の接頭辞から `: ` を削除 | 赤・2 failed |
| 前回condition: 許可語にマージ可を追加 | 赤・1 failed |
| 前回branch: 空報告を実装着手可とする | 赤・2 failed |
| 前回order: 先頭行でなく全行から結論を探す | 赤・1 failed |
| 前回extra-disconnect: 拒否結果の接続を無効化 | 赤・9 failed |
| 前回extra-fail-closed: 検査例外を拒否へ反転 | 赤・1 failed |
| control-splitlines: 共有分割をsplitlinesへ戻す | 赤・28 failed |
| control-disabled: 制御文字の拒否を無効化 | 赤・192 failed |
| claim-splitlines: 申告側だけsplitlinesへ戻す | 赤・4 failed |
| crlf-rejected: CRLFのCR除去を無効化 | 赤・3 failed（正常入力を止める欠陥を検出） |
| 追加1 extra-cli-newline-folding: CLIの読込を既定の改行変換へ戻す | 赤・2 failed |
| 追加2 extra-history-newline-folding: 履歴の読込を既定の改行変換へ戻す | 赤・2 failed |
| 陽性変換: 許可語のtupleを同じ要素のsetへ変更 | 緑・226 passed |

追加1・2は文字の種類や分割条件を変える攻撃と異なり、検査前のI/Oで元の入力を変えてしまう経路へ適用した。**欠陥12件すべて赤、生存0件**。

初回は履歴側の改行変換が緑で残った。試験が別のハッシュ不一致で先に拒否されていたため、履歴fixtureと一致するハッシュへ変更し、変換前の正常報告が履歴で受領されることを先にassertする形へ直した。3結論×2改行の陽性対照も履歴まで通し直し、全変異を再実行して上表の結果を得た。初回の生存を完了の根拠にはしていない。

### 最終の検証

```sh
GIT_CEILING_DIRECTORIES="$PWD/.tmp" TMPDIR="$PWD/.tmp" PYTHONDONTWRITEBYTECODE=1 \
  python3 -m pytest -q -p no:cacheprovider --basetemp=.tmp/verdict-control-related \
  tests/test_round_gate.py tests/test_verdict_line.py tests/test_codex_status_receipt.py \
  tests/test_received_history.py tests/test_routing_record.py \
  tests/test_codex_impl_receipt.py tests/test_codex_review_cli.py

GIT_CEILING_DIRECTORIES="$PWD/.tmp" TMPDIR="$PWD/.tmp" PYTHONDONTWRITEBYTECODE=1 \
  python3 tests/check_verdict_line_mutations.py
```

関連7ファイル **557 passed**。判定行契約は **226 passed**。既存のfail-openの障害注入・不一致SHAの拒否も成功。関連試験ログは `.tmp/verdict-control-related.log`、変異の実行ログは `.tmp/verdict-control-mutations.log`。全体スイートは今回再実行していない。

変更・一時コピーは指定worktree内だけに作成。レビュー発注・push・PR・マージは実行していない。
