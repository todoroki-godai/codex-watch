# Codex と CC の作業役で受領の確認を共有する

## Codex が使えない日も、CC の作業役を起こす前に止める

`codex-impl` の受領判定を `codex-watch` の `lib/` に切り出す。Codex の起動口は従来の判定を部品に任せる。Claude Code（CC）の `Agent|Task` hook は出所行を自分で確かめ、出所が `レビュー` で始まる依頼でだけ部品を呼ぶ。実装の完了条件は、Codex CLI も認証も使えない状態で、対象作業役への依頼の出所行の書き忘れを止めること。レビュー由来の直しでは受領3行のうち1行でも欠ける依頼と、本文のどこかに `Should` がある依頼も止め、書式を満たす依頼は通す。部品が故障している間も、書式を満たした通常の依頼と対象外のレビュー役の依頼は通る。

今回の未対応は次のとおり。

- 2番目の作業で扱う実作業先の隔離。CC hook の `cwd` や依頼文に書かれたパスから、作業役が実際に書く場所を確認する処理は未対応。
- 3番目の作業で扱うレビューの発注と受け取りの照合。巡数、発注記録、返答全文と実効依頼文、対象 SHA と内容ハッシュの照合は未対応。
- 別課題の時間超過通知と、Codex の起動口にある課題番号・モデル選択などの他の判定の共有は未対応。
- 起動済みの作業役に `SendMessage` で直しを送る経路は `Agent|Task` の matcher の外にあり、残る穴になる。件数と数え方は付録に記す。

CC だけで作業する場合、CC が書いた成果物を tacchi が確認しても別系統のレビューは0本で、人間が全件承認する。別系統レビュー1巡、未解消の `[Must]` がある間の着手禁止、変異確認、人間の承認が必須の操作は現行どおり。この案の現行版に対する別系統レビューと着手判断は実装前に行う。 [工程別ルーティング](/Users/matsukaze-takashi/.claude/rules/pipeline-routing.md)・[レビューの関門](/Users/matsukaze-takashi/.claude/rules/review.md)

## CC では書き込みを頼める3種類の作業役を対象にする

`tool_name` が `Agent` または `Task` で、`tool_input.subagent_type` が `general-purpose`、`impl-worker`、`mech-worker` のいずれかと完全一致する呼び出しを対象にする。キーを省略した呼び出しも既定の `general-purpose` として扱う。対象の `tool_input.prompt` が欠落、空、文字列以外なら拒否する。元の調査ではレビュー由来と推定した起動87件の内訳が `general-purpose` 83件、`impl-worker` 3件、`mech-worker` 1件だった。今回の拡大で、旧案では素通りする84件も対象に入る。 [general-purpose の仕様](https://code.claude.com/docs/en/sub-agents#built-in-subagents)・[impl-worker の定義](/Users/matsukaze-takashi/.claude/agents/impl-worker.md:7)・[mech-worker の定義](/Users/matsukaze-takashi/.claude/agents/mech-worker.md:6)

既存 hook の `作業の種類:` と同じく、対象の依頼には行頭・字下げなし・半角コロンで `直しの出所:` を1行書く。読み取りだけを頼む場合も `直しの出所: なし` が要る。対象は役名で決まり、tacchi などのレビュー役や Explore などの調査専用役は対象外。作業種別と `impl-worker` の `Claude で実装する理由:` は既存の検査で確かめる。 [既存 hook の役割判定](/Users/matsukaze-takashi/.claude/hooks/guard-impl-worker-routing.py:84)・[作業種別の既存判定](/Users/matsukaze-takashi/.claude/hooks/guard-impl-worker-routing.py:125)・[tacchi の役割](/Users/matsukaze-takashi/.claude/agents/tacchi.md:3)・[組み込み調査役の仕様](https://code.claude.com/docs/en/sub-agents#built-in-subagents)

**① CC hook が出所行を確かめる。** 行頭の `直しの出所:` を探す。最初の出所行の値から前後の空白を取り除き、`なし` または `レビュー` で始まることだけを確かめる。この出所行の検査で止まるのは、書式どおりの出所を書き忘れた依頼（欠落・空欄・値の書式違い）。`なし` で始まる場合は、続けて出所行より後ろを Codex と同じ正規表現 `巡[0-9]|指摘を反映` 1つで調べる。該当すれば出所と受領3行の書き方を案内して止める。ここまでは hook 内で完結する。 [Codex の本文検査](../bin/codex-impl#L63)

**② 出所が `レビュー` で始まるときだけ部品を呼ぶ。** 元の本文を渡し、出所の書式、受領3行、全文の `Should` を検査する。部品が合格したときは hook が合格行の版と SHA-256 を照合する。部品の故障や合格行の不一致による停止はこの依頼に限る。

## 共通部品は元の依頼文を1回読み、止める理由を返す

`lib/receipt_gate.py` に現行の判定と、拒否理由・控えを扱う実行口を置く。判定とハッシュの入力は元の依頼文の UTF-8 バイト列。呼び出しにシェルは挟まず、本文はコマンド引数に載せない。

| 呼び出し | 入力 |
| --- | --- |
| `python3 <部品のパス> --entrypoint codex --file <依頼ファイル>` | 依頼ファイルのバイト列。 |
| `python3 <部品のパス> --entrypoint cc --stdin` | JSON から取り出した `prompt` を UTF-8 に符号化し、整形せずに標準入力へ渡す。 |

`--entrypoint` は必須で、`codex` には `--file`、`cc` には `--stdin` を組み合わせる。契約外の引数は拒否する。下表は部品に渡された依頼文の契約。`なし…` を部品で検査するのは Codex の入口だけ。

| 入力 | 判定 |
| --- | --- |
| UTF-8 として読めない、または NUL を含む | 拒否する。 |
| `直しの出所:` | 字下げなし・半角コロン・空でない値が1行必要。値は `なし` または `レビュー` で始める。 |
| 出所が `なし…` | 出所行より後ろに `巡[0-9]` または `指摘を反映` があれば拒否する。 |
| 出所が `レビュー…` | 出所や受領の行も含む全文に `Should` があれば、大文字小文字を問わず拒否する。次に `受領①累計:`・`受領②件数:`・`受領③7段:` がそれぞれ字下げなし・半角コロン・空でない値で1行あることを確かめる。 |

現行の文字列判定をそのまま移す。受領欄の内容の真偽や人間の承認は既存手順で確認する。合格時は部品が終了コード `0` と標準出力の1行 `receipt-gate v1 pass sha256=<小文字16進64桁>` を返す。行末は LF 1つ。両入口は依頼文の元のバイト列から SHA-256 を自分で求め、期待する版 `v1` とそのハッシュで組み立てた1行が、標準出力全体とバイト単位で一致したときだけ、終了コード `0` を合格として扱う。空の応答、余分な出力、版やハッシュの不一致は起動を止める。拒否、読取・記録エラー、引数不正では合格行を出さず、標準エラーに理由を出して `2` を返す。 [現行判定と拒否案内](../bin/codex-impl#L40)・[依頼文の契約](../README.md)

出所行の不足を伝える CC の拒否案内には「CC の作業役への依頼でも『直しの出所:』の1行が要ります」と書き、作業種別と並べる例を示す。レビュー由来の直しには、既存の案内と同じく出所と受領3行の例を示す。

```text
作業の種類: 判断
直しの出所: なし（新規実装）
```

**共通部品が語で止めたときは控えを残す。** Codex では `なし` と `レビュー` の両方、CC では②の `Should` が該当する。写し1件と JSONL 1行を `~/.codex-watch/receipt-gate-stops/` と `~/.codex-watch/receipt-gate-stops.log` に記録する。CC の①で本文の語に当たった場合は拒否理由を返すだけとする。写しは元のバイト列、権限 `0600`、既存ファイルの上書き不可。Codex の `time`・`prompt`・`match`・`snapshot`・`sha256` は現行どおり。CC の行は元ファイルがないので `prompt: null` とし、`entrypoint: cc` を足す。写しまたはログの保存に失敗したら依頼を拒否する。ログへの追記だけ失敗した場合、先に保存できた写しは残す。 [現行の保存形式](../bin/codex-impl#L78)

## 両入口で判定を済ませてから注意文を足す

| 入口 | 呼び出しと停止 |
| --- | --- |
| `bin/codex-impl` | 起動スクリプト自身の隣の `../lib/receipt_gate.py` を `python3` で呼び、現行のインライン判定を置き換える。依頼ファイルは既存の時点で検査し、入口でもファイルをバイト列で読んで期待する合格行を組み立てる。読取・記録・部品起動に失敗した場合や、合格行の照合に失敗した場合は起動を止める。成功時は後続の既存処理に進み、手元の試験範囲の注記を先頭、`templates/hash-check.md` を末尾に足す。 |
| CC の `guard-impl-worker-routing.py` | ①の出所行と `なし` の本文の検査は hook 内で行う。②でだけ `Path.home()` を基点に `~/matsukaze-utils/codex-watch/lib/receipt_gate.py` を絶対パスで呼び、標準入力に渡すバイト列から期待する合格行を組み立てる。対象判定後の必須処理は現行末尾の `except Exception: return 0` の外に置く。各分岐の必須チェックと役に応じた後続処理が成功した場合に限り `0` を返す。②で部品の不在・読取不能・例外・異常終了・応答の異常・タイムアウトが起きた場合は、標準エラーに原因と復旧先を出し、`2` を返す。子プロセスは既定3秒で打ち切る。 |

CC は登録済みの `PreToolUse` を使い、対象3種類の元の `prompt` を1回判定する。`impl-worker` では、通過後に試験範囲の注記を先頭、同じ `templates/hash-check.md` を末尾に足し、他の入力欄を保った `updatedInput` を返す。試験範囲は Codex の既存の1文を使い、手元で全体試験を回せる明示依頼の例外も含める。`impl-worker` ではテンプレートを読めない場合も起動を止める。承認に関わる `permissionDecision: allow` は出さない。tacchi の既存の基準追記は従来の経路で行う。 [現行の注記](../bin/codex-impl#L325)・[CC の登録](/Users/matsukaze-takashi/.claude/settings.json:90)・[Claude Code の hook 仕様](https://code.claude.com/docs/en/hooks#pretooluse-decision-control)

auto mode が `updatedInput` を受けて再発注を求めた場合、新たなツール呼び出しとして受信した本文を判定する。注記とテンプレートがすでに同じ先頭・末尾にあれば追記を省く。初回も再発注も、②に進んだ場合は受信本文をそのまま部品に渡す。 [auto mode の再発注仕様](https://code.claude.com/docs/en/hooks#pretooluse-updatedinput-in-auto-mode)

## 巻き添えと故障時の停止を限定し、差分を戻せるようにする

1. **書き忘れと本文の語で止まる依頼。** 対象572件のうち、レビュー由来と推定した87件を除く通常依頼485件は、①で出所行の書き忘れとして止まる見込み。うち実装・編集は推定387件で、`impl-worker` は40件中37件。485件のうち36件（実装・編集では33件）は、先頭に `直しの出所: なし` を足しても本文の語で止まる。②では `Should 0件` などの記載や指摘の引用に `Should` が含まれる場合も止まる。拒否理由と書き方を返し、CC への反映初日に周知する。数え方と内訳は付録を参照。
2. **部品が壊れたとき。** CC で部品の故障や合格行の照合失敗で止まるのは②の依頼だけ。①は hook 内の文字列確認で済むので、故障中も出所が `なし` の有効な依頼と対象外のレビュー役の依頼は通る。対象の本文の不備や注記の追記・出力時の例外は hook 側で止める。外側の JSON が壊れて対象を識別できない入力は既存の扱いを維持する。hook 自体の起動は初回反映時に実セッションで確認する。 [現行の例外処理](/Users/matsukaze-takashi/.claude/hooks/guard-impl-worker-routing.py:277)・[Claude Code の終了コード仕様](https://code.claude.com/docs/en/hooks#exit-code-2)
3. **配布と戻す差分。** 先に `codex-watch` の部品と起動口を同じ版で反映し、次に CC の hook と受領ルールを反映する。CC 側を先に入れた場合や部品を先に取り除いた場合、CC では②の依頼が部品不在で止まる。両方を戻すときは、CC の①の出所・本文検査、②の部品接続・照合、注記の追記、受領ルールと関連試験を先に戻す。次に Codex の抽出差分を戻し、元のインライン判定を復元する。停止記録は残す。

部品の置き場は既存の絶対パス規約に合わせる。設定可能な探索先、作業ディレクトリからの探索、hook 側へのコピーも選択肢だが、既定は固定した正本1箇所。Codex CLI や認証への依存も増えない。後で部品を更新するときは既存の両入口が使う引数・入力・終了コード・合格行の契約を保つ。契約の版を変える場合は両入口が期待する版も合わせて更新する。

## 両方の実入口で拒否と通過を観測し、変異で検査を確かめる

| 検査 | 実装時に確かめること |
| --- | --- |
| 共通部品 | 出所の欠落・重複・不正値、受領各行の欠落・空欄・重複、`なし…` の後ろにある既存の検査語、レビュー由来の全文にある `Should` の大小文字と位置を固定する。正当な新規依頼、3行付きの直し、CRLF で通過する。 |
| Codex の実入口 | `tests/test_codex_impl_receipt.py` の陰性・陽性対照・変異の全ケースを維持する。試験の一時領域には `bin/codex-impl` と `lib/receipt_gate.py` を本番と同じ相対位置に写す。実物の起動スクリプトを使い、受領判定後の既存の目印で止めて CLI・認証に進ませない。依頼文・控え・記録の保存条件と、部品や Python の故障時に後続へ進まないことを検査する。インラインの既存変異は移動先に当てる。 |
| CC の実入口 | 既存 `test_guard_impl_worker_routing.py` から実物の hook に JSON を流す。`Agent` と `Task` で、`general-purpose`（明示・省略）、`impl-worker`、`mech-worker` のそれぞれに出所行が必要なことを確かめる。対象に合った実装理由・作業種別・終端チェックを満たし、①では出所行の欠落・空欄・不正値と `なし` の出所行より後ろにある検査語を個別に試す。②では受領各行の欠落と `Should` を試す。拒否は `2`・`updatedInput` なし。有効な直しと新規依頼は `0` で、`impl-worker` の場合は受信本文を保った入力に注記が1回だけ付く。対象の本文の欠落・空文字・非文字列・孤立サロゲートも拒否し、既存試験で非文字列の `impl-worker` を通していた期待値は拒否に更新する。 |
| 部品故障時の陽性対照 | 部品の不在・読取不能・例外・タイムアウト・保存失敗で②の依頼が止まることを確認する。部品を取り除いた場合と異常終了する部品に差し替えた場合に、①の `直しの出所: なし` を持つ有効な依頼と、出所行がなく検査語を含む tacchi の正当なレビュー依頼が、既存の必須チェックを満たせばともに `0` で通ることを確かめる。 |
| 合格行の照合 | 両入口（CC は②）で部品を、空のスクリプト、`main` を定義して呼ばないスクリプト、別入力のハッシュを返すスクリプトにそれぞれ差し替え、終了コード `0` でも拒否することを確かめる。版の不一致と余分な標準出力も拒否し、実物の部品が返す正しい版と本文のハッシュで後続へ進むことを確認する。 |
| 変異と対照 | 一時領域の実装コピーで、受領1行を免除する変異と `Should` を見逃す変異を当て、両入口の拒否試験がそれぞれ赤になり、正当な依頼は緑のままと確かめる。両入口で終了コード `0` だけで通す変異を当て、合格行の異常を拒否する試験が赤になることを確かめる。変えた箇所の一意性と差分を確認し、変異箇所に置いた目印が実入口の実行で出たことを別の証跡で確かめる。変異を外して元の検査を再実行し、緑に戻す。 |

同じ依頼を両入口へ流すケースでは、拒否理由と入口ごとの控えの件数を確かめる。CC の①は拒否理由のみ、共通部品が語で止めた場合は写しとログを1件ずつ確認する。原本と写しの一致は、同じ順で並べた SHA-256 と件数で比較し、不一致時だけ本文を開く。CC の試験は一時 HOME に `matsukaze-utils/codex-watch` を再現して実物の部品を置く。Codex CLI の入らない状態でも拒否と通過を検査でき、普段の hook やログを汚さない。既存の実依頼由来の Codex 試験素材を残し、CC 側も反映前に持ち出し可能な実依頼で dry-run する。反映後は実セッションで Codex CLI・認証なしの拒否2件と通過1件を確認する。実際の Agent 起動可否はこの段階で確定する。

手元は変更したファイルと近傍の試験、依存先込みの lint・型検査まで。パッケージ・リポジトリ全体の試験は、依頼で明示された場合を除き、頭が AWS で回す。今回は設計段階のため、上記の動作と変異は未実施。

## 既存の判定と hook を再利用し、接続だけ足す

| 仕組み | 足りた段 |
| --- | --- |
| 出所・受領・検査語の判定、拒否案内、写しとログ | ㋑。`bin/codex-impl` の判定と記録処理を移し、既存の Codex の試験ケースも使う。 |
| ①の対象選択と出所行の検査 | ㋑。hook の役名の完全一致と `作業の種類:` の必須行の扱いを再利用し、出所の値の先頭を確かめる。 |
| ①の `なし` の本文検査 | ㋑。`bin/codex-impl` と同じ正規表現1つを、hook の既存の `re` で出所行より後ろに当てる。hook に保存処理を足す案は㋐で止める。 |
| 引数、標準入力、SHA-256、CC の子プロセス起動と時間制限 | ㋒。Python 標準ライブラリの `argparse`、入出力、既存判定でも使う `hashlib`、`subprocess.run` で足りる。 |
| 合格の合図 | ㋕。版と SHA-256 を固定書式の1行に載せ、入口で組み立てた1行と比較する。 |
| CC の起動前の拒否・入力更新 | ㋓。登録済みの同期 `PreToolUse` と既存 hook の終了コード・`updatedInput` を使う。 |
| 注意文 | ハッシュ照合は㋑の既存テンプレート。試験範囲は㋕で既存の1文を同じ形で足し、専用の文面生成器を設けない。 |
| 実測と試験の器 | ㋒。付録の集計は標準ライブラリで元の記録を読む。部品を呼ぶ見込みは㋑の既存の役別集計で求める。故障時の陽性対照は㋑の実入口試験に加え、同じ一時領域で部品の不在・差し替えを作る。 |
| 受領ルールの旧文の置き換え | ㋕。既存の対象外の記述を1文で更新する。 |
| ②の部品呼び出しと失敗時の拒否 | ㋖。①の値が `レビュー` で始まるときだけ既存の部品呼び出しの設計へ進む。元の本文を渡し、実行・照合失敗を `2` にする最小の接続コードが要る。 |
| 共通起動コマンド・別の巡数処理・探索設定 | ㋐。今回の完了条件には要らない。 |

## 実装時に変更するファイル

| 管理先 | ファイル | 変更 |
| --- | --- | --- |
| `codex-watch` | `lib/receipt_gate.py`（新規） | 共通判定・拒否案内・停止記録と、ファイル／標準入力の実行口。 |
| `codex-watch` | `bin/codex-impl` | インライン判定を共通部品の呼び出しに置換。 |
| `codex-watch` | `tests/test_receipt_gate.py`（新規）、`tests/test_codex_impl_receipt.py` | 共通部品の検査、既存の実入口試験と変異の移設。 |
| `codex-watch` | `README.md` | 配布順と控えの CC 行の形式を記載。 |
| `~/.claude` | `hooks/guard-impl-worker-routing.py`、`hooks/tests/test_guard_impl_worker_routing.py` | CC の対象分岐、hook 内の検査、レビュー由来だけの部品呼び出しと照合、注記の追記と実入口の検査。 |
| `~/.claude` | `rules/review-receipt.md` | hook と同じ変更で、行2末尾の「作業役（Agent）・SendMessage への依頼は対象外」を下記の文に置き換える。 |

> CC の Agent／Task で新規に起こす general-purpose（役名を省略した場合を含む）・impl-worker・mech-worker には出所行を必須とし、出所が「レビュー」で始まるときだけ受領3行を確かめる。tacchi などのレビュー役と SendMessage での依頼は対象外とする。

hook の登録は既存の `settings.json` を使う。`templates/hash-check.md` は既存の内容を使う。設計の基点は `codex-watch` の `8ad688d` と、手元の CC hook（2026-11-25 確認）。

## 付録　元の会話記録で数えた初回停止と SendMessage

集計期間は 2026-10-26 00:00 以上、2026-11-26 00:00 未満（JST）。2026-11-25 19:32:57 JST に取得した。Agent／Task は `harness-nudge` の `6ce9e9f` にある `docs/research/cc-agent-delegations-20261125.jsonl` を索引にし、1行を1起動として `file_path` と `line_number` から元の `tool_use.input.prompt` を引いた。1,105行すべてで日時と役名が一致した。

| 起動時の役名 | 対象件数 | レビュー由来（推定） | 初回に止まる通常依頼（推定） | うち実装・編集（推定） | 「なし」を先頭に足しても停止（通常依頼／うち実装・編集） |
| --- | ---: | ---: | ---: | ---: | ---: |
| `general-purpose` | 457 | 83 | 374 | 281 | 18／15 |
| 役名省略（既定の `general-purpose`） | 16 | 0 | 16 | 11 | 0／0 |
| `impl-worker` | 40 | 3 | 37 | 37 | 5／5 |
| `mech-worker` | 59 | 1 | 58 | 58 | 13／13 |
| 計 | 572 | 87 | 485 | 387 | 36／33 |

新しい受領判定を元の依頼文に読み取り専用で当てたところ、対象572件すべてに行頭の出所行がなかった。正当な通常依頼の概数には、索引が「レビュー由来の直し」に分類した87件を除く485件を使った。実装・編集の387件は、索引の「実装・編集」と「実装・編集（推定）」の合計。どちらも索引の語と役名による推定で、各依頼の正当性を個別に認定した数ではない。「なし」を先頭に足しても停止する件数は、元の本文全体に `巡[0-9]|指摘を反映` がある通常依頼を数えた。実際の hook 起動や出し直し回数はこの集計に含まない。

**②で部品を呼ぶ見込みは572件中87件。** 上表の「レビュー由来（推定）」を役名別に足した（83＋0＋3＋1）。索引の「レビュー由来の直し」と分類された起動に `直しの出所: レビュー…` を1行付けて出した場合の推定であり、部品を呼んだ実績や照合に合格する件数は含まない。取得時の本文のままなら、対象572件すべてが①で止まるため、部品に届くのは0件。

**残る穴は、SendMessage での直しと推定した66件。** 同じ期間の通常セッションとサブエージェントの会話記録から、`tool_use.id` で重複を除いた SendMessage の呼び出し10,272件を集めた。同一プロジェクト・同一セッションの先行する Agent／Task の結果の `agentId` または起動時の `name` に宛先が一致し、役名が一意に決まったものを集計した。対象作業役宛て319件のうち、本文に `受領|巡[0-9]|Must`（大小文字を区別しない）がある66件（`general-purpose` 62件、`impl-worker` 4件、`mech-worker` 0件）を数えた。語による推定なので、直しの指示と報告・確認の区別や配信成否までは確定していない。宛先を判定できなかった本文ありの9,691件（うち検査語あり3,948件）と本文なしの1件は、66件に含めていない。

取得時の SHA-256 は、索引が `aa2fecc756330a1fa281edfb559d593fa9d178d98ee8353ac10bedee5fb2e24e`、元の起動入力1,105件が `10bf2f55d1f5f28253f7b910d8726e80dabcab680aa843fcb28269cd686fece2`、SendMessage の入力10,272件が `c3d75becc01f64a0e7aedbf5a47a2a20a4c36553b91139e5c103ecd261a96d7a`。後ろの2つは、下記の順序と書式で入力を要約した。会話記録が増えた場合は件数とハッシュが変わり得る。

### 集計に使った読み取り専用のスクリプト

下のコードを `python3 -I -` の標準入力に渡すと、件数とハッシュを再集計できる。

```python
import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

home = Path.home()
jst = ZoneInfo("Asia/Tokyo")
start = datetime(2026, 10, 26, tzinfo=jst)
end = datetime(2026, 11, 26, tzinfo=jst)
roles = {"general-purpose", "impl-worker", "mech-worker"}
index = subprocess.check_output([
    "git", "-C", str(home / "matsukaze-utils/harness-nudge"), "show",
    "6ce9e9f093c6575c4cacbd8965e3f4895ba92705:docs/research/cc-agent-delegations-20261125.jsonl",
])
indexed = {(Path(r["file_path"]), r["line_number"]): r
           for r in map(json.loads, index.splitlines())}
assert len(indexed) == len(index.splitlines())
projects = home / ".claude/projects"
paths = sorted(set(projects.glob("*/*.jsonl")) |
               set(projects.glob("*/*/subagents/*.jsonl")))
paths = sorted(set(paths) | {p for p, _ in indexed})
fields = ("直しの出所", "受領①累計", "受領②件数", "受領③7段")
review_words = re.compile(r"巡[0-9]|指摘を反映")
message_words = re.compile(r"受領|巡[0-9]|Must", re.I)


def profile(prompt):
    try:
        prompt.encode("utf-8")
    except UnicodeError:
        return "読取不可"
    if not prompt or "\0" in prompt:
        return "読取不可"
    lines = prompt.splitlines()
    values = [[line[len(key)+1:].strip() for line in lines
               if line.startswith(key + ":")] for key in fields]
    source, *receipt = values
    if not source:
        return "出所なし"
    if len(source) != 1 or not source[0].startswith(("なし", "レビュー")):
        return "出所不正"
    if source[0].startswith("なし"):
        line_no = next(i for i, line in enumerate(lines) if line.startswith(fields[0] + ":"))
        return "検査語" if review_words.search("\n".join(lines[line_no+1:])) else "通過"
    if re.search("Should", prompt, re.I) or any(len(v) != 1 or not v[0] for v in receipt):
        return "レビュー書式"
    return "通過"


def update_digest(digest, row):
    digest.update(json.dumps(row, ensure_ascii=True, separators=(",", ":")).encode() + b"\n")


spawns, results, sends = {}, {}, {}
agent_counts = Counter()
agent_hash, send_hash = hashlib.sha256(), hashlib.sha256()
read_index = set()
for path in paths:
    project = path.relative_to(projects).parts[0]
    with path.open("rb") as stream:
        for line_no, raw in enumerate(stream, 1):
            key = path, line_no
            row = indexed.get(key)
            if row is None and not any(w in raw for w in (b'"Agent"', b'"Task"', b'"SendMessage"', b'"agentId"')):
                continue
            try:
                record = json.loads(raw)
            except (ValueError, UnicodeError):
                continue
            msg = record.get("message") or {}
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            session = record.get("sessionId")
            stamp = record.get("timestamp", "")
            result = record.get("toolUseResult")
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "tool_result" and isinstance(result, dict):
                    agent_id = result.get("agentId")
                    if isinstance(agent_id, str):
                        results[item["tool_use_id"]] = agent_id
                if record.get("type") != "assistant" or item.get("type") != "tool_use":
                    continue
                name, tool_id = item.get("name"), item.get("id")
                data = item.get("input")
                if not isinstance(data, dict) or not isinstance(tool_id, str):
                    continue
                if name in {"Agent", "Task"}:
                    role = data.get("subagent_type", "general-purpose")
                    spawns.setdefault(tool_id, (project, session, stamp, data.get("name"), role))
                    if row is not None:
                        assert key not in read_index
                        read_index.add(key)
                        expected = data.get("subagent_type", "general-purpose(既定)")
                        assert (expected, stamp) == (row["subagent_type"], row["timestamp"])
                        prompt = data["prompt"]
                        update_digest(agent_hash, (row["file_path"], line_no, tool_id, prompt))
                        if role in roles:
                            agent_counts[expected, row["role"], profile(prompt),
                                         bool(review_words.search(prompt))] += 1
                if name == "SendMessage":
                    when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                    if start <= when < end:
                        dest = data.get("to") or data.get("recipient")
                        body = data.get("message") or data.get("content")
                        sends.setdefault(tool_id, (project, session, stamp, dest, body))
assert read_index == indexed.keys()

aliases = defaultdict(list)
for tool_id, (project, session, stamp, alias, role) in spawns.items():
    for dest in (results.get(tool_id), alias):
        if isinstance(dest, str):
            aliases[project, session, dest].append((stamp, role))

send_counts = Counter()
for tool_id, (project, session, stamp, dest, body) in sorted(sends.items()):
    update_digest(send_hash, (tool_id, project, session, stamp, dest, body))
    if not isinstance(dest, str) or not isinstance(body, str) or not body:
        continue
    candidates = {role for spawned_at, role in aliases[project, session, dest]
                  if spawned_at <= stamp}
    role = next(iter(candidates)) if len(candidates) == 1 else "宛先未確定"
    send_counts[role, bool(message_words.search(body))] += 1

print(datetime.now(jst).isoformat(timespec="seconds"))
print("index", len(indexed), hashlib.sha256(index).hexdigest())
print("Agent/Task", len(read_index), agent_hash.hexdigest())
for row, count in sorted(agent_counts.items()):
    print(*row, count)
print("SendMessage", len(sends), send_hash.hexdigest())
for row, count in sorted(send_counts.items()):
    print(*row, count)
```
