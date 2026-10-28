# Codex にブラウザを使わせる定型（囲いを外さない・先に開いたブラウザへ繋ぐ）

Codex の囲い（workspace-write）の中では Chromium を起動できない（Mach の名前登録を拒否される）。
代わりに、頭（Claude Code の窓）が囲いの外で Chromium を起こし、Codex は localhost の CDP に繋ぐだけにする。
囲い・config.toml は変えない（`network_access = true` のままで localhost に届く）。
実測: 2026-10-27 deploy 窓（run `cdp-trial-20261027-110633-73891`・撮影 0.76秒・手元の HTML 2枚）。

## 頭がやること（起動の前）

1. ポートの空きを確かめる（例: `curl -s -m 3 http://127.0.0.1:9333/json/version` が何も返さない）。
2. 専用プロファイル・localhost 限定・期限つきで起こす。`run_in_background: true` で起動し、`&` で切り離さない。PID は自分の起動のものだけを控える。

```
P=<使い捨ての置き場>; mkdir -p $P/profile; \
exec timeout -k 10 3600 ~/Library/Caches/ms-playwright/chromium_headless_shell-<版>/chrome-headless-shell-mac-arm64/chrome-headless-shell \
  --remote-debugging-port=<ポート> --remote-debugging-address=127.0.0.1 \
  --user-data-dir=$P/profile --no-first-run about:blank > $P/chrome.log 2>&1
```

- `<版>` は使う playwright の `playwright-core/browsers.json` の `chromium-headless-shell` の revision に合わせる。
- 普段使いの Chrome やそのプロファイルには繋がせない（CDP で繋ぐと中の Cookie・ログインを全部操作できるため）。
- 資格情報（簡易認証・共通ログイン）は Codex に渡さない。ログインが要る画面は、資格情報を渡さない形が決まるまで対象外。
- 終わったら起こしたプロセスだけを止め、終了を確かめる（`timeout` で1時間後にも自然に消える）。

## 依頼文に貼る定型

```
## ブラウザの使い方
- ブラウザは自分で起動しない（`chromium.launch` を使わない）。localhost の <ポート> 番で Chromium が待っている。
  playwright の `chromium.connectOverCDP("http://127.0.0.1:<ポート>")` で繋ぐ。
- 新しいページを開いて使い、終わったらページだけ閉じる。`browser.close()` は呼ばない（接続を切るだけにする）。
- localhost 以外へは接続しない。開いてよい URL は <許す URL の一覧>。
- 繋げない・撮れないときは、出たエラーをそのまま書いて止まる（別の方法でブラウザを起動しない）。
```
