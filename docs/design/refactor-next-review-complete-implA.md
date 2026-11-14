## 今回の作業（run 名: review-complete-implA-inputs）

作業場所: /Users/matsukaze-takashi/matsukaze-utils/codex-watch/_wt.noindex/review-complete

やること: docs/design/review-complete-implA-REPORT.md を読み、開始時のHEAD・statusを確認する。前回は製品未変更、文書3ファイルが未追跡。前回のcommitを期待todoroki-godai／実際matsukaze-mindenの名義不一致でPreToolUseが拒否した。gh auth switch・フック迂回はせず、書き込み可能な担当が処理する。前回の報告を消さない。

Aの実装に先立ち、state外のAgent/Task発注も含む履歴正本の保存先、対象セッションの列挙範囲と欠落検出、取得担当、出所付き補完の照合契約を設計補足する。repo slug・正規化したGit common directory・2規則の既知blob hashを結ぶ固定登録の所在・登録担当・対象版も具体化する。必要な正本が無ければ選択肢と既定案を記録して停止し、自己申告で完全性や権限を作らない。

通常の有効な人間承認では公開状態APIだけの取得失敗で止めないこと、補完後に巡3の判定・前置き・予約・保存が一致することについて入力区分表を補足する。予約とCの重なる最小範囲を明記する。C全体・D接続・製品実装はこの手番に含めない。

禁止: 他LLM起動、AWS・DB接続、prod操作、stg/dev書き込み、gh書き込み・名義切替、push・PR・merge・枝操作・checkout・stash・reset・rebase、依存install。updater-index・~/.claude・本体checkoutは読むだけ。実物の~/.codex-watchへ書かない。書き込みは当該作業場所内。

終わりの条件: 正本と取得契約・固定登録・Aに必要なCとの重なりを、実装担当が推測せず着手できる具体的な形で記録する。未確定なら不足を明記して止まり、完成扱いにしない。次の実装run名候補は review-complete-implA2。文書をcommitできなければフックの理由を残す。
