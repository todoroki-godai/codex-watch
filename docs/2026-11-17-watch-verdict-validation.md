# codex-watch#58: 終了通知でレビュー判定行を検査する

起点: `134368dd3ff5a782aa307beeb50ae0f98f691fe5`、枝: `fix/58-verdict-reason`。

依頼どおり、`bin/codex-watch` が報告再構築後に既存の
`round_gate.check_verdict_line` を呼び、既存の `EXIT` 通知に拒否理由を添える。
`lib/watch_verdict.py` は state の `mode=workspace-write` を持つ実装報告を除外する。
検査・import・読込みの例外は通し、Pythonプロセスの異常終了もシェル側で通す。
報告の削除や検査による書換えはしない。既存の再構築処理と codex-status の経路は維持する。

## 実経路の入力試験

全例で `.state` / `.log` / `.report` を実際に置き、`bash bin/codex-watch probe` を起動する。
直接関数を呼ぶだけの試験ではない。通知のLF区切りの通数、EXITが1通であること、
拒否理由と直し方、報告を直接読めることを確認する。
赤=入力を受領不可と表示、緑=入力を通す。試験としてはすべて成功。

| 入力クラス・実際の変換 | 入力判定 |
| --- | --- |
| 別語への置換: `マージ可` | 赤 |
| 理由と区切りを削除: `判定保留` | 赤 |
| 理由を削除: `判定保留:` | 赤 |
| 区切りの変形: `判定保留 :` / `判定保留：` | 赤 / 赤 |
| 許可語: `実装着手可` | 緑 |
| 許可語: `設計修正要` | 緑 |
| 同じ行の理由: `判定保留: 対象の版が読めない` | 緑 |
| 実装報告: `実装しました`、`mode=workspace-write` | 緑 |
| 旧語に補足を付加: `マージ可（前の回の [Must] は解消。新規 [Should] 1件）` | 赤 |
| 空白への置換: 保留理由をTAB・全角空白・NBSPだけにする | 赤 |
| 行位置の変更: 保留理由を次のLF行へ移す | 赤 |
| 表示の装飾: `**実装着手可**` | 赤 |
| バイト接頭辞: `実装着手可` の前にBOMを挿入 | 赤 |
| 行位置の変更: 判定行の前に説明行を挿入 | 赤 |
| 制御文字挿入: 理由の途中に単独CR / VT / ESC / U+2028を挿入 | すべて赤 |
| 改行の正常変換: 陽性4件をLF / CRLFで保存 | すべて緑 |
| 再構築: 最終節だけのreportを、`マージ可`で始まるlogから再構築 | 赤 |
| 例外注入: 検査内部 / 検査呼出し / importでRuntimeError | すべて緑、報告のバイト不変 |

陰性11入力はtokens usedの有無の両方（22件）、陽性4件はLF/CRLFの両方（8件）、
制御文字4件、再構築1件、例外3件で計38件。

## 故障を実際に入れた確認

`tests/check_watch_verdict_mutations.py` が worktree 内の `.tmp` に複製を作り、
以下の変異を実際に適用して同じ本番経路の試験を起動する。
ここで赤はpytestのassertion失敗を指す。構文・収集エラーは検出成功として数えない。

| コード変異 | 結果 | 赤の件数 |
| --- | --- | ---: |
| 終了通知から検査結果の補間を削除（配線切断） | 赤 | 22 |
| 実装除外条件を反転（レビューを素通り） | 赤 | 24 |
| 実装除外を無効化（実装報告も拒否） | 赤 | 2 |
| 通知から既存のreasonを削除（直し方を欠落） | 赤 | 22 |
| 読込みを通常のopenへ変更（単独CRの正規化） | 赤 | 1 |
| helperの例外を拒否へ変更 | 赤 | 2 |
| 既存validatorの例外を拒否へ変更 | 赤 | 1 |

7種類すべて赤。緑のままの故障変異は0件。元のソースが変わっていないこともrunnerで確認する。
機械記録: [watch-verdict-mutations.json](../evidence/watch-verdict-mutations.json)。

## 再実行

一時ファイルもこのworktree内に置く。`GIT_CEILING_DIRECTORIES` は一時領域から
親リポジトリの `.claude/codex-github-account` を誤って拾わないための試験環境設定。
最初の全体試験はこれを設定せず、既存試験でGitHub名義不一致が発生したため中断した。
単独の既存model/effort試験21件が、この環境設定後に成功することを確認して全体を再実行した。

```sh
GIT_CEILING_DIRECTORIES="$PWD/.tmp" PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider --basetemp=.tmp/pytest/isolated tests
PYTHONDONTWRITEBYTECODE=1 python3 tests/check_watch_verdict_mutations.py
bash -n bin/codex-watch
git diff --check
```

変更したパッケージ全体の試験: **codex-watch / 1292件 / 赤34件**
（1253件成功、5件スキップ、537.88秒）。追加した本番経路の試験は38件成功、赤0件。

赤34件はすべて既存の `tests/test_progress_overdue.py::test_estimate_record`。
この試験の `codex_impl_aws.py` スタブは引数なしのときだけ状態変数を出力するが、
現行の起動処理は名義引数を渡すため、`CODEX_IMPL_AWS_STATE: unbound variable` で失敗する。
起点 `134368dd3` の bin/lib/templates を別の複製へ取り出し、既存の試験の
`CODEX_OVERDUE_TEST_ROOT` でその版を指定した結果も **34件失敗・20件成功**。
全体試験の失敗ID34件と起点版の失敗ID34件が完全一致することをスクリプトで照合した。
この既存スタブには今回変更を加えていない。

全体結果と失敗IDの機械記録: [watch-verdict-tests.json](../evidence/watch-verdict-tests.json)。
`bash -n bin/codex-watch` と `git diff --check` も成功。
