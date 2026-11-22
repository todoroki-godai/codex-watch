# codex-impl がブラウザを自動で用意する

## なぜ
Codex の囲い（workspace-write）の中では Chromium を起動できない（`bootstrap_check_in` が `Permission denied (1100)`）。正しい手は `templates/browser-cdp.md`（頭が囲いの外で Chromium を起こし、Codex は CDP で繋ぐ）だが、頭が依頼文への定型の貼り付けを4回忘れた（2026-10-29・11-06・11-12・11-22。最後は updater-index run `2271-q1124-sm-20261122-231412-46493`）。覚えておくことに頼らない形にする（2026-11-22 本人決定「起動口が自動で用意する案」）。

## 何をするか（codex-impl だけ）
1. 依頼文（PROMPT_FILE）に次のいずれかの語があれば「ブラウザを使う依頼」とみなす（大小文字を区別しない）: `playwright`・`chromium`・`connectOverCDP`・`style-diff`・`run.sh dev`・`run.sh stg`・`https://dev.`・`https://stg.`・`見本照合`・`撮影`・`スクリーンショット`・`screenshot`。語で判定するので見逃しはありうる（下の「見逃したとき」）。
2. 当たったら、起動の前に頭のプロセスとして（囲いの外で）`chrome-headless-shell` を起こす。
   - 版: 環境変数 `CODEX_IMPL_CHROMIUM` があればそれ、無ければ `~/Library/Caches/ms-playwright/chromium_headless_shell-*` の番号が最大のもの。
   - ポートは選ばない。`--remote-debugging-port=0`（OS が空きを割り当てる）で起こし、**その run 専用の一時ディレクトリ**を `--user-data-dir` にする。Chromium がそのディレクトリに書く `DevToolsActivePort` の1行目を読んでポートを得る（他の run のブラウザの応答と取り違えない。巡1 [Must]1）。
   - 起動は監督役のサブシェル1つが行う: `( timeout -k 10 5400 <shell> --remote-debugging-port=0 --remote-debugging-address=127.0.0.1 --user-data-dir=<dir> --no-first-run about:blank & CH=$!; ... )`。Chromium は監督役の子なので、監督役が `wait` するまで PID は再利用されない（巡1 [Must]2）。
   - 10秒以内に `DevToolsActivePort` が現れ、そのポートの `/json/version` が応答しなければ、監督役が自分の子 `CH` だけを止めて `wait` し、理由を表示して非0で終える（Codex は起動しない）。
3. 依頼文の末尾に `templates/browser-cdp.md` の「依頼文に貼る定型」を、`<ポート>` を実際の番号に、`<許す URL の一覧>` を「この依頼文に書かれた URL だけ」に置き換えて足す。ログインの一文は足さない（ログインが要る画面は、頭がこれまでどおり定型を自分で貼る）（依頼文がすでに `connectOverCDP` を含み、かつ `127.0.0.1:<数字>` を書いていれば、ブラウザも定型も足さない＝頭が自分で用意した場合）。
4. state に `browser_port=`・`browser_pid=` を書く。
5. 後始末: 同じ監督役が、Codex の PID の終了（`kill -0` で見るのは時刻を知るためだけ）を待ち、終わったら自分の子 `CH` だけに TERM を送って `wait` する。止める対象は監督役の子だけで、`ps` で探した PID や名前では止めない。通常終了・`timeout` の期限切れ（90分）・Chromium の自滅のどれでも、監督役は `wait` で子を回収してから一時ディレクトリを消す。state の `browser_pid` は Chromium の PID（監督役の子）、`browser_supervisor_pid` は監督役の PID と書く。
6. `CODEX_IMPL_NO_BROWSER=1` で 1〜5 を全部飛ばせる（ブラウザが要らないのに語に当たった場合の逃げ道）。

## 何が起きうるか
| 場合 | 結果 |
|---|---|
| 間違って当たる | 要らない Chromium が1つ起き（起動待ち最大10秒）、Codex の終了か90分で消える。Chromium の実行ファイルが無い機械では Codex を起動せずに止まるので、`CODEX_IMPL_NO_BROWSER=1` を付けて起動し直す |
| 見逃す | 今までどおり Codex 内の launch が Permission denied で止まる |
| Chromium を起こせない | Codex を起動せず、理由を出して非0で終える |
| 戻す | この変更の commit を戻す |

## 試験
- 2件を同時に起こしても、それぞれ自分の `DevToolsActivePort` のポートを使う。片方の Chromium だけ起動に失敗させると、失敗側は Codex を起動しない
- Codex の終了後、監督役の子だけが止まり、同じ名前の別プロセス（試験で先に起こしたもの）は残る
- 語あり → Chromium が起き、依頼文に定型（実ポート入り）が足され、state に2行が入る。Codex の終了後に PID が消える。
- 語なし → 何も起きない（陽性対照）。
- `connectOverCDP` と `127.0.0.1:<数字>` を含む → 足さない。
- `CODEX_IMPL_NO_BROWSER=1` → 足さない。
- Chromium の実行ファイルが無い → 非0で終わり、Codex を起動しない。
- 陰性試験（変異）: 語の判定を外す／定型の追記を外す／後始末を外す／応答確認を外す、を当てて赤を確かめる。
