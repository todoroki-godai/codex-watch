# Receipt Must1–3 検証記録

対象: fix/receipt-must3、起点ff0a1dc。参照: todoroki-godai/claude-config#55。

## TDD

本体変更前の実測: `17 failed, 158 passed in 18.67s`。
Must1 6件、Must2 4件、Must3 6件、拒否表示強化1件が赤。
テストcommit c306e6e → 修正commit 451bfa1。

## 最終検証

コマンド: `python3 -m pytest tests/ -q`

188 passed in 8.86s

依頼に記載された既知の5失敗はこの環境では再現しなかった。
state・git fixture・fake CLIはtmp_path配下。実LLM/codexへの発注なし。
共有checkoutの編集・push・PR・mergeなし。

## 単独変異

全件451bfa1のclean状態から単独適用。適用前・復元後のgit status --porcelainが空であることをassert。
適用中は対象1ファイルのみM、git diff非空を確認。pytestは全件exit 1で指定テストのassertion失敗。
以下に実際の差分を保存する。

### M1: 失敗伝播を外し元のrecipeへ戻す

- status: 空 → `M lib/round_gate.py` → 空
- コマンド: `python3 -m pytest tests/test_round_gate.py::test_hash_failure_has_no_output -q`
- 結果: `6 failed in 1.10s`
- 経路の実行証拠: git実行のrc=0で失敗。個別git失敗はstderrのreached-<command>確認も通過し、注入経路を実行済み。

```diff
diff --git a/lib/round_gate.py b/lib/round_gate.py
index d3047df..03d162c 100644
--- a/lib/round_gate.py
+++ b/lib/round_gate.py
@@ -395,11 +395,9 @@ def check_receipt(expected_head_sha: str, expected_content_hash: str, report_tex
 # && は個別の git、pipefail は内外のパイプの失敗を伝播する。
 # 成功するまで出力を保留するため、失敗した部分入力のハッシュを表示しない。
 CONTENT_HASH_RECIPE = (
-    "bash -o pipefail -c '"
-    'hash=$( { git status --porcelain -uall && git diff HEAD && '
-    'git ls-files -o --exclude-standard -z | xargs -0 -r git hash-object; } '
-    '| shasum -a 256) && printf "%s\\n" "${hash%% *}"'
-    "'"
+    "(git status --porcelain -uall; git diff HEAD; "
+    "git ls-files -o --exclude-standard -z | xargs -0 -r git hash-object) "
+    "| shasum -a 256 | awk '{print $1}'"
 )
```

### M2: 先頭10行の自由検索へ戻す

- status: 空 → `M lib/round_gate.py` → 空
- コマンド: `python3 -m pytest tests/test_round_gate.py::test_receipt_rejects_misplaced_claims -q`
- 結果: `4 failed in 0.05s`
- 経路の実行証拠: check_receiptの実戻り値がokになった。引用・空行・順序交換・判定行欠落で失敗。

```diff
diff --git a/lib/round_gate.py b/lib/round_gate.py
index d3047df..1f744c5 100644
--- a/lib/round_gate.py
+++ b/lib/round_gate.py
@@ -317,9 +317,9 @@ RE_RECEIPT_CONTENT_HASH = re.compile(r"^content_hash=([0-9a-fA-F]{64})\s*$", re.
 
 def parse_receipt_claim(report_text: str) -> tuple[str | None, str | None]:
     """2行目の read_sha と3行目の content_hash を読む。位置ずれは欠落扱い。"""
-    lines = (report_text or "").splitlines()
-    m_sha = RE_RECEIPT_READ_SHA.fullmatch(lines[1]) if len(lines) > 1 else None
-    m_hash = RE_RECEIPT_CONTENT_HASH.fullmatch(lines[2]) if len(lines) > 2 else None
+    head = "\n".join((report_text or "").splitlines()[:10])
+    m_sha = RE_RECEIPT_READ_SHA.search(head)
+    m_hash = RE_RECEIPT_CONTENT_HASH.search(head)
     sha = m_sha.group(1).lower() if m_sha else None
     content_hash = m_hash.group(1).lower() if m_hash else None
     return sha, content_hash
```

### M3: 受領処理に tokens used 条件を戻す

- status: 空 → `M bin/codex-status` → 空
- コマンド: `python3 -m pytest tests/test_codex_status_receipt.py::test_finished_receipt_without_tokens -q`
- 結果: `6 failed in 0.21s`
- 経路の実行証拠: 終了PID・判定行0件の実出力で受領行が消え、6入力で表示assertionが失敗。

```diff
diff --git a/bin/codex-status b/bin/codex-status
index a403629..b3d2701 100755
--- a/bin/codex-status
+++ b/bin/codex-status
@@ -84,7 +84,7 @@ show_one() {
   IFS=$'\t' read -r hdr_model hdr_model_source hdr_effort hdr_effort_source <<<"$(extract_codex_log_header "$log")"
   echo "要求値               : model=${requested_model:-(未指定)} effort=${requested_effort:-(未指定)}"
   echo "ログ先頭のヘッダー（参考・run同一性は未検証）: model=$hdr_model($hdr_model_source) effort=$hdr_effort($hdr_effort_source)"
-  if [[ "$alive" == "終了" ]]; then
+  if [[ "$alive" == "終了" && "$verdict_count" -gt 0 ]]; then
     local report
     report="${log%.log}.report"
     rebuild_report_if_needed "$log" "$report" || true
```

### M4: 拒否時だけreceipt_msgを空にする

- status: 空 → `M bin/codex-status` → 空
- コマンド: `python3 -m pytest tests/test_codex_status_receipt.py::test_status_shows_receipt_rejected_line_on_mismatched_claim -q`
- 結果: `1 failed in 0.09s`
- 経路の実行証拠: 終了かつ判定行ありの不一致レポートで、read_sha不一致の理由表示assertionが失敗。

```diff
diff --git a/bin/codex-status b/bin/codex-status
index a403629..5dda1cb 100755
--- a/bin/codex-status
+++ b/bin/codex-status
@@ -95,6 +95,7 @@ show_one() {
     # receipt は照合結果次第で非0を返す（rejected=4）。判定結果の表示が目的であって
     # codex-status 自体の異常終了ではないため、ここでは exit code を握りつぶして表示のみ行う。
     receipt_msg="$(python3 "$GATE_PY" receipt --state-file "$state_file" --report "$report" 2>&1 || true)"
+    [[ "$receipt_msg" == *"受領可:"* ]] || receipt_msg=""
     echo "受領     : $receipt_msg"
   fi
   if [[ "$alive" == "終了" && "$verdict_count" -gt 0 ]]; then
```

### M5: 追加: HEAD差分を作業ツリー対index差分へ変更

- status: 空 → `M lib/round_gate.py` → 空
- コマンド: `python3 -m pytest tests/test_round_gate.py::test_git_content_hash_differs_for_fully_staged_content_with_no_working_tree_diff -q`
- 結果: `1 failed in 0.16s`
- 経路の実行証拠: 完全ステージ済みの異なる2内容で同じハッシュになりhash_a != hash_bが失敗。

```diff
diff --git a/lib/round_gate.py b/lib/round_gate.py
index d3047df..4bfb5a5 100644
--- a/lib/round_gate.py
+++ b/lib/round_gate.py
@@ -396,7 +396,7 @@ def check_receipt(expected_head_sha: str, expected_content_hash: str, report_tex
 # 成功するまで出力を保留するため、失敗した部分入力のハッシュを表示しない。
 CONTENT_HASH_RECIPE = (
     "bash -o pipefail -c '"
-    'hash=$( { git status --porcelain -uall && git diff HEAD && '
+    'hash=$( { git status --porcelain -uall && git diff && '
     'git ls-files -o --exclude-standard -z | xargs -0 -r git hash-object; } '
     '| shasum -a 256) && printf "%s\\n" "${hash%% *}"'
     "'"
```

### M6: 追加: 未追跡blob hashをパス出力へ変更

- status: 空 → `M lib/round_gate.py` → 空
- コマンド: `python3 -m pytest tests/test_round_gate.py::test_git_content_hash_detects_untracked_file_content_change -q`
- 結果: `1 failed in 0.17s`
- 経路の実行証拠: 同名未追跡ファイルの内容変更で同じハッシュになりbefore != afterが失敗。

```diff
diff --git a/lib/round_gate.py b/lib/round_gate.py
index d3047df..3cdc7e9 100644
--- a/lib/round_gate.py
+++ b/lib/round_gate.py
@@ -375,7 +375,7 @@ def check_receipt(expected_head_sha: str, expected_content_hash: str, report_tex
 # - `git status --porcelain -uall`: 追跡ファイルの状態変化（add/削除/リネーム含む）と、
 #   未追跡ファイルの**存在**をパスの一覧として拾う（中身は拾わない）。
 # - `git diff HEAD`: 追跡ファイルの**内容差分**（ステージ済み・未ステージ双方、HEAD との差分）。
-# - `git ls-files -o --exclude-standard -z | xargs -0 -r git hash-object`: 未追跡ファイルの
+# - `git ls-files -o --exclude-standard -z | xargs -0 -r printf "%s\\n"`: 未追跡ファイルの
 #   **中身**を git blob ハッシュ（追加ファイルの中身が変わっても `git status`/`git diff HEAD` の
 #   どちらにも出ない＝未追跡ファイルの中身の取りこぼしへの対処。2026-09-21 [Must]3①）。
 #   index には触れない（`git add` しない）。`-r`（GNU xargs 互換。macOS xargs は既定で
@@ -397,7 +397,7 @@ def check_receipt(expected_head_sha: str, expected_content_hash: str, report_tex
 CONTENT_HASH_RECIPE = (
     "bash -o pipefail -c '"
     'hash=$( { git status --porcelain -uall && git diff HEAD && '
-    'git ls-files -o --exclude-standard -z | xargs -0 -r git hash-object; } '
+    'git ls-files -o --exclude-standard -z | xargs -0 -r printf "%s\\n"; } '
     '| shasum -a 256) && printf "%s\\n" "${hash%% *}"'
     "'"
 )
```

## 探索した入力クラスと変換

- git管理外ディレクトリ、GIT_INDEX_FILE=/dev/null。
- status / diff / ls-files / hash-objectだけをexit 73に置換。他のgitは実gitへ転送。
- 今回の申告を省略し過去値を引用、空行挿入、2・3行目交換、1行目削除。
- 終了プロセスでtokens used削除／ログ削除 × report正しい／空／不在。
- read_sha不一致、拒否時だけ受領メッセージを削除。
- 完全ステージ済みの異なる内容。HEAD比較をindex比較へ変換（M5）。
- 同じパスの未追跡ファイルの内容変更。blob hashをパスへ変換（M6）。

M5/M6はエラー伝播・申告位置・表示分岐とは異なる、ハッシュ対象データの欠落。6変異の生き残りなし。

## 陽性対照

`python3 -m pytest tests/test_round_gate.py::test_receipt_positive_real_recipe -q`

2 passed in 0.27s

clean・dirtyともに唯一のrecipeを別途実行した申告でok。
dirtyはCRLFの追跡ファイル差分＋未追跡バイナリ、申告レポート自体もCRLF。
既存の発注口テストでもプロンプトから抽出したrecipeとstateの一致が通過。

## はしご

- 共通recipe: 段2。既存定数とgit_content_hashを再利用。本体関数・依存追加なし。
- 失敗伝播・出力保留: 段4。bash pipefail、&&、コマンド置換、printf、パラメータ展開。
- parse_receipt_claimの固定位置・行数分岐: 段3。splitlinesと既存正規表現fullmatch。RECEIPT_HEAD_LINESは廃止。
- codex-statusの終了時分岐: 段4。シェル条件。再構築・receipt・|| trueを再利用。
- CLI拒否ラベル分岐: 段6。既存statusから1行で受領不可を付与。JSON契約維持。
- test_hash_failure_has_no_output: 段3。subprocess・一時ファイル・fake git。
- test_receipt_rejects_misplaced_claims: 段3。文字列とリスト。
- test_receipt_positive_real_recipe: 段2。既存_init_repo・recipe・照合を再利用。
- test_finished_receipt_without_tokens: 段2。既存state生成・status起動を再利用。
- テストパラメータ化: 段5。導入済みpytest。新フレームワークなし。

## 未解決・懸念

依頼範囲の未解決なし。gitignore対象・submodule内部は指定どおり対象外。
recipeは標準bashを使用（既存CLIもbash依存）。extract_verdict_lineの契約は変更なし。
