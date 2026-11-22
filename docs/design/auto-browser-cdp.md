# codex-impl がブラウザを自動で用意する

## なぜ
Codex の囲い（workspace-write）の中では Chromium を起動できない（`bootstrap_check_in` が `Permission denied (1100)`）。正しい手は `templates/browser-cdp.md`（頭が囲いの外で Chromium を起こし、Codex は CDP で繋ぐ）だが、頭が依頼文への定型の貼り付けを4回忘れた（2026-10-29・11-06・11-12・11-22。最後は updater-index run `2271-q1124-sm-20261122-231412-46493`）。覚えておくことに頼らない形にする（2026-11-22 本人決定「起動口が自動で用意する案」）。

## 何をするか（codex-impl だけ）
1. 依頼文（PROMPT_FILE）に次のいずれかの語があれば「ブラウザを使う依頼」とみなす（大小文字を区別しない）: `playwright`・`chromium`・`connectOverCDP`・`style-diff`・`run.sh dev`・`run.sh stg`・`https://dev.`・`https://stg.`・`見本照合`・`撮影`・`スクリーンショット`・`screenshot`。語で判定するので見逃しはありうる（下の「見逃したとき」）。
2. 当たったら、起動の前に頭のプロセスとして（囲いの外で）`chrome-headless-shell` を起こす。
   - ポート: 9333〜9399 のうち `curl -s -m 2 http://127.0.0.1:<p>/json/version` が応答しない最初の番号。
   - 版: 環境変数 `CODEX_IMPL_CHROMIUM` があればそれ、無ければ `~/Library/Caches/ms-playwright/chromium_headless_shell-*` の番号が最大のもの。
   - `timeout -k 10 5400 <shell> --remote-debugging-port=<p> --remote-debugging-address=127.0.0.1 --user-data-dir=<run 専用の一時ディレクトリ> --no-first-run about:blank`。
   - 起動後10秒以内に `/json/version` が応答しなければ、起こした PID を止めて、理由を表示し非0で終える（Codex は起動しない）。
3. 依頼文の末尾に `templates/browser-cdp.md` の「依頼文に貼る定型」を、`<ポート>` を実際の番号に置き換えて足す（依頼文がすでに `connectOverCDP` を含み、かつ `127.0.0.1:<数字>` を書いていれば、ブラウザも定型も足さない＝頭が自分で用意した場合）。
4. state に `browser_port=`・`browser_pid=` を書く。
5. 後始末: Codex の PID が終わったら、起こした Chromium の PID だけを止め、終了を確かめる見張りを `nohup` で起こす。`timeout` で 90 分後にも消える。broadcast の kill はしない。
6. `CODEX_IMPL_NO_BROWSER=1` で 1〜5 を全部飛ばせる（ブラウザが要らないのに語に当たった場合の逃げ道）。

## 何が起きうるか
| 場合 | 結果 |
|---|---|
| 間違って当たる | 要らない Chromium が1つ起き、Codex の終了か90分で消える。作業は止まらない |
| 見逃す | 今までどおり Codex 内の launch が Permission denied で止まる |
| Chromium を起こせない | Codex を起動せず、理由を出して非0で終える |
| 戻す | この変更の commit を戻す |

## 試験
- 語あり → Chromium が起き、依頼文に定型（実ポート入り）が足され、state に2行が入る。Codex の終了後に PID が消える。
- 語なし → 何も起きない（陽性対照）。
- `connectOverCDP` と `127.0.0.1:<数字>` を含む → 足さない。
- `CODEX_IMPL_NO_BROWSER=1` → 足さない。
- Chromium の実行ファイルが無い → 非0で終わり、Codex を起動しない。
- 陰性試験（変異）: 語の判定を外す／定型の追記を外す／後始末を外す／応答確認を外す、を当てて赤を確かめる。
