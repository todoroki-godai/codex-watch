# D 警告接続の入力区分（試験作成前）
出所: 本人の今回の依頼1〜6（2026-11-15）。実装由来の期待は置かない。

| 入力 | 区分・境目 | 置く値 | 期待 | 期待の出所 | 試験の大きさ | 試験名 |
|---|---|---|---|---|---|---|
| 正常発注 | 通し | 全段true・exit0 | fake発注成功、警告1行、JSONL1行、ID一致 | 依頼1・3 | CLI通し | test_dispatch_outcomes[pass] |
| 判定 | 止めるはず | A/1/2/3/B停止・exit1 | 発注成功、段と理由分類を保存 | 同上 | CLI通し | test_dispatch_outcomes[block*] |
| 実行 | 異常終了 | exit7、成功JSON＋exit7、未捕捉例外 | 発注成功、処理失敗を記録 | 依頼1②・3 | CLI/関数 | test_dispatch_outcomes[error*], test_internal_failure |
| 出力 | 型・欠け | 空/壊れたJSON/null/配列/数値bool/段欠落/矛盾/65535・65536・65537 bytes | 発注成功、出力不正を記録 | 信頼境界・依頼3 | CLI/関数 | test_dispatch_outcomes[invalid*], test_invalid_outputs, test_output_size_boundary |
| 部品 | 不在・空 | 指定なし/不存在/ディレクトリ | 発注成功、部品なし | 依頼2・3 | CLI/関数 | test_dispatch_outcomes[missing], test_missing_adapter |
| 記録引数 | 欠落・空 | REVIEW_GATE_RECORD未設定/空白/日本語空白パス | 必須展開で止めずadapterへそのまま渡す | 依頼1②・2 | CLI通し | test_record_arguments |
| 締切 | 未満/等号/超過 | 29.999/30/30.001秒（単調時計）、実30秒 | 等号以上で時間切れ、発注成功 | 依頼1③ | 関数・実時間CLI | test_deadline_boundary, test_dispatch_timeout, test_detached_worker_cleanup |
| 子プロセス | 孫が継続 | adapter終了後も同groupの孫が待つ | 締切時にgroupを打切る | 依頼1③ | 実時間CLI | test_dispatch_timeout, test_detached_worker_cleanup |
| 継ぎ目 | 対象・種別・発注ID | updater以外、設計/コード | 入力と記録が一致、終了状態不変 | 依頼1⑤・2 | CLI通し | test_dispatch_outcomes, test_record_arguments |
| 文字・秘密 | エラー出力/JSON内の秘密・改行 | 合成の秘密、改行・制御字、未知の理由 | stderr1行、本文や生理由を保存しない | 依頼1④⑤ | CLI/関数 | test_dispatch_outcomes, test_invalid_outputs, test_output_size_boundary |
| 記録 | 既存行/並列/書込不能 | 既存1行、同時発注、JSONLがディレクトリ | 追記して保持、書込不能も発注継続し警告 | 依頼1①⑤ | CLI/関数 | test_append_and_write_failure, test_concurrent_append |
| 予約・既存ゲート | 公開前再照合/既存拒否 | reservation既存、前段exit4 | 予約不変、前段拒否では警告処理を呼ばない | 依頼1挿入位置 | CLI通し | test_prerelease_order, test_existing_gate_rejection |

数字・継ぎ目・時刻・できない操作・文字と欠け・合図の6問を適用。時刻はUTC timezone付き、試験は前後時刻で挟んで検証。発注完了は固定sleepではなくstate/同期stubの証跡で確認。環境dev/stg/prod・DB・実LLMは対象外、すべて一時stateとfake sender。

変異計画: ①停止結果の伝播 ②実行失敗の伝播 ③追記削除 ④締切削除。別種の回避はboolを数値1へ、対象と種別の入替、stderrへの生出力漏出。陽性は意味のないコメント変更。各変異に差分と実行markerを別logで残し、元バイト列へ復元する。今回commitは禁止なのでcommit済み起点の条件は未充足と明記し、HEADと固定した未commit版のSHA256で代替する。

既存adapterの別session workerの後始末: 締切でSIGINTを渡し最大0.2秒待つ。模した監督部品で別session workerのFIFOがEOFになることを検証し、割込みを無効にする変異09で赤を確認する。

## fix1 入力区分（試験作成前、出所: 今回の作業1〜5・レビュー3件）
| 入力 | 区分・境目 | 値 | 期待 | 出所 | 大きさ | 試験 |
|---|---|---|---|---|---|---|
| 警告全体 | 正常通し | 正常adapter・通常ファイル・通常stderr | 記録後fake本体起動 | Must① | CLI | test_dispatch_outcomes[pass] |
| 記録待ち | open待ち/write待ち | 読者なしFIFO/満杯FIFO | 外側31秒制限で本体へ進む | Must① | CLI | test_blocked_dispatch |
| 通知待ち | stderr待ち | 満杯pipe | 外側31秒制限で本体へ進む | Must① | CLI | test_blocked_dispatch |
| 締切 | 未満/等号/超過 | 既存29.999/30/30.001 | 既存判定の境界保持 | Must① | 関数 | test_deadline_boundary |
| SIGINT | 通常→無視継承 | 既定/IGN | timeout後別session workerのFIFOがEOF | Must② | プロセス | test_detached_worker_cleanup |
| 追記 | 正常→短いwrite | 全量/初回12byte/毎回1byte/0byte | 2記録が解析可・0は記録失敗 | Must③ | 関数 | test_short_write |
| 集計 | 正常→破損混在 | 正常JSON/途中JSON/空行/不正schema | 正常分を計数・破損行数を表示 | Must③ | README実行 | test_readme_aggregation |

数字・継ぎ目・時刻・できない操作・文字・合図を適用。実時間の上限は既存30秒判定＋終了猶予を覆う31秒（終了回収最大0.2秒）。外側には外部timeoutコマンドを使わない。時刻・対象・秘密の既存試験を保持。実LLM/DB/環境接続なし。正常系を先に置く。変異: 外側制限除去、SIGINT復元除去、短write処理除去、期限弱化、値入替、試験無効化＋独立検査、別種回避=0byte無限ループと壊れた行の早期終了。陽性はコメント/正常データ。未commit固定SHA256で実施し差分・実行行を別logへ残す。
