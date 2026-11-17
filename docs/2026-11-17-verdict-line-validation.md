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
