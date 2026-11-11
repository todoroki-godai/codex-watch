# CODEX_SUMMARY 起動前検査の検証（2026-11-11）

起点: 349bb9b、枝: feat/summary-issue-number。
共通関数 `check_codex_summary_issue` を、両起動口の共通ファイル読込直後に追加。
`LC_ALL=C grep -Eq '#[0-9]+'` の終了値 1 のみ exit 2 に変換する。
終了値 0 および判定異常（2、127 等）は起動を許可する。
既存の単一行化・60字切り詰め・見込みの読取処理は変更していない。

## 新規試験

すべて codex-impl / codex-review の両方で実行。既存の fake codex / gh を使う。
正常系は実装を足す前に実行し、`2 passed, 78 deselected in 2.48s` を確認。

| 試験名 | 入力・観測 | 件数 |
| --- | --- | --- |
| test_issue_number_normal_launch | `#123 何かの実装`、Codex 呼出1回、state.summary の一致 | 2 |
| test_issue_number_rejects_missing_ascii_number | 未設定、空、`#`、`#abc`、`＃12`、`issue 12`、`#１２`、`#١٢`。exit 2、指定の stderr、Codex 呼出0回、state ディレクトリなし | 16 |
| test_issue_number_positive_controls | `#0 番号なし`、`#12`、文中 `#45`、改行後 `#7`、61字の説明の後に `#7`。起動と保存内容 | 10 |
| test_issue_number_checker_failure_allows_launch | 判定用 grep だけを終了値 2 / 127 にする偽物。未設定 / 有効要約の双方で起動。故障した分岐の実行マーカーも確認 | 8 |

陽性対照と陰性は別集計。空要約・不正UTF-8の保存処理は、起動口の新契約と独立に
`codex_summary_state` の直接試験で従来の空出力を確認する。

## 変異

変異は一時コピーだけに適用し、各コピーを破棄。作業ツリーの実装は壊していない。
分岐の実行マーカー、pytest 終了値 1、AssertionError を必須とする。

入力の探索・変換:
- 記号除去・置換: `#12` → `issue 12`、`＃12`。
- 数字除去・置換: `#12` → `#`、`#abc`、全角数字、アラビア数字。
- 値の欠落: 未設定・空。
- 位置変更: 先頭 → 文中・改行後・60字より後。
- 課題のない仕事: 正整数 → `#0`。
- 判定故障: grep の一致判定 → 異常終了 2 / 127。
- 既存の保存境界: LF / CR / VT / FF / FS / GS / RS / NEL / LS / PS を挿入し、既存キー上書き・新規キー注入を試す。
- 既存の切り詰め境界: 前後空白、61字の日本語・絵文字、59字と絵文字と末尾文字を使う。

新規の変異3件は提示例とは異なるもの:

```text
python3 -m pytest -q tests/test_codex_summary.py -k issue_number
36 passed, 44 deselected in 32.01s

python3 tests/check_summary_issue_mutations.py
M1 require number at start: RED; branch hits=10; 4 failed, 6 passed, 67 deselected in 8.32s
M2 reject numberless escape: RED; branch hits=10; 2 failed, 8 passed, 67 deselected in 9.85s
M3 truncate before checking: RED; branch hits=10; 2 failed, 8 passed, 67 deselected in 14.60s
```

M1 は `^` により文中の番号を拒否、M2 は最初の桁を `[1-9]` に制限して #0 を拒否、
M3 は検査入力を Bash の部分文字列で先に60字へ切り詰める。
3件とも両起動口で赤。生存変異0件。

既存の要約保存の変異も再実行した。空値試験の直接呼出への変更に合わせ、
変異検査器が失敗箇所として `summary_state` も認識するよう調整した。

```text
python3 tests/check_codex_summary_mutations.py
M1 narrow normalization: RED; branch hits=40; 16 failed, 4 passed, 57 deselected in 49.15s
M2 normalize wrong value: RED; branch hits=40; 20 failed, 57 deselected in 49.47s
M3 empty check before normalization: RED; branch hits=4; 2 failed, 2 passed, 73 deselected in 0.76s
M4 truncate before trim: RED; branch hits=20; 2 failed, 8 passed, 67 deselected in 21.49s
M5 drop impl wiring: RED; branch hits=11; 8 failed, 8 passed, 61 deselected in 29.46s
M6 drop review wiring: RED; branch hits=11; 8 failed, 8 passed, 61 deselected in 26.98s
```

## 7段の確認

1. session-board の課題別把握のため本人指定の起動検査が必要。
2. 既存の共通ファイル・起動前検査・要約試験・変異試験の形を再利用。
3. 試験の呼出・観測には標準ライブラリ subprocess / pathlib / time を使用。
4. 判定はプラットフォーム標準の grep の1行で足りる。
5. 新しい依存は不要（試験は既存の pytest）。
6. 判定自体は1行。拒否メッセージと「一致なしだけ拒否」の制御は必要なので残す。
7. 本体に足すのは共有関数1個と各起動口1行のみ。

| 追加した関数・試験 | 止まった段と理由 |
| --- | --- |
| check_codex_summary_issue | 4: 標準 grep、終了値を使う最小限の関数。新しい判定器・依存なし |
| summary_state | 3: subprocess で既存の保存関数を直接呼ぶだけ |
| assert_started | 3: time / pathlib で既存の非同期起動の完了と回数を観測 |
| test_issue_number_normal_launch | 2: 既存の launch fixture と state reader を再利用 |
| test_issue_number_rejects_missing_ascii_number | 2: 同じ fixture に入力の表を足す |
| test_issue_number_positive_controls | 2: 同じ fixture と既存の要約正規化の期待値を利用 |
| test_issue_number_checker_failure_allows_launch | 2: 既存の偽コマンドの手法を grep に使用 |
| check_summary_issue_mutations.main | 2: 既存 check_codex_summary_mutations.py のコピー・実行マーカー・赤必須の形を再利用 |

## #0 を足した既存試験名

共通 helper / fixture を経由する試験も以下に列挙する（パラメーター違いは同じ関数名に集約）。

test_codex_model_effort.py（_run_impl）:

- test_impl_allow_missing_node_modules_passes
- test_impl_empty_effort_uses_config_default
- test_impl_empty_node_modules_exits_4
- test_impl_explicit_effort_is_forwarded
- test_impl_explicit_empty_model_uses_config_default
- test_impl_helper_ignores_inherited_impl_overrides
- test_impl_missing_node_modules_exits_4
- test_impl_model_env_adds_exactly_one_dash_m
- test_impl_no_model_env_uses_default_model_once
- test_impl_populated_node_modules_passes
- test_impl_returns_run_id_without_waiting_when_header_absent
- test_impl_state_has_requested_only_no_effective_fields
- test_status_shows_requested_and_effective

test_codex_review_cli.py（_run, _run_in_git_workdir）:

- test_cli_cr_injection_cannot_corrupt_saved_state
- test_cli_dispatch_content_hash_changes_with_uncommitted_diff
- test_cli_dispatch_content_hash_matches_recipe_extracted_from_generated_prompt
- test_cli_dispatch_writes_content_hash_for_git_managed_workdir
- test_cli_generated_prompt_requires_evidence_for_must
- test_cli_passes_with_valid_goal_cut
- test_cli_rejects_cr_injection
- test_cli_rejects_missing_goal_cut
- test_cli_saved_goal_cut_state_line_is_single_line
- test_cli_unset_model_and_effort_use_config_defaults

test_codex_review_images.py（_run）:

- test_absolute_symlink_to_regular_file_accepted_as_given
- test_blank_lines_only_adds_nothing
- test_comma_in_path_rejected
- test_directory_named_png_rejected
- test_empty_env_same_argv_as_unset
- test_existing_relative_path_rejected
- test_images_combine_with_existing_model_port
- test_leading_dash_rejected
- test_missing_path_rejected
- test_no_env_has_no_image_flag_and_same_argv_as_before
- test_no_extension_rejected
- test_other_allowed_extensions_and_uppercase
- test_path_with_spaces_is_one_dash_i
- test_two_pngs_give_two_dash_i_in_order
- test_txt_extension_rejected

test_codex_impl_aws.py（launch）:

- test_config_rejected_before_launch
- test_existing_set_cannot_reinject_prod
- test_export_is_data_not_shell
- test_failure_has_no_credentials
- test_positive_permissions_environment
- test_rotated_profile_is_not_trusted
- test_safe_set_launches
- test_unreadable_config_rejected

test_codex_github_account.py（launch）:

- test_concurrent_runs_keep_separate_accounts
- test_dangling_declaration_is_error
- test_environment_credentials_cannot_override
- test_failed_preflight_stops_and_redacts
- test_fixed_config_without_shared_version
- test_invalid_or_missing_account_stops
- test_persistence_after_failed_codex
- test_persistence_after_term
- test_pinned_child_and_persistence
- test_real_gh_from_child
- test_repeated_account_replaces_files
- test_review_records_after_codex_exit
- test_undeclared_never_calls_gh
- test_undeclared_preserves_inherited_gh_config
- test_undeclared_preserves_launch

test_progress_overdue.py（launch）:

- test_estimate_record

test_codex_summary.py:

- test_negative_line_injection
- test_negative_trim_and_codepoint_limit
- test_positive_controls

`test_negative_empty_after_normalization` と `test_negative_invalid_utf8_summary` は
空値の保存処理を守るため、#0 の追加に代えて共通関数の直接試験に変更した。

## 全件試験

初回（変異試験と並行）:

```text
python3 -m pytest -q tests
539 passed, 5 skipped in 320.16s (0:05:20)
```

変異試験9件の完了・一時コピー破棄後の最終再実行:

```text
python3 -m pytest -q tests
539 passed, 5 skipped in 327.02s (0:05:27)
```

`tests/test_progress_overdue.py` と `tests/test_codex_summary.py` を含む全件で失敗0件。

Bash 構文検査と `git diff --check` も成功。起点との関数本文比較で、
`sanitize_single_line` / `codex_summary_state` / `ESTIMATE_MIN` は同一と確認。

5件の skip は既存の実 gh/keychain の opt-in 試験4件と、実装起動口では対象外の review 記録試験1件。

## 未確認

実 Codex・実 GitHub・実 AWS への起動、session-board の実画面での採用効果は未確認。
外部ポート・DB は使用していない。共有の稼働版は変更していない。

## レビュー巡1の修正（303d13f から）

以下は上記の初回実装記録を更新する追記。生の CODEX_SUMMARY を検査する仕様と、
M3「truncate before checking」を欠陥扱いした初回記録は、この修正で置き換える。

`_codex_summary_normalized` に既存の単一行化・strip・60コードポイントの
切り詰めを集約し、起動判定と state 保存で共有する。判定は、切り詰め前の
正規化値にある ASCII 番号の一致終端が保存範囲内にあるかを1式で確認する。
そのため `#1234` の一部 `#123` だけを有効な番号として採用しない。
範囲内に別の完全な番号（例 #0）があれば起動する。
README の案内と拒否文は「先頭60字以内」に合わせ、review の実行例にも
`CODEX_SUMMARY='#N …'` を追加した。

不正 UTF-8（`b'\xe4\xbc#5 description'`）は正規化異常として**通す**。
本人決定「判定失敗は通す」に従い、一致なしの終了値1と異常を区別する。
この場合の state は従来どおり summary キーを省略する。
両起動口で Codex 呼出1回・state 生成・summary キーなしを試験で固定した。

### 入力の探索と対照（両起動口）

陰性: 番号欠落・非 ASCII 番号の既存8入力×2口=16件に加え、保存境界7入力×2口=14件。
境界入力は `あ*61+#7`、`あ*59+#12`、`あ*56+#1234`（57字目から番号・全61字）、
`あ*59+#7`（全61字）、`😀*61+#7`、`あ*55+LF+#1234`、
`あ*55+LS+#1234`。すべて exit 2・Codex 呼出0回・state ディレクトリなしを確認する。

陽性対照: 既存の先頭 #0・#12・文中番号・改行後番号に加え、
`あ*58+#7`（60字目で完結）、`空白*65+#0 説明`（strip 後に判定）、
`あ*56+#123`（60字目で完結）、`#0+あ*54+#1234`（別の完全な番号あり）の
8入力×2口=16件。通常起動 `#123 何かの実装` は別に2件。
判定異常 2/127 は未設定・有効要約との組合せ8件、不正 UTF-8 は別に2件。
これらの異常時通過を陰性・陽性対照の件数に混ぜない。

保存境界の既存陰性試験は、先頭に #0 を置き、日本語・絵文字の60字切り詰めと
単一行化を引き続き検査する。改行は LF と LS を境界付近へ挿入し、
先頭空白除去・番号の位置移動・末尾数字の延長・日本語から絵文字への置換も探索した。

### 起動判定の変異

各変異は既存の一時コピー方式で適用・破棄する。実行マーカーと終了値1と
AssertionError を必須にし、構文・収集エラーを赤として扱わない。生存0件。

```text
M1 require number at start: RED; branch hits=16; 8 failed, 8 passed, 83 deselected in 13.67s
M2 reject numberless escape: RED; branch hits=16; 6 failed, 10 passed, 83 deselected in 15.67s
M3 check without truncation: RED; branch hits=14; 14 failed, 85 deselected in 30.94s
M4 shift boundary to 61: RED; branch hits=14; 8 failed, 6 passed, 85 deselected in 19.25s
M5 accept a cut number: RED; branch hits=14; 6 failed, 8 passed, 85 deselected in 15.03s
M6 reject checker failures: RED; branch hits=10; 10 failed, 89 deselected in 5.04s
```

M3 は保存範囲への切り詰めを除去、M4 は60→61へ変更。
別種の M1 は文頭への制限、M2 は #0 拒否、M5 は切断済み番号への誤一致、
M6 は異常時の拒否。既存の保存用変異検査器も、共通化後の処理位置と
実行マーカー位置へ追従させる。保存用 M4 は共有化により保存前の起動拒否で
赤になるため、検査器の失敗箇所判定にも起動成功の assertion を追加した。
初回は試験自体が赤でも検査器がこの失敗箇所を認めず停止したため、修正後に全6件を再実行する。

### 7段

| 足した・変更したもの | 止まった段 |
| --- | --- |
| 正規化の共有関数と state 保存・起動判定の接続 | 2: 既存 sanitize_single_line と state の正規化を共有 |
| 番号終端の境界判定 | 6: 既存 Python 内の any と正規表現の1式。ASCII 数字と終端を検査 |
| 正規化異常の扱い | 2: 既存の異常時通過・summary 省略を再利用し、Unicode 異常を一致なしと区別 |
| 境界・不正 UTF-8・偽判定器の起動試験 | 2: 既存 launch fixture・偽コマンド・state reader を再利用 |
| 変異6件と保存用検査器の追従 | 2: 既存の置換・実行マーカー・赤必須方式を再利用 |
| README・実行例・検証記録 | 2: 既存の記載箇所を更新 |

新しい依存・外部サービスは追加していない。

保存用変異の最終再実行（全6件完了・コピー破棄、生存0件）:

```text
python3 tests/check_codex_summary_mutations.py
M1 narrow normalization: RED; branch hits=80; 16 failed, 4 passed, 79 deselected in 44.05s
M2 normalize wrong value: RED; branch hits=80; 20 failed, 79 deselected in 62.27s
M3 empty check before normalization: RED; branch hits=4; 2 failed, 2 passed, 95 deselected in 0.92s
M4 truncate before trim: RED; branch hits=38; 2 failed, 8 passed, 89 deselected in 24.60s
M5 drop impl wiring: RED; branch hits=14; 11 failed, 11 passed, 77 deselected in 41.84s
M6 drop review wiring: RED; branch hits=14; 11 failed, 11 passed, 77 deselected in 52.49s

python3 -m pytest -q tests/test_codex_summary.py
99 passed in 167.82s (0:02:47)
```

### 修正後の全件試験と未確認

変異はすべて一時コピーに適用・破棄し、本体に変異がない状態で実行した全件試験:

```text
python3 -m pytest -q tests
561 passed, 5 skipped in 430.62s (0:07:10)
```

`tests/test_progress_overdue.py` と `tests/test_codex_summary.py` を含め失敗0件。
5件の skip は既存の opt-in 実 gh/keychain 試験4件と、impl 対象外の review 記録試験1件。
`bash -n bin/_codex_common.sh bin/codex-review` と `git diff --check` も成功。

実 Codex・GitHub・AWS への起動と session-board の実画面・採用効果は未確認。
外部ポート・DB は未使用。共有の稼働版は変更していない。
