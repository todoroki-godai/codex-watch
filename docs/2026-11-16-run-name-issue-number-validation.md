# #53 実装・検査の証跡（2026-11-16）

設計 `docs/2026-11-16-run-name-issue-number.md` のまま実装。設計変更なし。
実装と検査は完了、コミットだけ名義の自動検査で拒否され未完了。

## 見た版の固定

- 受領・現在の HEAD: `0a778f26e91cea38ed6d7ec44affbad2ac534847`。新しいコミットは作成できていない。
- 検査対象のコードはこの HEAD に `.tmp/run-name-code.patch` を適用したもの。
- コードパッチ SHA-256: `1ed74cec2caa73b0ff8bd2336c6a76781e8643a060ac7fa851494e2a4dd14c21`。この報告書を除く8ファイル。
- `git apply --reverse --check .tmp/run-name-code.patch` で現在の内容と一致することを検査済み。
- 下記の実行ログ先頭にも、実際に読んだ5ファイルの完全な SHA-256 を記録。
- 変更・新規ファイルはステージ済み。ログとパッチを含む `.tmp/` はコミット対象外。

## 変更したファイルと行数（報告書を除く）

追加行、削除行、ファイルの順:

```text
17	2	bin/_codex_common.sh
1	1	bin/codex-impl
1	1	bin/codex-review
186	0	tests/check_run_name_mutations.py
3	3	tests/test_prerelease.py
1	1	tests/test_prerelease_implA3.py
3	3	tests/test_round_count_c.py
168	0	tests/test_run_name_issue.py
```

既存試験3ファイルの `fixture-*.state` は、`#0` の新しい仕様どおり
`0-fixture-*.state` へ更新。拒否時の不存在検査も同じ名前を参照する。
`tests/test_codex_summary.py` の `RUN_ID=fixed` の比較試験はそのまま維持した。
新規試験は起動口をバイト単位でコピーし、IDを上書きせず返却値・state内ID・
`.state` / `.log` / `.report` の実ファイル名を両起動口で照合する。
既存runは偽CLIの実プロセスを維持し、次の起動前後でPID生存と記録3種のinode・内容を照合する。

## 再現コマンド全文

作業場所の中に一時ファイルを置く。`GIT_CEILING_DIRECTORIES` は、入れ子の一時作業先が
親checkoutの名義宣言を継承しないために指定する。新規試験は自身の隔離gitを用意する。
CLIは既存の偽CLIを使用し、実LLMや実runには接続しない。

```sh
mkdir -p .tmp
TMPDIR="$PWD/.tmp" GIT_CEILING_DIRECTORIES="$PWD" python3 -m pytest tests/ -q --basetemp=.tmp/pytest-final --junitxml=.tmp/pytest-final.xml > .tmp/pytest-final.log 2>&1
TMPDIR="$PWD/.tmp" GIT_CEILING_DIRECTORIES="$PWD" python3 tests/check_run_name_mutations.py > .tmp/run-name-mutations-final.log 2>&1
bash -n bin/_codex_common.sh bin/codex-impl bin/codex-review
git diff --check
git diff --cached --check
git apply --reverse --check .tmp/run-name-code.patch
```

## tests/ 全体の実施範囲

| ファイル | 通過 | 失敗 | skip |
|---|---:|---:|---:|
| `tests/test_codex_github_account.py` | 59 | 0 | 5 |
| `tests/test_codex_impl_aws.py` | 62 | 0 | 0 |
| `tests/test_codex_impl_receipt.py` | 42 | 0 | 0 |
| `tests/test_codex_model_effort.py` | 21 | 0 | 0 |
| `tests/test_codex_review_cli.py` | 14 | 0 | 0 |
| `tests/test_codex_review_images.py` | 15 | 0 | 0 |
| `tests/test_codex_status_receipt.py` | 10 | 0 | 0 |
| `tests/test_codex_summary.py` | 99 | 0 | 0 |
| `tests/test_history_backfill.py` | 36 | 0 | 0 |
| `tests/test_prerelease.py` | 75 | 0 | 0 |
| `tests/test_prerelease_fixA.py` | 19 | 0 | 0 |
| `tests/test_prerelease_fixA2.py` | 13 | 0 | 0 |
| `tests/test_prerelease_implA3.py` | 9 | 0 | 0 |
| `tests/test_preview_checks.py` | 30 | 0 | 0 |
| `tests/test_progress_overdue.py` | 20 | 34 | 0 |
| `tests/test_received_history.py` | 44 | 0 | 0 |
| `tests/test_report_rebuild.py` | 12 | 0 | 0 |
| `tests/test_review_must_criteria.py` | 21 | 0 | 0 |
| `tests/test_round_count_c.py` | 42 | 0 | 0 |
| `tests/test_round_gate.py` | 173 | 0 | 0 |
| `tests/test_roundcount_perkind.py` | 32 | 0 | 0 |
| `tests/test_routing_record.py` | 48 | 0 | 0 |
| `tests/test_routing_warn.py` | 52 | 0 | 0 |
| `tests/test_run_name_issue.py` | 38 | 0 | 0 |

全24ファイル・1025件。通過986件、失敗34件、skip5件。全体ログ: `.tmp/pytest-final.log`、機械集計: `.tmp/pytest-final.xml`。
新規 `tests/test_run_name_issue.py` は24件の関数試験、両起動口各6件の実ID試験、
両起動口各1件の走行中run維持試験の計38件。

## 変異（指定9種類 + 自作3種類、両起動口を分けた計13変異）

(a) 独立した差分検査: 対象が1箇所だけ一致すること、変換後のディスク内容の再読込一致、
差分とSHA-256を確認。(b) 独立した実行証跡: Pythonの行イベント / shellの実行トレース /
偽CLIが実際に読み取った出力先を確認。`codex-impl` の `set +x` は変更していない。
失敗はJUnitを読み、検査のassertionによるものだけを数える。検査基盤の例外は数えない。

全13変異が赤、意味を変えない変換Pは38件が緑。M6でも既存の異常時起動継続10件は緑。
M9は新しい起動で既存reportを壊す変異。X1はlabelの非ASCII文字削除、
X2は番号を整数化して先頭ゼロを失わせる変換、X3は番号の出所をREVIEW_TARGETへ変える変換。

圧縮した実測（変異を当てた後のファイル全体のハッシュ、到達証跡、assertion件数）:

```text
M1 omit prefix: RED; file sha256=9d0fb08af00e; shell "printf '%s\\n' tally" hits=1; ================= 20 failed, 4 passed, 14 deselected in 2.13s ==================
M2 double prefix: RED; file sha256=19f82fcf346e; shell '== __never_equal__' hits=24; ================= 4 failed, 20 passed, 14 deselected in 1.93s ==================
M3 substring match: RED; file sha256=0f3c43a90027; shell '== *\\1\\9\\8\\7*' hits=13; ================= 3 failed, 21 passed, 14 deselected in 1.91s ==================
M4 ignore 60 boundary: RED; file sha256=5fa028471598; Python issue_value line=7 hits=23; ================= 2 failed, 22 passed, 14 deselected in 1.93s ==================
M5a disconnect impl: RED; file sha256=bbdb646541b5; offline child read numberless report path hits=1; ================= 5 failed, 7 passed, 26 deselected in 12.10s ==================
M5b disconnect review: RED; file sha256=f31714b36fb2; offline child read numberless report path hits=1; ================= 5 failed, 7 passed, 26 deselected in 12.24s ==================
M6 remove abnormal fallback: RED; file sha256=fac5a00e12be; shell 'issue=' hits=12; ================= 7 failed, 39 passed, 91 deselected in 30.03s =================
M7 search truncated text: RED; file sha256=a592212828b4; Python issue_value line=7 hits=23; ================= 1 failed, 23 passed, 14 deselected in 1.95s ==================
M8 select second number: RED; file sha256=b424247d9f80; Python issue_value line=8 hits=47; ================= 2 failed, 22 passed, 14 deselected in 1.89s ==================
M9 corrupt existing live report: RED; file sha256=ebf39a95f8b6; shell "printf 'corrupted\\n'" hits=1; ================== 1 failed, 1 passed, 36 deselected in 3.96s ==================
X1 strip non ASCII label: RED; file sha256=2d8e79d28f53; shell "tr -cd '\\000-\\177'" hits=24; ================= 2 failed, 22 passed, 14 deselected in 2.10s ==================
X2 normalize leading zeros: RED; file sha256=38afebbd4217; Python issue_value line=10 hits=23; ================= 1 failed, 23 passed, 14 deselected in 1.96s ==================
X3 use review target as authority: RED; file sha256=526b29f82b98; shell 'issue=53' hits=24; ====================== 24 failed, 14 deselected in 2.04s =======================
P equivalent rewrite: GREEN; file sha256=d048a59c1af9; Python issue_value line=10 hits=37; ============================= 38 passed in 17.43s ==============================
```

完全な差分・トレース・pytest出力・JUnitは `.tmp/<M1〜M9・M5a/M5b・X1〜X3・P>-{diff,trace,pytest,junit}.log`。
集約は `.tmp/run-name-mutations-final.log`。ログはコミットしない。

## 探索した入力と変換

- summary: 未設定、番号なし、`#0`、`#1987`、`#0012`、複数番号、Unicode前後空白、改行、
  日本語による60文字ちょうど / 超過 / 数字列の途中切断、先頭の正常番号と後方の切断番号、不正UTF-8。
- label: 番号なし、番号が先頭 / 中間に存在、`11987` / `19870` / `10` の誤一致境界、
  別番号、日本語、`.` / `_`、空文字、前後空白、`*[]$;` を含む文字列。
- 変換: 付与削除、無条件重複付与、部分一致、60文字制限撤去、両起動口の配線削除、
  異常時0撤去、切詰め後抽出、2件目採用、既存記録破壊、非ASCII削除、整数化、出所混同、
  意味を変えないスライス `[::1]` の追加。
- 陽性対照: 既存番号・日本語label・`#0`・意味を変えないPは緑。
- `/` のlabel検査と全角数字混在の境界は設計どおり範囲外。

## 7段

- 番号取得・異常時の値: ㋑。既存 `_codex_summary_normalized` に返り方を追加。
- labelへの付与・両起動口: ㋑。既存Bashの正規表現とRUN_ID生成を利用。独立した抽出器なし。
- 試験: ㋑。既存pytestと偽CLIを再利用。
- 変異証跡: ㋑。既存の隔離コピー型変異検査に合わせる。diff・trace・XML解析は標準ライブラリ。
新しい依存なし。走行中run・過去のrunは変更しない。

## 範囲外の赤

`tests/test_progress_overdue.py::test_estimate_record`（34件）。
受領時SHAの3つのbinを戻した隔離コピーでも34件すべて同じ
`CODEX_IMPL_AWS_STATE: unbound variable`。ログは `.tmp/progress-baseline-all.log`。

受領版での再現コマンド全文（本作業で実施済み）:

```sh
python3 - <<'PYBASE'
from pathlib import Path
import shutil, subprocess
root = Path('.tmp/progress-baseline')
for directory in ('bin', 'lib', 'tests', 'templates'):
    shutil.copytree(directory, root / directory, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__'))
for name in ('_codex_common.sh', 'codex-impl', 'codex-review'):
    (root / 'bin' / name).write_bytes(subprocess.check_output(
        ['git', 'show', '0a778f26e91cea38ed6d7ec44affbad2ac534847:bin/' + name]))
PYBASE
TMPDIR="$PWD/.tmp" GIT_CEILING_DIRECTORIES="$PWD" python3 -m pytest .tmp/progress-baseline/tests/test_progress_overdue.py -q -k test_estimate_record --basetemp=.tmp/pytest-progress-baseline-all --junitxml=.tmp/progress-baseline.xml > .tmp/progress-baseline-all.log 2>&1
```

## コミットの阻害

PreToolUseの名義検査が、期待 `todoroki-godai` と現在 `matsukaze-minden` の不一致で
`git commit` を拒否した。作業場所内の名義別設定で実アカウントを検証できたが、
同検査は既定のGH_CONFIG_DIRのみを要求し、それを指定しても現在名義が不一致として拒否。
共有認証設定は変更せず、検査の回避も行っていない。コミットと新規SHAは未作成。
