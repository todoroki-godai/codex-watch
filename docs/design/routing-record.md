記録の自動作成: 項目20件のうち自動4件・一部12件・不可4件／見込み 約180分

# 発注ごとの記録の設計

対象は HEAD `9fce0727db8ab967a6334ab2a8d84a669e2a3b64`。これは設計であり実装・レビュー・実発注はしていない。以下の20件は JSON の意味単位で数え、条件付き項目も含む。自動は必要な材料が揃った通常ケースで機械的に導出できるという意味で、取得失敗まで保証しない。一部は明示された正本や人の入力がある場合だけ作れる。不可は現行の発注材料から値の意味を確定できないもの。参照の `route.mjs` 等は `/Users/matsukaze-takashi/.claude/_wt.noindex/review-gate-parts/skills/review-gate/` 内。

| # | 記録の項目 | 読む箇所 | 判定と材料・不足時に誰がどこへ書くか |
|---|---|---|---|
| 1 | series_id | route.mjs:253 | 一部。課題IDは取得可能だが再設計等をまたぐ系列は同一とは限らない。依頼者が依頼文の構造化行に正本の系列IDを書く。 |
| 2 | predecessor_ids | route.mjs:253 | 一部。履歴から明示された前身を使う。未記載と前身なしは別。依頼者が同じ行にID配列または明示的な `[]` を書く。 |
| 3 | base_sha | route.mjs:254 | 一部。系列の開始commitが正本に固定されていればgitで検証。なければ依頼者が依頼文にフルSHAを固定。merge-baseで代用しない。 |
| 4 | kind | route.mjs:255 | 作れる。既存 `CODEX_REVIEW_KIND_LABEL` の設計/コードを design/code に対応。 |
| 5 | history_source.available | route.mjs:256 | 作れる。正本取得成功だけを true にする。失敗は false。 |
| 6 | history_source.url | route.mjs:256 | 一部。issue/PR target から正本URLを作る。none/bypass や不明時は依頼者が正本を示す。 |
| 7 | history_source.fetched_at | route.mjs:256 | 作れる。取得成功時のUTC時刻。 |
| 8 | history_source.body_hash | route.mjs:256 | 一部。取得した本文の同じバイト列のSHA-256。取得失敗時は空履歴にしない。 |
| 9 | target_paths | route.mjs:263,273; routing.md:39-45 | 一部。固定baseと作業木が有効なら route の `collectChanges` と同一の対象集合。base不明は依頼者が確定。未追跡・削除を含む。 |
| 10 | current.event_id | route.mjs:259,268 | 作れる。既存 RUN_ID。ただし履歴中との衝突を検査。 |
| 11 | current.family_tags | route.mjs:260; routing.md:46-47 | 一部。初巡と証明できる場合だけ `initial`、直前指摘0件と確認できる場合だけ `none`。他は依頼者が依頼文に指摘族を記入。 |
| 12 | current.target_sha | route.mjs:260-262 | 一部。対象gitの実HEADを取得。gitなしや取得不能は不明として警告、値を偽造しない。 |
| 13 | current.content_hash | route.mjs:263-264,42-57 | 一部。base・paths確定時に部品の `contentIdentity` を再利用。既存 round_gate の作業木全体ハッシュとは別物。 |
| 14 | current.target_list_hash | route.mjs:263-265,42-57 | 一部。同じ `contentIdentity` の対象一覧ハッシュ。削除も含む部品のレシピを使う。 |
| 15 | current.input_tokens / input_hash | route.mjs:241-245,275 | 不可。実効入力全体と公式または同一tokenizerの実測は発注前に保証できない。任意項目として未取得理由を残し、実測できた場合のみ実行記録担当が実入力ハッシュと共に書く。 |
| 16 | history の event_id / status / family_tags / target_sha / content_hash / finding_family_tags | route.mjs:257,267-270,284-287 | 一部。課題本文とstateを照合して確実な行だけ変換。既存履歴の行は全フィールドを保証しない。依頼者・受領担当が正本の各巡に不足するID、受領状況、SHA、対象ハッシュ、族と指摘族を記録する。欠落巡を省略しない。 |
| 17 | history.family_stop_cleared_by.{stopped_event_id,evidence} | route.mjs:288-292 | 不可。解除は本人の裁定・訂正が必要。本人が正本に対象停止IDと根拠を書く。未解除なら省略。 |
| 18 | checks の plan / evidence / bundle_id / owner / execution_at | route.mjs:299-310 | 不可。適用確認の計画・証跡・実行責任は推測できない。発注者または実行担当が依頼文・検査結果に記入。登録PJが空なら現行は適用IDなし。 |
| 19 | reporting_complete | route.mjs:307-308 | 一部。報告済みと明示された正本からのみ true。未確認は true にしない。報告担当が正本に段階を明記。 |
| 20 | greens 各行の exit_code / cwd / argv / config_file / config_hash / include / exclude / collected_set / canonical_collected_set | route.mjs:316-319,175-239; routing.md:53-55 | 不可。現行発注口は実行結果全体を持たない。実行担当が既存試験記録に実コマンド・終了値・設定と収集集合を残し、記録器が転記。設計で未実行なら `[]`、コードで空にして成功を装わない。 |

`ledger.mjs` の reviews/findings 等は別の集計台帳の契約で、route はこの JSON を読まない（ledger.mjs:85-87、route.mjs:246-270）。新台帳は作らない。`limits.json` は部品の設定（現在 cumulative_units 60、active_projects 空）で発注記録の項目ではない。`adapter.py:57-61` は記録ファイルのパスとリポジトリを渡すだけ。既存 `routing_warn.py:123-126` は環境変数を読み、無指定時には部品がエラーになる。

## 最小案と扱い

発注口の既存 gate が通り RUN_ID が確定した後、`bin/codex-review:251-252` の警告直前に、取得できた正本・state・環境変数・git と、依頼者が明示した構造化行を組み立てる。既存の `round_gate.py` の正本取得・前身・巡・state読取を再利用し、`history_backfill.py:14-54` の一対一照合条件も参考にする。行の対応が曖昧なら補完しない。route の `collectChanges` と `contentIdentity` をエクスポート済み関数として使い、別のハッシュ実装を作らない。DのJSONは認証ではない。本文取得失敗、未受領、証拠欠落はそのまま欠落として残す。

記録は安全な一時ファイル（専用ディレクトリ、0600、排他的作成）に保存し、警告プロセスだけに絶対パスを `REVIEW_GATE_RECORD` で渡し、読み終えたら削除する。既に明示された外部パスは優先する案を既定とし、生成失敗は安全な分類の警告にして従来通り発注を続ける。タイムアウトも含め既存の警告上限を守る。生本文・依頼文・資格情報をログに書かない。既存の巡数ゲート、予約、別系統レビュー、[Must]残存時の着手禁止、決定論チェックと変異確認は変更しない。警告のみというのはこの観測処理についてであり、既存ゲートを緩める意味ではない。

## 既知の限界

読む側の部品へは記録のパスを渡すため、`lib/routing_warn.py:140-151` の読込前後の照合の間に記録を差し替えて戻すと、別の記録で判定した結果が警告の記録に残り得る。
発注を止める関門は迂回されず、影響は警告の記録だけ。差し替えには同じ利用者の権限が要る。
完成条件2「記録は認証ではない」の外側として扱う。本人が「既知の限界として入れる」と裁定し、調整役 main-index 経由で2026-11-15 19:17:10 JSTに受領した。

## 影響の見込みと測り方

REPORT-d.md:22-39 は2026-11-15 10:00:03 JSTまでの7日間、stateの started_at により抽出した一意のOPEN対象37件。空JSONでのD単体実験であり、実際の新規停止件数ではない。

| 当時の最初の理由 | 母数 | この案でその「記録なし」の理由が減る見込み | 根拠・限界 |
|---|---:|---:|---|
| series/predecessor欠落 | 32 | 0〜32件、点推定不可 | 正本に系列・前身が明記された件だけ解消。欠けた情報を推測しない。解消しても次の不足や停止に移る場合がある。 |
| 作業場所消失 | 5 | 0件 | 記録生成では作業場所を復元できない。既存入口でも拒否され得る。 |
| 状態取得不能 | 2 | 未算定 | 37件の外。OPENか不明なので分母に加えない。 |

実装後は当時の対象一覧・時刻・最新state選択・同じ作業場所を固定し、原資料と正本を保存した読取専用スナップショットで、各対象を旧条件（空JSON）と新生成条件で同じrouteに通す。発注せず、対象ごとに取得可否、生成材料の出所、Aの最初の理由、全段結果を記録し、32件中「旧理由が消えた」件数と「全段通過」件数を別集計する。取得失敗・消失・不足は除外数と理由を明示、現在のOPEN数や違う時刻の集合を当時の37と混ぜない。状態変化で再現不能なら当時のスナップショットでの再現は未実行とする。前段A/C通過まで含む実発注への増分は別測定であり、この比較から断定しない。

## 試験と変異の計画（未実施）

実装時に `.claude/skills/test-design/` の区分表を先に作成。正常系から、(1) 明示正本・完全履歴・設計・git差分ありで全項目と実adapter受渡し、(2) 正本の前身なし明示、(3) 対象パスの追加・変更・削除・未追跡とハッシュ一致、(4) 既存外部記録優先を確認。異常系は履歴取得失敗／欠落・pending／重複ID／曖昧対応／消失・git不在／不一致ハッシュ／不正JSON・書込失敗・時間切れ／codeで緑なしを分け、架空の成功値を作らず警告後に既存発注へ進むことと、既存の拒否経路が維持されることをスタブで確認。外部発注・実GitHub書込なし。パッケージ全体を実行し範囲・件数・skipを残す。

陽性対照の後、commit済み実装に対し①対象・履歴の欠落検査を削除、②同一性ハッシュを作業木全体の別レシピへ置換、③系列と前身などを入替え、④検査を常時成功に変更する各変異を試す。別種の回避として未追跡・削除の省略と、pending履歴を `none` に偽装する変異も試す。各々で (a) 不変条件を壊す差分と (b) その分岐が実行で読まれた証跡を別に残し、当該試験が赤になることを確認。緑の変異があれば完了不可。終了後に元に戻し `git diff` が空であることを確認。今回はcommit禁止なので変異は実施しない。

## 7段と見積もり

追加するものは発注用一時JSON、既存入口への生成・受渡し、試験、設計文書。㋐明示依頼と記録未供給の実例で必要。㋑ `git grep -n -E 'REVIEW_GATE_RECORD|review_gate_record' -- bin lib README.md` は2行、既存の受渡しのみ。`git grep -n -E 'REVIEW_GATE_RECORD|review_gate_record|routing_warn|content_hash|PREDECESSOR|REVIEW_TARGET' -- bin lib README.md` は55行で既存処理を確認。㋒JSON・一時ファイル・SHAは標準ライブラリ、㋓git・既存Nodeで対象同一性、㋔既存試験環境、㋕環境変数受渡し自体は1行、㋖材料の厳密な統合と欠落表現だけ最小追加。文書は㋐明示依頼・㋑既存設計を参照して作成。新サービス・永続台帳は需要が確認できず作らない。

AI Codexによる概算: 実装75分、試験45分、変異60分、合計約180分。履歴正本の欠損や技術的制約が判明した場合は増える。独立レビュー・修正依頼・反映の待ち時間は含めず別途未見積もり。

## 参照と制約

指定部品 adapter.py、route.mjs、ledger.mjs、ledger.md、routing.md、limits.json、配置報告 `.tmp/review-gate-parts-REPORT.md`、REPORT-d.md、`bin/codex-review`、`lib/routing_warn.py`、`lib/round_gate.py`、`lib/history_backfill.py` を参照。指定 `gh issue view 2006 -R min-sys/updater-index --comments` は repository を解決できず未取得。選択肢は取得待ち／手元の証拠で設計し不足を明示。今回の個別指示の既定案として後者を採用。段取り表の該当行: 無し（欄が空）。本人決定: 今回の依頼に記された 2026-11-15 13:34:12 JST の中継文、原文は未取得。見本HTML: 無し（欄が空・画面変更なし）。前身の設計と巡の履歴: 指定欄は空、代わりに routing.md と REPORT-d.md を参照。

| 環境 | 今回確認した経路・設定・データの差 |
|---|---|
| dev | 接続・読書きなし。差は未調査 |
| stg | 接続・読書きなし。差は未調査 |
| prod | 接続・読書きなし。差は未調査 |
