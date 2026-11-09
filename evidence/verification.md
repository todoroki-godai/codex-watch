# 起動口の受領検査: 実装と検査

## 対応

依頼文の存在確認の直後、共通設定の読み込みより前に検査を置いた。呼び出し元のBashは解析しない。空でない出所の1行を必須とし、値が「レビュー」で始まる場合は受領①②③をそれぞれ空でない値つきで必須とする。重複する申告は拒否する。読取失敗・非UTF-8・NULも拒否し、いずれもexit 2。案内は固定文で、依頼文の値は表示しない。

(2)は実装前計測の23.08%が5%を超えたため不採用。語の組の変更は試算だけで、採用していない。新しい環境変数・hook・Agent検査はない。READMEに4行の例を追加した。

7段: 起動位置の選択は㋑（既存の依頼文存在確認を再利用）。欄の抽出・空値・重複・読み取りエラーの検査は㋒（既に起動口で必要なPython標準ライブラリのpathlibと文字列操作だけ）。計測は㋒（pathlib/json/re/hashlib）、試験は㋑（既存pytestとfake CLIの形を再利用）。新依存なし。新たな別系統レビューは本人の「レビューもしない」に従い実行していない。

## 新規検査（実際のCodexは起動しない）

`python3 -m pytest -q tests/test_codex_impl_receipt.py`

```text
25 passed in 0.99s
```

実ファイルbin/codex-implを試験用コピーにし、検査直後の既存の次工程をsentinel（exit 71）で止める。後続のgit/aws/gh/codex/nohupもfakeで遮断。既存の全体試験は別途、fake CLIを使い起動口の最後まで通す。

- 陰性8件: 出所なし／出所に字下げ／全角コロン／出所空値／レビューで受領なし／受領②欠落／受領①空値／受領③空値。すべてexit 2、次工程に到達しない。案内の3手順・4行例・自己申告の制限も照合。
- 陽性6件: なしだけ／4行のレビュー／同じレビューをCRLFへ変換／B群実物id5,7,9。すべて次工程まで到達、資格情報の準備やCLI起動前に止める。B群実物は原文をfixture化し、試験が出所の行だけを付ける。
- 独立に探索した入力7件: 出所の重複を前後双方の順で追加、受領②の空の重複を末尾に追加、受領②をU+3000とU+00A0だけに変換、出所をU+3000だけに変換、NUL追加、非UTF-8バイト。すべてexit 2。異なる入力クラスは「複数申告の矛盾」「Unicode空白」「テキストとして不正な入力」。この範囲の回避残存0件。
- 今日の事故形1件: `直しの出所: なし（新規実装）` の依頼の末尾に `## C. レビュー巡3の指摘を直す` を追記。次工程に到達することを確認。陰性の成功や回避を閉じた件数には含めない。(2)を外すという事前基準に従った既知の未防止1件であり、この事故を防いだとは報告しない。
- 変異3件: 出所不備の拒否を除去／受領欠落の拒否を除去／Unicode空白の受領を拒否する処理を除去。元の入力がexit 2だったことを先に確認し、変更対象が1箇所だけであることを照合。変えた分岐で固有のMUTANT印をstderrへ出し、印とNEXT_STAGE・exit 71を実測するassertionで着弾を確認した。元の「exit 2でなければ失敗」の期待を3件とも破り、3件検出・残存0件。構文エラーや未実行を検出と数えていない。

閉じられない形: 出所を「なし」や任意の非レビューの値と偽る、本文の後からの追記、受領欄に事実でない値を記す、レビューの言い換え、申告をコードブロックに置く等。既知の行の存在と非空だけを見る自己申告の検査で、受領を実際に済ませた事実までは検証できない。今日の事故形を含め、意味の迂回を全部閉じたとは扱わない。

## 既存試験との突き合わせ

最初の全体実行 `python3 -m pytest -q` は `8 failed, 331 passed, 5 skipped in 69.72s`。
起点の `git archive efe4aad | tar -x -C .tmp/baseline`（index操作なし）で展開したコピーでも、次を再現した:

```sh
python3 -m pytest -q .tmp/baseline/tests/test_codex_impl_aws.py .tmp/baseline/tests/test_codex_review_cli.py
```

```text
8 failed, 27 passed in 12.62s
```

内訳はAWS設定を単一profileの全文と照合する旧い期待1件と、必須のCODEX_REVIEW_KIND_LABELを渡さないレビューCLIのfixtureで7件。現行の別名profileの集合・region・環境変数参照を検査し、レビューのfixtureに種別を明示して合わせた。製品のAWSやレビュー実装は変更していない。

```sh
python3 -m pytest -q tests/test_codex_impl_aws.py tests/test_codex_review_cli.py
```

```text
35 passed in 29.63s
```

初回の既存AWS変異検査は、変更していない等価の陽性対照も旧い期待で失敗したため、その初回の陰性結果は検出実績に算入しない（initial-aws-mutations.jsonl）。修正後の再実行結果だけを採用する。

全体の最終結果はall-tests.txt、既存オフライン変異検査の最終結果はexisting-aws-mutations.jsonlとexisting-github-mutations.jsonlに記録。実環境用probe_codex_github_environment.pyはCodexを起こすため実行禁止の対象として除外。

`bash -n bin/codex-impl` と `git diff --check` は成功。新規試験を含め、AWS・DB・stg・prdへ接続せず、実際のCodex/claude/LLMやghの書き込みも実行していない。

既存変異検査の最終コマンドと結果:
```sh
python3 tests/check_codex_impl_aws_mutations.py
python3 tests/check_github_account_mutations.py
```
AWS: exit 0・17/17ケース期待どおり（壊す変異16検出、等価陽性1成功）。GitHub: exit 0・12/12ケース期待どおり（壊す変異11検出、等価陽性1成功）。これは既存検査の回帰確認で、新規受領検査の着弾確認3件とは別集計。

全体の最終コマンドと結果（2026-11-09 10:17 JST確認）:
```sh
python3 -m pytest -q tests
```
```text
339 passed, 5 skipped in 91.18s (0:01:31)
```
5 skippedは、明示的opt-inが必要な実keychain試験4件と、実装起動口には該当しないレビュー専用記録1件。実Codexを起こすprobeは除外。全体339成功には新規25件を含む。

## commitと差分

- c3539e3: 実装前の計測を記録
- 610a5c1: 起動口・README・新規試験・実物fixture・既存依頼の出所行
- 99b2a7e: 起点でも再現する既存試験8失敗を現行契約に合わせて修正
- この報告と最終の出力ファイルを別のdocs commitで記録（SHAは最終回答に記載）

最終commit後に `git status --porcelain` が空であることを別途確認する。
差分の全文（計測・fixture・結果ファイルを含む）: `.tmp/receipt-full.diff`。最終commit後の `git diff --no-ext-diff --binary efe4aad HEAD` を保存したもの。自己参照を避けるため、この差分の写しだけはgitignore対象の検査生成物として置く。

完了の範囲: 事前基準で選ばれた(1)の実装・検査・commitまで。(2)および今日の事故形の拒否は未実装で、誤検知率に基づく明示的な不採用。この制限を含めて引き渡す。push・PR・枝操作・共有checkoutへの変更はしていない。
