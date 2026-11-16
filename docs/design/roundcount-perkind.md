# #37 未発注の承認巡を種別へ帰属する

run: roundcount-perkind。開始版 e88a922be2c6b7c90b5ac7ac9f98d647b04e5d35。

## 読んだもの・判断

- 段取り表: 無し（割当ては #37、T番号の指定なし）。
- 本人決定: 今回の依頼にある 2026-11-16 10:58 JST main-index 中継「起動口を直してから出す」。
- 見本HTML: 無し（画面変更なし）。
- 前身: `docs/design/round-count-c.md`、`docs/design/round-count-c-REPORT.md`、既存 C 試験・変異実行器、`.tmp/repro/` の課題本文と5 state、`~/.claude/rules/review.md:6`。
- 試験設計: 指定のローカル `.claude/skills/test-design/` は無し。前身が参照する `/Users/matsukaze-takashi/updater/updater-index/_wt.noindex/rev9-audit/.claude/skills/test-design/SKILL.md` を読んで適用。

既存の承認Nの帰属検査は、未発注Nの保存済みround=Nが無いため混算へ戻る。設計3のauthorityでは分岐しない。
最小案: 候補種別が0、今回が未登録HEAD、今回種別の前身込み実績+1=N、Nが3〜5のときだけ、その新規1巡へ承認Nを帰属する。
保存済み候補の競合・不足、不正入力、過去の承認の検査と互換混算は維持する。前身にrootの未発注HEADを貸さない。
特例の固定総上限を変更しない。今回の人間承認で通常経路が先に通るため、特例の照合を緩める必要がない。

## 入力の区分表（試験追加前）

期待の出所は今回の依頼§1〜4と正典 review.md:6。既存互換は前身設計§2.2。

|入力|区分・境目・置く値|期待|出所|大きさ・試験名|
|---|---|---|---|---|
|#2078正常通し|設計3（ordinary2+特例1）・コード2・未発注HEAD・承認4/cap4・特例指定有無|設計4、人間承認で通過|今回§1/2|run_gate / repro_design4|
|種別|同じ履歴からコード新HEAD・承認3/cap3|コード3で通過|今回§3|run_gate / pending_kind|
|数字・承認欠け|3/4/5、承認なし・capだけ|各種別3以上停止|今回§3|run_gate / pending_boundaries|
|数字・上限|3/4/5、capが巡-1/巡/巡+1|上限以内だけ通過|今回§3|run_gate / pending_boundaries|
|数字・5巡|設計5+コード2、設計新HEAD、cap6|設計6で停止|今回§3|run_gate / sixth_round|
|継ぎ目・既発注|未登録HEAD/同HEAD、欠損round/候補競合/不足|未発注だけ新規帰属、他は従来互換|前身§2.2|関数・run_gate / pending_not_reused、既存invalid/deficit|
|できない操作|特例cap3の履歴から承認なしにcap4|特例は拒否|今回§2/4|evaluate / exception_cap_increase|
|文字・欠け|全角round/空HEAD、不正kind、説明文、偽区切り行|入力検査維持|前身§2.2/2.3|既存 C tests|
|前身・合図|前身の未発注を子孫で埋める|混算へ戻す|前身§2.2|既存 predecessor_approval|
|時刻|新しい時刻分岐なし|試験追加なし、既存特例の固定NOWを再利用|今回§2|既存 A tests|

## 再利用・7段

事前 `git grep -n -E '_selected_rounds|_target_total_rounds|target_total_rounds|ledger_own_round_for_predecessor|parse_approval_rounds' -- lib bin tests` は44行（`.tmp/roundcount-callers-before.log`）。
追加前の関連条件探索は13行（`.tmp/roundcount-perkind/reuse.log`）。既存のdistinct HEAD、再帰、承認parser、decide、pytest fixture、変異実行器を再利用する。

|項目|止まった段|
|---|---|
|未発注承認の帰属|㋐明示依頼、㋑既存計数・候補集合を利用、㋒標準比較、㋓㋔追加不要、㋕条件と制限が必要、㋖最小の分岐|
|回帰試験|㋑既存pytest/fixtureを再利用。再現stateは必要な5項目と承認行だけを固定|
|変異・影響計測|㋑既存実行器を再利用、㋒trace/hash/diff/mock、㋓gh読取のみ|
|新台帳・新依存・特例拡張|㋐不要、作らない|

|環境|経路・設定・データの違い|
|---|---|
|dev / stg / prod|巡数処理の環境別分岐は無し。いずれも接続・操作なし|
|ローカル|隔離stateで検査。実 `~/.codex-watch` と対象本文は読取だけで影響比較|
