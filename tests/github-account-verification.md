# PJ GitHub 名義固定 — 実装・検証記録（2026-10-23）

作業先は依頼された `codex-watch-wt.noindex` の写しだけ。本物の codex-watch は変更していない。
git コマンドを実行せず、git を使う起動口の試験では PATH 上の stub に置き換えた。
gh は `api user --jq .login` の読み取りだけ。モデルの turn、commit、投稿、名義切替は行っていない。

## 変更ファイル

- `bin/_codex_common.sh`: 宣言の読取・検証、run ごとの gh 設定、名義照合、子シェルへの設定、監督・削除、state の1項目。
- `bin/codex-impl`, `bin/codex-review`: 共通関数の呼出しと宣言ありの場合の起動分岐。review は巡数ゲートより前に名義を検証する。
- `tests/test_codex_github_account.py`: 両起動口を通すテスト。実 git/モデルの起動なし。実 gh の4件は明示 opt-in。
- `tests/check_github_account_mutations.py`: 個別の隔離コピーに変異を当て、赤を確認してコピーも戻す。
- `tests/probe_codex_github_environment.py`: モデル turn を作らず、実 CLI の環境生成を測る。
- `README.md`: 宣言方法・state・監督 PID・削除条件。
- この検証記録。

## 最終動作と置き場の寿命

`-C` に渡す作業場所から `git rev-parse --show-toplevel` で得る最上位の
`.claude/codex-github-account` を使う。宣言がない／最上位を得られない場合、
従来の nohup 起動行をそのまま使い、環境や CLI 引数を追加しない。
もともとの impl の linked worktree／node_modules ガードも維持する。
git 外で impl を許可するには、従来どおり既存の明示例外が必要。

宣言は前後空白を除去し、英数字・ハイフンの GitHub login（1〜39文字、先頭・末尾は英数字）として検証。
空値、内部空白、複数行、NUL、不正 UTF-8、長すぎる値、壊れた symlink は拒否する。
不正な入力値そのものはエラーへ再出力しない。

状態ディレクトリ（既定 `~/.codex-watch`、試験では写し内に指定）の
`gh-account.XXXXXX` を mktemp で mode 0700 にする。そこへ以下の token を含まない hosts.yml を書く。

```yaml
github.com:
    users:
        matsukaze-minden:
    user: matsukaze-minden
```

共有 hosts.yml はキー名・字下げだけを確認した。値は表示していない。
実 gh 2.89.0 では config.yml がないと旧形式の移行に入って検証に失敗したため、
共有 config.yml を読み取りコピーする方式を採用した。共有 hosts.yml をコピーしない。
GH_CONFIG_DIR は専用パスへ変更し、環境の token 上書き・debug・host 上書きは値を読まず unset。
同じ環境の `gh api --hostname github.com user --jq .login` が宣言と一致した場合だけ起動する。
gh の stderr は捨て、stdout は login として妥当な値かを通してからエラーに載せる。
保管庫にない名義で別名義へフォールバックした場合も不一致として拒否する。

Codex の子シェルには `-c shell_environment_policy.set.GH_CONFIG_DIR=...` を渡す。
config.toml の set 経由で認証上書きが復活しないよう、token 環境変数・debug・host は空値で上書きする。
資格情報の値を取得する処理はない。

宣言ありの場合だけ nohup した監督シェルが Codex を起動し、wait する。
状態の pid は監督シェル。起動口が run ID を返しても置き場は存続し、
Codex の通常終了／エラー終了後に EXIT trap で削除する。
TERM/INT を受けた場合は子へ転送して wait してから削除する。
起動前の拒否・失敗は起動口の EXIT trap で削除する。
SIGKILL／電源断では trap が走らず、token を含まない専用置き場が残る可能性がある。

state の追加は `github_account=` の1項目だけ。
空値＝宣言なし、login の値＝宣言あり・検証済み。
要求された state 追加以外の宣言なしの起動引数・環境・既存ガードは維持している。

## コマンド・件数

以下の作業ディレクトリはすべてこの写しの最上位。`$PWD` もこの写し。

```sh
CODEX_TEST_REAL_GH=1 python3 -m pytest tests/test_codex_github_account.py -q --basetemp="$PWD/.test-account-final"
```

**52 passed**。両名義の子からの実 gh 読取4件、宣言なし、git 外（既存ガードの例外を明示）、
remote を必要としない最上位からの読取、不正値、未登録名義、gh 失敗・異常出力、
環境認証の上書き、state、共有設定不変、通常／異常終了・TERM 後の削除、同時2名義の隔離を含む。
実 gh を opt-in しない通常の実行では **48 passed / 4 skipped** 相当。

既存テストでは git 実行を防ぐため、写し内 `.test-tools/git` を PATH の先頭に置いた。
この stub は常に exit 128。git を必要とする既存の内容ハッシュ試験は選択しなかった。

```sh
PATH="$PWD/.test-tools:$PATH" python3 -m pytest tests/test_codex_model_effort.py tests/test_codex_status_receipt.py tests/test_report_rebuild.py -q --basetemp="$PWD/.test-regression"
# 43 passed
PATH="$PWD/.test-tools:$PATH" python3 -m pytest tests/test_round_gate.py -q -k 'not git_content_hash and not hash_failure and not receipt_positive_real_recipe and not content_hash_recipe_survives_backslash_loss and not echo_recipe_matches_legacy_printf_bytes' --basetemp="$PWD/.test-round-regression"
# 146 passed, 16 deselected
PATH="$PWD/.test-tools:$PATH" CODEX_REVIEW_KIND_LABEL=コード python3 -m pytest tests/test_codex_review_cli.py -q -k 'receipt_cli or cr_injection' --basetemp="$PWD/.test-cli-regression"
# 6 passed, 7 deselected
bash -n bin/_codex_common.sh bin/codex-impl bin/codex-review
shellcheck -S warning bin/_codex_common.sh bin/codex-impl bin/codex-review
```

既存 **195件**、追加 **52件**の計 **247件**が通過。構文検査と shellcheck の警告も0。
既存テスト全体を実行したという意味ではない。

## 変異と陽性対照

```sh
python3 tests/check_github_account_mutations.py
```

指定4件＋独自3件がすべて赤。生存変異0。各変異は独立した bin/lib のコピーに1件ずつ適用。
共有書込変異で使う HOME はテスト専用の偽物なので、本物の共有設定は書き換わらない。
各コピーは試験後に元に戻し、復元後の SHA-256 も保存した。

| 変異 | 結果 | 当たった試験・証拠 |
|---|---|---|
| (a) Codex プロセスへ GH_CONFIG_DIR を渡さない | 赤・4 failed | `test_pinned_child_and_cleanup`、子プロセスの環境と専用パスの一致が崩れる |
| (b) 名義の一致確認を外す | 赤・6 failed | `test_invalid_or_missing_account_stops` の未登録名義、`test_failed_preflight_stops_and_redacts` の wrong/bad-output が起動してしまう |
| (c) 宣言なしで拒否する | 赤・2 failed | `test_undeclared_preserves_launch` の git 最上位あり・宣言なし |
| (d) 共有 hosts.yml へ書く | 赤・4 failed＋4 teardown errors | 起動検証失敗に加え、fixture の共有 hosts バイト比較が変更を検出 |
| 独自(e) 宣言の先頭行だけを採用する | 赤・4 failed | 複数行を受理する／空値で1行エラー契約が崩れる |
| 独自(f) 子シェル用 set 引数を外す | 赤・4 failed | 同じ `test_pinned_child_and_cleanup`、core 相当の環境生成後に宣言名義にならない |
| 独自(g) EXIT の削除を外す | 赤・4 failed＋4 teardown errors | 子終了後も専用パスが残り、寿命の assertion と fixture の残留検査が失敗 |
| 陽性対照: `!=` を `! ==` 相当の比較に書換え | **緑・26 passed** | 正常起動4件＋入力／未登録名義拒否22件。陽性対照は変異の赤とは別集計 |

(b) には、意図せず起動した監督役を fixture が停止する際の残留検出も1件付随した。
検出の主根拠は上表の6つの拒否 assertion。

生データ: [results.json](../.test-account-mutations/results.json)。
各行の `evidence` は失敗 node ID、`replacements` は実際に置換したコード、
`restored` と `restored_sha256` は復元結果。
各ケースの `pytest.log` に assertion と行番号を保存している。

## 実 Codex の環境引き継ぎ実測

```sh
python3 tests/probe_codex_github_environment.py
```

実 CLI の app-server `command/exec` を使い、thread／turn／モデル呼出しを作らずに実測した。
CODEX_HOME とサーバーのログはこの写し内の一時ディレクトリに限定した。

| core の環境生成 | 子の GH_CONFIG_DIR | 子の実 gh が返した login |
|---|---|---|
| 親だけに指定、set 引数なし | **消える** | todoroki-godai（共有設定） |
| set 引数あり、matsukaze-minden を宣言 | 専用パスのまま | **matsukaze-minden** |
| set 引数あり、todoroki-godai を宣言 | 専用パスのまま | **todoroki-godai** |

`codex sandbox` 自体は、この実行環境で macOS seatbelt の二重適用が
`sandbox_apply: Operation not permitted`（exit 71）になった。
そのため測定は既存の外側サンドボックスの中で、`externalSandbox` を指定した実 CLI の
環境生成・子コマンド経路で行った。外側の制限は維持されている。
新しい read-only / workspace-write の seatbelt を二重起動して成功したという証拠ではない。
その2モードの起動口の引数・環境配線は、両起動口の統合試験で確認している。

生データ: [environment/results.json](../.test-account-environment/results.json)。

## 共有設定・資格情報

実共有 hosts.yml の試験前後 SHA-256 は同一:

```
7e55d9d9bee87d4712810708d588726792198e9f89cb7e63fd3de33dcc79c977
```

起動結果の stdout/stderr は各テストで検査。
生成したログ・状態・報告・子の capture・変異の pytest.log も token 形式の検出を実施し **0件**。
走査件数は [secret-scan.json](../.test-account-secret-scan.json) に保存。
`gh auth token` / switch / login / refresh は呼ばず、共有設定への書込もない。

## 7段のはしご

| 足した仕組み | 止めた段 | 理由 |
|---|---|---|
| 両起動口への共通配線 | 2 既にある | 既存 `_codex_common.sh` と STATE_DIR を再利用 |
| 宣言の strip・login 検証・パスの JSON 引用 | 3 標準ライブラリ | 導入済み Python の pathlib/re/json。新依存なし |
| 専用設定・排他的作成・権限・コピー・削除 | 4 プラットフォーム標準 | mktemp/cp/bash trap。独自の一時ディレクトリ管理なし |
| 名義確認・保管庫読取・子シェル環境の設定 | 5 導入済み依存 | gh と Codex の標準機能を使う。資格情報抽出なし |
| 認証上書き除去・state の1項目 | 6 一行 | unset と printf を使用。独自の資格情報状態を持たない |
| 非同期終了待ちとシグナル転送 | 7 動く最小コード | 起動口は即時に戻るため監督役が必要。wait/trap のみ |
| 正常／異常／変異試験 | 5 導入済み依存 | 既存 pytest と PATH 差替えの流儀。変異ツールの新依存なし |

段1は明示依頼と、実測した gh の別名義へのフォールバックで必要性を確認した。
信頼境界の入力検証・誤名義での起動拒否・共有設定保護は削っていない。
