# 変異検査の証跡

実行入口: `python3 _work/notes/run_mutations.py`。専用コピー内で逐次実行し、各変異の後に元のバイト列への復元をassert。元の作業実装は書き換えない。

ユーザーのcommit・枝操作禁止と作業場所指定を優先し、commit済み専用worktreeを作る一般手順は使わず、この作業場所内の使い捨てコピーを使用。

①削除、②意味破壊、③入替、④無効化を実施。独自探索: 否定文の意味、複数行への分散。既存試験で巨大入力・ANSI/CRLF/タブ・数値summary・空report・生存/終了も確認。平文区間偽装と混在stderrは保証外として試験名とコードに明記。

初回の06はmacOS awkで不正な正規表現となったため結果を破棄し、構文が成立する `&& 0` へ変更して全変異を再実行した。以下が採用結果。

## 01-delete-recovery-reset

①要素削除: 回復時の状態解除

変更箇所: bin/codex-watch:67

実行した内部コマンド全文:

```sh
python3 -m pytest -q /Users/matsukaze-takashi/matsukaze-utils/codex-watch/_wt.noindex/watch-capacity/_work/mutation-vv5bgbz7/tests/test_codex_capacity.py -k rechecks_capacity
```

結果: exit=1; 1 failed, 76 deselected in 0.15s

差分: `01-delete-recovery-reset.diff`。出力・失敗assertion: `01-delete-recovery-reset.txt`。対象は各1試験ファイル。

## 02-disable-body-boundary

④無効化: role区間を無視

変更箇所: bin/_codex_common.sh:253

実行した内部コマンド全文:

```sh
python3 -m pytest -q /Users/matsukaze-takashi/matsukaze-utils/codex-watch/_wt.noindex/watch-capacity/_work/mutation-vv5bgbz7/tests/test_codex_capacity.py -k role_section_error_quote
```

結果: exit=1; 4 failed, 73 deselected in 0.33s

差分: `02-disable-body-boundary.diff`。出力・失敗assertion: `02-disable-body-boundary.txt`。対象は各1試験ファイル。

## 03-hook-meaning-reversal

②意味破壊: CLI区間を本文と誤認

変更箇所: bin/_codex_common.sh:252

実行した内部コマンド全文:

```sh
python3 -m pytest -q /Users/matsukaze-takashi/matsukaze-utils/codex-watch/_wt.noindex/watch-capacity/_work/mutation-vv5bgbz7/tests/test_codex_capacity.py -k terminal_capacity
```

結果: exit=1; 36 failed, 41 deselected in 2.47s

差分: `03-hook-meaning-reversal.diff`。出力・失敗assertion: `03-hook-meaning-reversal.txt`。対象は各1試験ファイル。

## 04-always-negative-detector

④判定を常に陰性にする

変更箇所: bin/_codex_common.sh:268

実行した内部コマンド全文:

```sh
python3 -m pytest -q /Users/matsukaze-takashi/matsukaze-utils/codex-watch/_wt.noindex/watch-capacity/_work/mutation-vv5bgbz7/tests/test_codex_capacity.py -k capacity_without_tokens
```

結果: exit=1; 2 failed, 75 deselected in 0.12s

差分: `04-always-negative-detector.diff`。出力・失敗assertion: `04-always-negative-detector.txt`。対象は各1試験ファイル。

## 05-remove-negation

独自変異A: 否定文の意味を失う

変更箇所: bin/_codex_common.sh:242

実行した内部コマンド全文:

```sh
python3 -m pytest -q /Users/matsukaze-takashi/matsukaze-utils/codex-watch/_wt.noindex/watch-capacity/_work/mutation-vv5bgbz7/tests/test_codex_capacity.py -k normal_or_noncapacity
```

結果: exit=1; 4 failed, 16 passed, 57 deselected in 1.13s

差分: `05-remove-negation.diff`。出力・失敗assertion: `05-remove-negation.txt`。対象は各1試験ファイル。

## 06-break-wrapped-block

独自変異B: 複数行への分散を読まない

変更箇所: bin/_codex_common.sh:262

実行した内部コマンド全文:

```sh
python3 -m pytest -q /Users/matsukaze-takashi/matsukaze-utils/codex-watch/_wt.noindex/watch-capacity/_work/mutation-vv5bgbz7/tests/test_codex_capacity.py -k terminal_capacity
```

結果: exit=1; 8 failed, 28 passed, 41 deselected in 1.37s

差分: `06-break-wrapped-block.diff`。出力・失敗assertion: `06-break-wrapped-block.txt`。対象は各1試験ファイル。

## 07-swap-summary-state

③入替: tokens usedで候補を消失

変更箇所: bin/_codex_common.sh:255

実行した内部コマンド全文:

```sh
python3 -m pytest -q /Users/matsukaze-takashi/matsukaze-utils/codex-watch/_wt.noindex/watch-capacity/_work/mutation-vv5bgbz7/tests/test_codex_capacity.py -k terminal_capacity
```

結果: exit=1; 32 failed, 4 passed, 41 deselected in 2.05s

差分: `07-swap-summary-state.diff`。出力・失敗assertion: `07-swap-summary-state.txt`。対象は各1試験ファイル。

## positive-control

意味を変えないコメント追加による陽性対照

変更箇所: bin/_codex_common.sh:1

実行した内部コマンド全文:

```sh
python3 -m pytest -q /Users/matsukaze-takashi/matsukaze-utils/codex-watch/_wt.noindex/watch-capacity/_work/mutation-vv5bgbz7/tests/test_codex_capacity.py
```

結果: exit=0; 77 passed in 3.16s

陰性変異は全7件がexit=1。緑のまま残った陰性変異は0件。陽性対照のみexit=0。

実プロセスの終了状態だけで容量とは判定せず、共有関数の結果と組み合わせる。追加コードにパイプはなく、変数は引用。既存kill -0のstderr破棄はそのままで、権限エラー等の理由を隠す既存の限界がある。
