# 受け取り済みレビューの履歴：設計と見積もり

対象: `32e272d0fa4fd223879299c56e13c879ac080a23`。設計のみ、実装・レビュー・実発注は未実施。

## 定義

受け取り済みの履歴は、同じ正本・系列と種別に属する過去の巡について、正本の巡行と一意に対応する発注を、結果 `.report` が存在し、その2・3行目の `read_sha` と `content_hash` が発注時 `.state` と `check_receipt` で一致し、さらに正本の巡の履歴にその発注の受領行がある場合に、巡単位で `received` として渡す時系列である。複数レビュアーの同一巡は全員の受領を確認し、指摘族を和集合にする。結論・Must 件数は正本の受領行で参照しても、route の必須項目ではなく、未確認の値は作らない。受領行の構文と指摘族・対象別ハッシュの正本は統一されていないため、以下の構造化行を暫定案とする。意味が覆ればこの節と入力契約・試験区分を差し替える。曖昧な自由文の推測はしない。

## 最小案と入力契約

既存 `history()` / `backfill()` の巡・state の一対一対応と `round_gate.check_receipt()` を再利用し、既存の一時 JSON の `history` を充実させる。正本の「巡の履歴」内に受領担当が発注ごとに次の独立した構造化行を記載する暫定案（実装時に厳密な JSON として解析、重複や構文不正は欠落）。入力は申告であり認証ではない。

```text
routing-receipt: {"dispatch_id":"発注ID","status":"received","finding_family_tags":["族またはnone"],"route_content_hash":"発注時の対象別SHA-256"}
```

| 記録項目 | 出所・条件 | 不足・競合 |
|---|---|---|
| `event_id`, `family_tags`, `target_sha` | 既存の正本巡行と state の一対一照合、同一巡の族和集合 | 曖昧・重複・SHA 不一致は巡を missing にする |
| `status` | 上記対応に加え report・state の既存受領照合成功と、その ID に一意な受領行。複数人は全員成功 | 未受領・欠落・不一致は pending／missing。report の存在だけでは不可 |
| `finding_family_tags` | 対応する受領行の明示配列、複数人は和集合。`none` は明示された指摘なしの場合のみ | 未記載・空・不正は欠落。結論や Must 件数から推測しない |
| `content_hash` | 受領行に明示された、**当該発注時**の route `contentIdentity` の対象別ハッシュ。複数人は同値の場合のみ | 不明・不一致は欠落。state の作業木全体ハッシュを流用しない。現時点の作業木から過去値を再計算しない |

発注時の route 対象別ハッシュを記録する既存永続先は確認できていない。将来の発注では既存の自動生成記録の `current.content_hash` を発注時の控えとして既存 state に明示的な別名で保存し、受領行の値と一致確認する案とする。既存の外部 `REVIEW_GATE_RECORD` 優先・生成失敗時の警告動作を維持し、控えが取れない過去巡は欠落のまま。対象別ハッシュは状態変更前に固定し、生成値と実際の控えが同一であること、時間制限・書込失敗を検証する。既存の受領照合用 `content_hash` とは別名・別レシピとする。新たな台帳は作らない。受領行が別の発注に紐づく、または全員の対象 SHA／対象別ハッシュが異なる巡は received に束ねない。巡数・予約・Must・別系統レビューなど既存関門と、観測だけの routing 警告は変更しない。

## 完成条件 round 0

- 守る対象: 実際に受領された巡だけを証拠どおりに渡し、欠落巡を隠さず、既存関門を維持する。
- 信頼境界: 正本の申告と report は信頼できる認証情報ではない。state・正本・report の一意な照合と構文検査を行い、本文・資格情報をログへ出さない。既知の一時記録パス差し替えの限界は #45 の裁定の範囲。
- 対象外: route の仕様変更、実発注・実 GitHub 書込、新台帳、結論や族の自動推測、過去の欠落証拠の捏造。
- blocking: 受領の誤認、異なるハッシュの混用、欠落の隠蔽、既存関門の緩和、情報漏洩、変異の生存。
- 検証: 固定フィクスチャで契約と受渡しを確認し、パッケージ全体・変異確認を実施する。実環境の改善件数は別に測り、模擬結果と混同しない。

## 試験計画（未実施）

実装時は `.claude/skills/test-design/` を探して入力区分表を先に作る（この作業場所の同パスには存在しない）。正常系先行: 一巡全証拠一致、複数人全一致と指摘族の和、明示 `none`、将来の発注時控えから受領まで、既存外部記録優先。異常系: report 無し・空・形式ずれ・SHA／作業木ハッシュ不一致、受領行無し／重複／別ID、不正族、対象別ハッシュ未保存・不一致、正本取得失敗、並列巡の部分受領、旧state、時限・書込失敗、未追跡差分。欠落・pending と既存関門維持を確認する。

陽性対照を通し、commit 済み実装に対して①受領行確認を削除、②別レシピの state ハッシュを route ハッシュに流用、③発注 ID の受領行を入れ替え、④照合を常時成功にする各変異を赤にする。別種の回避として複数人の一部だけ成功で巡を受領扱い、欠落族を `none` に置換する変異も試す。それぞれ不変条件を壊す差分と実行で分岐を読んだ証跡を別々に残し、終了後 `git diff` が空であることを確認。パッケージ全体の範囲・件数・skip を記録し、生存変異があれば完了しない。

## 見積もりと7日間の観測

実装の中心 **240分（幅180〜360分）**。内訳は実装90分、試験65分、変異・証跡70分、統合確認15分。独立レビューとその待ち時間は別。受領行の運用や過去の対象別ハッシュ欠落によって幅が広がる。

2026-11-15 23:59:23 JST を上限とする直近168時間の `~/.codex-watch/routing-warn.jsonl` は16行・16 dispatch、`missing` 8件、`would_block` 8件（全て A）。理由は部品なし6件、部品なし＋対象同一性未取得2件、その他＋対象同一性未取得5件、その他＋履歴照合失敗＋対象同一性未取得3件。**この設計で received を渡せ、停止相当が変わる件数は不明**。ログは理由を分類・集約し生成記録や当時の正本を保存しないため pending が原因か、全受領証拠が揃うか、他の不足が解消するかは判別できない。部品なし8件は本設計だけでは部品なしが解消しない。0件と断定しない。ログに残らなかった発注や将来の実効果も数えていない。

再集計（境界は固定、値を出力せず集計）:

```sh
python3 - <<'PY'
import collections, datetime, json, pathlib
end = datetime.datetime.fromisoformat('2026-11-15T23:59:23+09:00')
start = end - datetime.timedelta(days=7)
rows = [json.loads(s) for s in (pathlib.Path.home()/'.codex-watch/routing-warn.jsonl').open()]
rows = [r for r in rows if start <= datetime.datetime.fromisoformat(r['time'].replace('Z','+00:00')) <= end]
print('rows', len(rows), 'dispatches', len({r['dispatch_id'] for r in rows}))
for k in ('verdict', 'stopped_at', 'reasons'):
    print(k, dict(collections.Counter(str(r[k]) for r in rows)))
PY
```

個別件数の確定には、各 dispatch の当時の正本・生成記録・state・report・発注時 route 対象別ハッシュを固定し、受領照合と旧／新の同条件再判定が必要。入手不能分は未判定として数える。

## 7段と再利用

書く前に `git grep -n -E 'received|finding_family_tags|content_hash|history\(' -- lib bin | wc -l` は44行、`git grep -n -E 'check_receipt|parse_receipt_claim|history\(|backfill\(|contentIdentity|finding_family_tags' -- lib bin | wc -l` は17行。既存の記録・照合・同一性を再利用する。

| 追加対象 | 7段の到達点 |
|---|---|
| `status` 受領判定 | ㋐明示依頼、㋑既存 `check_receipt` と履歴照合を再利用、㋒標準ライブラリ、㋓既存 git、㋔既存依存、㋕1行では複数証拠の一意照合不可、㋖最小統合 |
| `finding_family_tags` | ㋐route 必須、㋑既存タグ処理を再利用、㋒JSON、㋓㋔追加不要、㋕1行では複数受領の検証・和を保証不可、㋖最小解析 |
| 過去 `content_hash` と発注時別名控え | ㋐route 必須で別レシピを区別、㋑既存 `contentIdentity` と state 保存を再利用、㋒JSON、㋓git、㋔追加不要、㋕1行では取得・保存失敗と一致を扱えず、㋖最小配線 |
| 構造化受領行 | ㋐受領と族の明示に必要、㋑既存正本・構造化入力を再利用、㋒JSON、㋓㋔追加不要、㋕照合は1行では不足、㋖最小契約 |
| 試験・設計文書 | ㋐明示依頼、㋑既存試験・本設計を再利用し不足部分だけ追加、㋖。新依存・新台帳は不要 |

## 資料と環境

- 段取り表の該当行: 無し（指定欄が空）。本人決定: 今回提示された 2026-11-15 23:48 受領の中継と補足。見本 HTML: 無し（指定欄が空、画面変更なし）。
- 前身: `gh issue view 45 -R todoroki-godai/codex-watch`、`docs/design/routing-record.md` と `docs/design/routing-record-REPORT.md`。#2006 は指定 `gh issue view` が repository を解決できず、今回提示された本文を読んだ。
- `bin/codex-review`、`lib/routing_record.py`、`lib/routing_warn.py`、`lib/round_gate.py`、`lib/history_backfill.py`、振り分け部品の `route.mjs`・`routing.md`、ローカル警告ログ。巡の履歴は #45 の本文と既存コードの書式を確認。

| 環境 | 経路・設定・データの違い |
|---|---|
| ローカル | `~/.codex-watch` は読取のみ。adapter は既定で `~/.claude/skills/review-gate/adapter.py`、環境変数で変更可能。 |
| dev | 接続なし、違い未調査。 |
| stg | 接続なし、違い未調査。 |
| prod | 接続なし、違い未調査。 |
