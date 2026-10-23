# PJ GitHub 名義固定 — レビュー巡2の修正・検証記録（2026-10-23）

## 巡2の変更

- `bin/_codex_common.sh`: config.yml は固定バイト列 `version: "1"\n`。共有 config の変数・引数・読取りを削除。atomic replace と入力検証は維持。
- `README.md`: 固定値の説明と、codex-review の PR・課題本文の GET・PATCH も宣言名義を使う旨を追記。
- `tests/test_codex_github_account.py`: 偽 gh と再起動試験で固定値のバイト完全一致を検査。共有 config が無い・version 行が無い場合、および既存 config に有効な version 行と余分な設定がある場合を追加（6件増）。
- この検証記録。新しい依存・運用機構は追加していない（既存処理と Python 標準ライブラリで足りる）。

## 巡2の試験コマンドと件数

全生成物は指定作業場所内。git は実行せず、起動口は偽 git を使う。
実 gh は opt-in の `api user` 読取り4件だけ。record の GET・PATCH は偽 gh とローカル本文を使う。
共有の実設定への書込み・名義変更・トークン出力・commit はしていない。

```sh
python3 -m pytest tests/test_codex_github_account.py -q --basetemp="$PWD/.test-round2-local-final"
# 59 passed, 5 skipped（実 gh 4件と review 専用試験の impl 側1件）
CODEX_TEST_REAL_GH=1 python3 -m pytest tests/test_codex_github_account.py -q --basetemp="$PWD/.test-round2-real"
# 63 passed, 1 skipped（review 専用試験の impl 側）
PATH="$PWD/.test-tools:$PATH" CODEX_REVIEW_KIND_LABEL=コード python3 -m pytest tests/test_codex_model_effort.py tests/test_codex_status_receipt.py tests/test_report_rebuild.py tests/test_round_gate.py tests/test_codex_review_cli.py -q -k 'not git_content_hash and not hash_failure and not receipt_positive_real_recipe and not content_hash_recipe_survives_backslash_loss and not echo_recipe_matches_legacy_printf_bytes and not dispatch_writes_content_hash and not dispatch_content_hash' --basetemp="$PWD/.test-round2-regression"
# 199 passed, 19 deselected
bash -n bin/_codex_common.sh bin/codex-impl bin/codex-review
shellcheck -S warning bin/_codex_common.sh bin/codex-impl bin/codex-review
# ともに exit 0、警告0
PYTHONDONTWRITEBYTECODE=1 python3 .test-round2-check-mutations.py
```

実 gh を含む名義試験 **63 passed, 1 skipped** と回帰 **199 passed, 19 deselected**、合計 **262 passed, 1 skipped, 19除外**。
ローカル版は59 passed, 5 skipped（実 gh 4件を skip）。重複実行は合計件数に足していない。
19件の除外理由は前巡と同じ git 禁止。既存試験を除外なしで全件通過したという意味ではない。
構文・shellcheck は各 exit 0。最後に境界試験だけ再確認し4 passed, 60 deselected:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_codex_github_account.py -q -k test_fixed_config_without_shared_version --basetemp="$PWD/.test-round2-edge-final"
```

[ローカル名義試験](../.test-round2-local-final.log)・[実 gh を含む名義試験](../.test-round2-real.log)・[既存回帰](../.test-round2-regression.log)・[境界再確認](../.test-round2-edge-final.log)。

## 巡2の変異・回避・陽性対照

既存の変異ハーネスを再利用した作業場所内の [.test-round2-check-mutations.py](../.test-round2-check-mutations.py) で実行。
各変異は独立コピーへ適用し、置換元がちょうど1か所であることを assertion で検査。
試験後は復元し、元ソースとの一致と SHA-256 を検査した。

| 変異・回避 | 結果 | 当たった証拠 |
|---|---|---|
| 指定(a) 共有 config のコピーへ戻す | 8 failed, 56 deselected in 8.78s | `test_pinned_child_and_persistence[codex-impl-matsukaze-minden]` |
| 指定(b) 固定値を空にする | 4 failed, 60 deselected in 3.66s | `test_pinned_child_and_persistence[codex-impl-matsukaze-minden]` |
| 追加回避(c) config の作成そのものを省く | 4 failed, 60 deselected in 4.59s | `test_pinned_child_and_persistence[codex-impl-matsukaze-minden]` |
| 追加回避(d) 既存の version 行を信用して更新を省く | 2 failed, 2 passed, 60 deselected in 8.96s | `test_repeated_account_replaces_files[codex-impl-version: "1"\nprompt: disabled\n]` |
| a-per-run-directory | 1 failed, 1 skipped, 62 deselected in 2.28s | `test_review_records_after_codex_exit[codex-review]` |
| b-empty-state | 4 failed, 60 deselected in 5.03s | `test_undeclared_preserves_launch[codex-impl-False]` |
| c-undeclared-gh | 2 failed, 62 deselected in 3.23s | `test_undeclared_never_calls_gh[codex-impl]` |
| d-stale-config | 4 failed, 60 deselected in 7.32s | `test_repeated_account_replaces_files[codex-impl-stale invalid config]` |
| e-nonatomic-overwrite | 4 failed, 60 deselected in 9.39s | `test_repeated_account_replaces_files[codex-impl-stale invalid config]` |
| old-a-child-env | 4 failed, 60 deselected in 3.15s | `test_pinned_child_and_persistence[codex-impl-matsukaze-minden]` |
| old-b-no-match | 6 failed, 22 passed, 36 deselected in 15.18s | `test_invalid_or_missing_account_stops[codex-impl-no-such-user-xyz]` |
| old-c-require-declaration | 2 failed, 2 passed, 60 deselected in 2.57s | `test_undeclared_preserves_launch[codex-impl-False]` |
| old-d-write-shared-hosts | 4 failed, 60 deselected, 4 errors in 2.64s | `test_pinned_child_and_persistence[codex-impl-matsukaze-minden]` |
| old-e-first-line-only | 4 failed, 18 passed, 42 deselected in 8.83s | `test_invalid_or_missing_account_stops[codex-impl-]` |
| old-f-drop-shell-policy | 4 failed, 60 deselected in 3.72s | `test_pinned_child_and_persistence[codex-impl-matsukaze-minden]` |
| positive-equivalent-comparison | 26 passed, 38 deselected in 10.52s | `入力・名義試験26件が緑（別集計）` |

**15変異すべて赤、生存変異0。陽性対照1件は26 passed。**
追加回避(d)は不正な既存設定の場合には緑だが、有効な version 行と余分な設定を持つ場合の2件が赤になることを確認。
指定の2変異、追加回避2件、前巡の11変異、陽性対照は個別に数えた。

[変異結果 JSON](../.test-round2-mutations/results.json) に置換内容・exit code・失敗 node ID・復元 SHA-256、各ケースの `pytest.log` に失敗本文を保存。
[機械照合結果](../.test-round2-artifact-check.json) は全16ケースの置換1か所・変更前後のハッシュ差・復元一致・失敗 node ID とログの一致を検査。
名義試験の出力・state・capture 等403ファイルの資格情報形式検査は0件。
実 Codex のモデル turn、追加サンドボックスの実環境検証、実 GitHub の PATCH は実行していない。

---

以下は巡1の記録（config の最終動作の説明は巡2に合わせて更新）。

# PJ GitHub 名義固定 — レビュー巡1の修正・検証記録（2026-10-23）

作業は依頼された `codex-watch-wt.noindex` 内だけ。git コマンドは実行していない。
起動口が使う git は PATH 上の偽物で置換。実 gh は opt-in 試験の
`api user --jq .login` の読取りだけ。record の GET/PATCH は偽 gh がローカルの本文を更新する。
実 GitHub の PATCH、名義切替、commit、モデル turn は行っていない。

## 変更ファイルと削除した仕組み

- `bin/_codex_common.sh`: 名義別の常設設定、ファイル単位の atomic replace、宣言ありだけの state 行。
- `bin/codex-impl`, `bin/codex-review`: 共通の設定引数を直接 nohup する Codex に渡す。
- `README.md`: 常設化、state 行の有無、照合の限界、worktree への宣言の届け方。
- `tests/test_codex_github_account.py`: 常設・PID・再起動時の更新・宣言なしの gh 不呼出し・record の統合試験。
- `tests/check_github_account_mutations.py`: 指定3件、独自2件、前回から有効な6件、陽性対照。
- この検証記録。

run ごとの `mktemp -d`、親の削除・シグナル trap、監督役とその起動関数、起動時の分岐を撤去した。
state の pid は Codex 本体の PID に戻した。README の SIGKILL 残留注記も削除した。
Codex の終了後に設定置き場を消す要件は、今回の依頼により撤去した。

## 最終動作と限界

対象の git 最上位の `.claude/codex-github-account` を読み取る。
宣言が無い場合は gh を呼ばず、環境・設定引数を追加せず、state に `github_account=` 行を出さない。
行が無ければ宣言なし。行の値が login なら宣言あり・照合済み。
英数字・ハイフン、1〜39文字、先頭末尾が英数字という入力検証は維持した。

常設の置き場は `$STATE_DIR/gh-account/<login>/`（既定 `~/.codex-watch/gh-account/<login>/`）。
相対 STATE_DIR でも GH_CONFIG_DIR には絶対パスを渡す。置き場は mode 0700。
中身は次の hosts.yml（宣言した名義だけ・トークンなし）と固定値 `version: "1"\n` の config.yml だけ。
共有 config.yml は読み取らない。

```yaml
github.com:
    users:
        matsukaze-minden:
    user: matsukaze-minden
```

起動のたびに Python 標準ライブラリの tempfile.mkstemp（mode 0600）で同じディレクトリ内に
一時ファイルを作り、書き終えてから os.replace で個別に置換する。失敗時は一時ファイルを除去する。
同じ名義の起動は同じパス、異なる名義の起動は別パスを使う。Codex 終了後も残るので、
親の `round_gate.py record` の GET/PATCH も同じ設定で実行できる。

共有 hosts.yml への書込み・コピー、資格情報の抽出はしない。
環境 token/debug/host の除去、名義の事前照合、子シェルの set 引数は維持した。
宣言した名義が保管庫に無く、しかも現在の共有名義と同じ場合は、事前の照合では見分けられない（前回確認時の該当は0件。今回は保管庫の列挙をしていない）。
宣言ファイルは git に commit しないと worktree に届かず、宣言なしに戻る。

## 試験コマンドと件数

作業ディレクトリはこの写しの最上位。全 basetemp、偽 HOME、生成物はこの写し内。

```sh
python3 -m pytest tests/test_codex_github_account.py -q --basetemp="$PWD/.test-round1-local-final"
# 53 passed, 5 skipped（実 gh 4件と review 専用試験の impl 側1件）
CODEX_TEST_REAL_GH=1 python3 -m pytest tests/test_codex_github_account.py -q --basetemp="$PWD/.test-round1-final"
# 57 passed, 1 skipped（review 専用試験の impl 側）
PATH="$PWD/.test-tools:$PATH" CODEX_REVIEW_KIND_LABEL=コード python3 -m pytest tests/test_codex_model_effort.py tests/test_codex_status_receipt.py tests/test_report_rebuild.py tests/test_round_gate.py tests/test_codex_review_cli.py -q -k 'not git_content_hash and not hash_failure and not receipt_positive_real_recipe and not content_hash_recipe_survives_backslash_loss and not echo_recipe_matches_legacy_printf_bytes and not dispatch_writes_content_hash and not dispatch_content_hash' --basetemp="$PWD/.test-round1-regression"
# 199 passed, 19 deselected
bash -n bin/_codex_common.sh bin/codex-impl bin/codex-review
shellcheck -S warning bin/_codex_common.sh bin/codex-impl bin/codex-review
# ともに exit 0、警告0
python3 tests/check_github_account_mutations.py
```

既存試験は前回の195件すべてを含め、CLI 4件を加えた199件。
内訳は model/status/report 43件、round gate 146件、review CLI 10件。
実 git を必要とする round gate 16件と review CLI 3件は、今回の git 禁止に従い除外した。
既存試験全件を実 git で通したという意味ではない。
名義試験57件を合わせて **256件通過、1件skip、19件除外**（変異試験・陽性対照は別集計）。

record 試験はソース中で参照されている既存 issue `issue:todoroki-godai/claude-config#55` を対象に、
origin・HEAD・内容ハッシュの経路を偽 git で通す。none/bypass は使わない。
偽 Codex の終了マーカーに加え PID の消滅を待ってから、record の GET → PATCH → GET を行う。
各呼出しの GH_CONFIG_DIR と hosts.yml の名義を検査し、`round_row_written=1`、本文の巡行、
state の HEAD・内容ハッシュ、Codex 本体の PID を確認する。ネットワーク上の issue 本文は変更しない。

宣言なし試験では偽 Codex 自身の gh 呼出しを止め、起動口から gh が呼ばれると
マーカーを残して exit 9 にする。起動成功だけでなく、マーカーが無いことも確認する。
再起動試験では同名義の既存設定を壊して再起動し、両ファイルの更新・同じパスの再利用・
inode の交換・config の固定値との完全一致・一時ファイルの残留なしを確認する。

## 変異試験と陽性対照

変異は各々独立した bin/lib のコピーに1件だけ当てる。
各ケースのコードは試験後に元へ戻し、復元後の SHA-256 を保存する。
偽の共有設定への書込み変異もテスト専用 HOME の中だけで行う。

| 変異 | 結果 | 当たった証拠 |
|---|---|---|
| 指定(a) 常設を run ごとの mktemp ディレクトリへ戻す | 赤・1 failed | `test_review_records_after_codex_exit[codex-review]`。record の GET が常設パスでなくなり、`round_row_written` が無い |
| 指定(b) 宣言なしでも空の state 行を出す | 赤・4 failed | `test_undeclared_preserves_launch`。`github_account` キー不在の assertion |
| 指定(c) 宣言なしで gh を呼ぶ（失敗を握りつぶす） | 赤・2 failed | `test_undeclared_never_calls_gh`。起動は成功しても `unexpected-gh` マーカーを検出 |
| 独自(d) 既存 config.yml の更新を省略する | 赤・2 failed | `test_repeated_account_replaces_files`。壊した config が残り再起動に失敗 |
| 独自(e) rename を直接の上書きへ変える | 赤・2 failed | 同試験。内容が直っても inode が交換されず assertion が失敗 |
| 前回(a) Codex プロセスへの環境の export を外す | 赤・4 failed | `test_pinned_child_and_persistence`。親の設定パスと子シェルの設定パスが不一致 |
| 前回(b) 名義の一致確認を外す | 赤・6 failed | 未登録名義・wrong・bad-output が起動して拒否 assertion に失敗 |
| 前回(c) 宣言なしを拒否する | 赤・2 failed | `test_undeclared_preserves_launch`。最上位あり・宣言なしの正常起動に失敗 |
| 前回(d) 共有 hosts.yml へ書く | 赤・4 failed、4 teardown errors | 専用設定による起動失敗と、fixture の共有 hosts バイト比較で検出 |
| 前回(e) 宣言の先頭行だけ採用する | 赤・4 failed | 空値の1行エラー契約と、複数行の拒否 assertion が失敗 |
| 前回(f) 子シェルの set 引数を外す | 赤・4 failed | `test_pinned_child_and_persistence`。子シェルで共有名義へ戻る |
| 陽性対照: 比較の `!=` を `! ==` 相当へ書換え | 緑・26 passed | 正常起動4件＋入力・未登録名義拒否22件。赤とは別集計 |

**11変異すべて赤、生存変異0。陽性対照1件は緑。**
前回(g)「EXIT の削除を外す」は、今回その削除機構自体を撤去したため、対象が消えたので外した。
前回(a)は監督役内の起動行が無くなったので、同じ目的の export 除去へ移した。

証拠は [results.json](../.test-round1-mutations/results.json) と各ケースの `pytest.log`。
JSON に置換元・置換先、失敗 node ID、復元結果と SHA-256 を保存。
[名義試験ログ](../.test-round1-local-final.log)、[実 gh を含むログ](../.test-round1-final.log) も保存している。
[既存回帰ログ](../.test-round1-regression.log) も保存。
生成ログ・状態・capture 等319ファイルの資格情報形式検査は0件。
全12ケースのソース復元と SHA-256 の一致も確認済み
（[検査結果](../.test-round1-artifact-check.json)）。
record の呼出し証拠は `.test-round1-local-final/test_review_records_after_code1/state/gh-calls.jsonl`。

## 7段のはしご

監督役・終了時削除は段1で不要と判断して撤去した。
状態置き場・起動行は段2の既存機構を使う。atomic replace は段3の Python 標準ライブラリ、
権限・nohup は段4の標準機能、認証・子の環境設定・試験は段5の既存依存で足りる。
入力検証、誤名義拒否、資格情報の上書き除去、共有設定保護は維持した。新しい依存は追加していない。

実 Codex の環境生成に関する前回の app-server 実測は
[前回の記録](../.test-account-environment/results.json) に残る。今回はその実測を再実行していない。
今回の57件には実 gh の読取り4件を含むが、実 Codex のモデル turn や追加サンドボックスの起動検証は含まない。
