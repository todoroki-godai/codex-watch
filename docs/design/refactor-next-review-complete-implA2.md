## 今回の作業（run 名: review-complete-implA2-verify）

作業場所: /Users/matsukaze-takashi/matsukaze-utils/codex-watch/_wt.noindex/review-complete（既存のfeat/review-gate-prerelease。枝操作は禁止）

やること: docs/design/review-complete-implA2-REPORT.md と review-complete.md のA、指定設計レビューと前回報告を読み、HEAD・status・差分を確認する。前回はHEAD b96b8a977e1f0c67706e94b61a763f668c0e2cb6、Aの実装・README・75追加試験・変異runner・報告と転記用2ファイルが未commit。全試験は647 passed, 5 skipped（652件・253.50秒）。前回報告3ファイルを保持する。

PreToolUseがcommitを含むコマンドを実行前拒否した。期待名義todoroki-godai／write時点matsukaze-minden。作業場所の.claude/codex-github-account=todoroki-godaiでは解消しなかった。書き込み名義を扱える担当が通常の経路でcommit可能にする必要がある。gh auth switch・フック迂回・共有設定の無断変更はしない。再び拒否されたら同じ理由を残す。

commit可能なら実装差分を確認して意味のある単位でcommitする（closeキーワード・Co-Authored-By無し）。statusが空になってから `python3 tests/check_prerelease_mutations.py` を実行する。runnerは未実測なので実行上の欠陥があれば直し、commitした版からやり直す。8陰性（①〜④と異種回避）すべて赤、意味保存対照は緑、各独立diffと実行行traceの着弾を確認する。緑残存・未着弾があれば完成扱いにしない。全出力は.tmpに置きcommitしない。原本のgit diffとstatusが空であることを変異前後に確認する。

実装を変えたら区分表を先に更新し、パッケージ全体 `python3 -m pytest tests` を回す。通常の人間承認は公開状態APIの失敗で止めない。本文だけの発注も数え、巡3の判定・前置き・予約・保存を揃える。C全体・D・配布・実レビューの発注に進まない。完成後、実測版と結果をREPORTへ反映してcommitする。cold review未実施を分けて報告する。

禁止: claude/他LLM起動、AWS/DB接続、prod操作、stg/dev書込み、gh書込み・名義切替、push・PR・merge・枝作成削除・checkout・stash・reset・rebase・依存install。~/.claude・updater-index・本体checkoutは読み取り専用。実物の~/.codex-watchへ書かない。一時置場は作業場所内か試験自身の一時ディレクトリだけ。

終わりの条件: Aの原本commit、全試験、陰性8件と意味保存対照の実測・独立着弾証跡、最終clean、報告のcommitまで揃うこと。足りない場合は理由を残して未完了とする。指定のupdater-indexへの2ファイルは許可外で未作成なので、書込み可能な依頼元へ転記用を渡す。次のrun名候補は review-complete-implA2-finish（残件無しなら次回依頼は「なし」）。
