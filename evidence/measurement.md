# 実装前の計測（2026-11-09）

取得時刻: 2026-11-09 10:10:25 +09:00（収集開始は10:09台）。
対象: ~/.codex-watch/*.state の mode=workspace-write（2835件）のうち、prompt= が現存ファイルを指す1203件から、stateのmtime降順で本文の完全一致を重複排除した直近60件。全履歴の推定値ではなく、取得できた直近標本。失われた1632件の本文は未取得。ログやscratchpadからの復元は混ぜていない。
1件=取得時の依頼文本文1種類。同一パスでも版の過去復元はしない。起動数とは違う。

収集コマンド（python3の標準ライブラリ、元ファイルへ書き込みなし）:
```python
for p in sorted((Path.home()/'.codex-watch').glob('*.state'),
                key=lambda p:p.stat().st_mtime, reverse=True):
    d=dict(x.split('=',1) for x in p.read_text(errors='replace').splitlines() if '=' in x)
    q=Path(d.get('prompt','/nonexistent'))
    if d.get('mode')!='workspace-write' or not q.is_file(): continue
    t=q.read_text(errors='replace')
    if t in seen: continue
    seen.add(t); rows.append((p.stem,str(q),t))
    if len(rows)==60: break
```
保存したのはパス・state ID・本文SHA256・分類のみ（corpus-paths.json）。再計数: `python3 evidence/measure_receipt.py`。取得後の本文変更はhash不一致で止まる。

分類: 作業の目的・今回の作業・末尾の追記を読み、「既存成果物に返ったレビューの具体的指摘を直す」指示をA、実装・調査・検査失敗の修正・本人の新規決定の反映をBとした。単に[Must]やレビューという語があるだけではAにしない。A=20、B=39、迷い=1（id18 eic-fix2:前の依頼の続きで「指摘4・5」を仕上げるが本文だけではレビュー出所が確定しない。率の分母から除外）。id31は残存Must/Should/Nitの直し、id38は速さのレビュー結果を受けた直しなのでA。

指定の語: `巡[0-9]|\[Must\]|指摘を反映`（本文全体、[Must]はリテラル）。
- Bの誤検知候補=9/39=23.0769%。例: id3 receipt-gate-hook（新機構の目的・必須ゲートの説明）、id15 starfix-red1（原因調査だけだが必須ゲートの定型文に[Must]）、id20 starfix-prep2（検査準備の続きだが同じ定型文）。
- Aの見逃し候補=1/20=5%。id21 should1: レビューの[Should]1件だけを直す指示で、指定語を含まない。
- 迷いのid18も指定語なし。仮にAへ含めればA21・見逃し2、Bの率は変わらない。

判定: 5%超のため(2)は入れず(1)だけ。語の組の試算（採用しない）:
- `巡[0-9]|指摘を反映`: B誤検知0/39、A見逃し5/20（21,31,38,41,43）。
- `レビュー[^\n]{0,40}(?:指摘|直す|修正)`: B誤検知3/39=7.69%、A見逃し4/20（0,38,40,55）。

資格情報: 本文のtoken/key/passwordの値・既知token形式を収集時に照合。fixtureにするid5,7,9は全文を目視でも確認し、資格情報なし。本文はこの3件だけtests/fixtures/receiptに原文のまま保存し、試験側で「直しの出所: なし」を付ける（本文は変更しない）。
