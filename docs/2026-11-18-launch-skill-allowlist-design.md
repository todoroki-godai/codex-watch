**結論　`codex-impl` と `codex-review` で毎回、置き場から `SKILL.md` を直接数え、許可リストにないものを起動引数で無効にする。既存の記憶の差し込みも切る。**<br>
**初期値は利用記録のある11件。依頼ごとに追加でき、元の設定でも起動できる。本人が開く Codex と Claude Code は今までどおり使える。**<br>
**実測では両方を外して初回入力が37,316から25,703トークン（＝かんたんに言うと、AIに渡す情報の量）へ約31%減った。本書は設計で、この方式の実起動は実装後に確認する。**

# 起動口で使う skill と記憶を絞る設計

2026-11-18。対象は起動口（＝かんたんに言うと、実装・レビューを別の Codex に発注するコマンド）から作る新規セッション。skill は Codex が必要に応じて読む作業手順。記憶は Codex が過去のセッションからまとめた情報で、今回切るのは新規セッションへの自動差し込み。必要な背景や根拠は依頼文に添える。既存記憶の保存と生成は現在の設定に従う。

## 測定済みの効果

2026-11-18 09:47〜09:53 JST、CLI 0.169.1 と同じ作業場所・モデルで「OK と返すだけ」を各3回。保存済みの会話記録から最初の要求の `input_tokens` を再集計した。キャッシュ（＝かんたんに言うと、以前処理した入力の再利用）で変わる画面の `tokens used` とは分けて比較する。［[測定データ](../../../../harness-nudge/_wt.noindex/startup-weight/docs/experiments/data/turns-20261118-094716-390716/)・[集計スクリプト](../../../../harness-nudge/_wt.noindex/startup-weight/docs/experiments/scripts/codex-startup-turns.py)］

| 条件 | 初回入力（3回） | 基準からの減少 | skill 掲載数 | 記憶の差し込み |
| --- | ---: | ---: | ---: | ---: |
| 基準 | 37,316／37,316／37,316 | — | 312 | 1 |
| skill を絞る | 29,757／29,733／29,757 | 7,559〜7,583 | 29 | 1 |
| 記憶を切る | 33,267／33,267／33,267 | 4,049 | 312 | 0 |
| 両方 | 25,703／25,703／25,703 | 11,613（31.1%） | 29 | 0 |

harness-nudge の試験では、保存した一覧の284件を `SKILL.md` の絶対パスと `enabled = false` の組で一時設定の `[[skills.config]]` に指定した。掲載は312件から29件、初回入力は37,316から29,757トークン（3回中2回）に減った。指定数と掲載減少数の差は個別に特定していない。この試験はパスによる無効化の根拠になる。今回の直接列挙と `-c` を組み合わせた起動、初期11件の掲載結果、列挙時間は実装後に確認する。［[使用したパス一覧](../../../../harness-nudge/_wt.noindex/startup-weight/docs/experiments/data/unused-skills-20261118.txt)・[計測手順](../../../../harness-nudge/_wt.noindex/startup-weight/docs/experiments/scripts/codex-startup-weight.sh)］

## 残す11件と発注時の指定

初期値を起動口のリポジトリの `templates/codex-skills-allowlist.tsv` に置く。1行1件で掲載名と提供元の識別子を持つ。起動するプロジェクトの作業コピーからこのファイルを探すと、そのプロジェクトが許可リストを書き換えられるため、起動口自身の配置先を基準に読む。

| Codex に載る名前 | 記録上の提供元・手順の位置 | 読み込み回数 |
| --- | --- | ---: |
| `agent-browser` | `~/.agents/skills/agent-browser` | 13 |
| `investigate` | `~/.agents/skills/gstack/investigate` | 2 |
| `natural-japanese` | `~/.agents/skills/natural-japanese` | 4 |
| `aws-bedrock-cost-audit:aws-bedrock-cost-audit` | `~/.claude/skills/aws-bedrock-cost-audit` | 1 |
| `commit` | `~/.claude/skills/commit` | 485 |
| `daily-report` | `~/.claude/skills/daily-report` | 10 |
| `ground-truth-over-summary` | `~/.claude/skills/ground-truth-over-summary` | 3 |
| `anthropic-skills:docx` | `claude-cowork` の `anthropic-skills` 内 `skills/docx` | 1 |
| `anthropic-skills:pdf` | `claude-cowork` の `anthropic-skills` 内 `skills/pdf` | 1 |
| `engineering:documentation` | `claude-cowork` の `engineering` 内 `skills/documentation` | 1 |
| `pdf:pdf` | `openai-primary-runtime` の `pdf` 内 `skills/pdf` | 1 |

集計は11/10〜11/18 09:26の保存済み1,816セッション。比較に使った316掲載件のうち、本文を読んだ証跡があるのは11件・522回。掲載316件は、前節の起動試験312件とは別の観測。最後の `pdf:pdf` は当時のキャッシュ版が調査時に欠けていたため、同じ提供元・名前・版内の相対位置で現在の版を解決する。［[11件の内訳と判定方法](../../../../harness-nudge/_wt.noindex/startup-breakdown/docs/experiments/2026-11-18-codex-startup-breakdown.md#skill-一覧と記憶の出所2026-11-18)］

- ローカルの初期項目は、表の実体ディレクトリ直下の `SKILL.md` と掲載名の両方で照合する。プラグイン（＝かんたんに言うと、追加機能のセット）は提供元を含むプラグイン ID・版内の位置・掲載名で照合する。これで通常版の `agent-browser` だけを残せる。同じ実体への複数経路は1件として扱う。
- `CODEX_SKILLS_ALLOW=名前,名前` を起動口の環境変数（＝かんたんに言うと、その発注だけに付ける設定）で指定すると初期値に加わる。掲載名を完全一致で選ぶ。前後の空白を除いて重複をまとめ、空の要素・制御文字・ワイルドカード・未知の名前・別実体への複数一致はエラー。全体が未指定または空文字なら追加0件。依頼文中の文字列からは設定を取り込まない。
- `codex-review` は既定で実際に渡す依頼文の前置きに、`~/.agents` 配下の skill 定義を読むことを禁じる指示を付ける。追加指定がこの禁止に当たる場合は、起動口が対象の名前と前置きに抵触する理由、利用に必要な既存設定 `CODEX_REVIEW_ALLOW_SKILLS=1` を標準エラーに示し、実作業の起動前に非0で終了する。明示的に許可された場合は既存の前置き処理に従い、追加項目にも通常の照合を行う。［[読み込み許可の判定](../bin/codex-review#L200)・[既定の前置き](../bin/codex-review#L209)］
- リンク経由の追加 skill がレビューの読み込み禁止に当たるかは、探索経路（一覧に載る置き場のパス）とリンクを解決した実体のパスの両方を照合し、どちらかが `~/.agents` 配下なら起動前に止める。
- 初期項目の未導入・対象外・既存設定で無効は、名前と理由を短く記録して続行する。絞り込みを行うときは、発注者がその回に指定した項目がすべて有効であることを確認する。既存設定が無効にした項目は起動口から再有効化しない。複数実体への一致やパス解決エラーは初期項目でも停止する。

## 置き場の直接列挙と起動時の設定

起動口の共通処理が実作業の `-C` と同じ作業場所を基準に、次の置き場を読み取り専用で調べる。各置き場で `SKILL.md` を持つフォルダを列挙し、見つかったパスをその回の無効化候補にする。

| 置き場 | Codex 0.169.1 に合わせる範囲 |
| --- | --- |
| ユーザー共用・互換用・内蔵 | `~/.agents/skills`、`$CODEX_HOME/skills`、`$CODEX_HOME/skills/.system`。実作業の `CODEX_HOME` が未指定または空なら `~/.codex`。内蔵の `.system` は独立した置き場として調べる。［[ホームの決定](https://github.com/openai/codex/blob/c376cf7396eff83ce4c6ac61b9553df142e7a0be/codex-rs/utils/home-dir/src/lib.rs#L13-L62)・[内蔵の配置先](https://github.com/openai/codex/blob/c376cf7396eff83ce4c6ac61b9553df142e7a0be/codex-rs/skills/src/lib.rs#L66)］ |
| プロジェクト | 作業場所からプロジェクトルートまでの各祖先（両端を含む）の `.agents/skills` と、プロジェクト設定層の `.codex/skills`。ルートの印は既定で `.git`（worktree のファイルも含む）で、`project_root_markers` の指定を反映する。印が無い場合の `.agents/skills` は作業場所だけ。0.169.1 の skill 探索は無効なプロジェクト設定層も置き場の候補にする。［[祖先とルートの判定](https://github.com/openai/codex/blob/c376cf7396eff83ce4c6ac61b9553df142e7a0be/codex-rs/ext/skills/src/host_roots.rs#L335-L440)・[プロジェクト設定層の探索](https://github.com/openai/codex/blob/c376cf7396eff83ce4c6ac61b9553df142e7a0be/codex-rs/config/src/loader/mod.rs#L1853-L1900)・[skill の探索先](https://github.com/openai/codex/blob/c376cf7396eff83ce4c6ac61b9553df142e7a0be/codex-rs/ext/skills/src/host_roots.rs#L127-L189)］ |
| 管理者配布 | macOS ではシステム設定層の `/etc/codex/skills`。［[システム設定の位置](https://github.com/openai/codex/blob/c376cf7396eff83ce4c6ac61b9553df142e7a0be/codex-rs/config/src/loader/mod.rs#L81)・[管理者配布の探索先](https://github.com/openai/codex/blob/c376cf7396eff83ce4c6ac61b9553df142e7a0be/codex-rs/ext/skills/src/host_roots.rs#L173-L178)］ |
| プラグイン | `$CODEX_HOME/plugins/cache/<提供元>/<プラグイン>/<版>` のうち、有効なプラグインの採用版。通常のローカルキャッシュは有効な版名のディレクトリを対象とし、`local` を優先する。それが無ければ両方が SemVer のときは SemVer 順、それ以外は文字列順で比較する 0.169.1 の版選択に従う。採用版の定義が指定する skill の置き場（既定は `skills/`）と、旧形式の `.codex-plugin/migrated-command-skills` を調べる。Agent Plugin 形式は各置き場の直下の skill フォルダを対象とする。［[キャッシュの階層](https://github.com/openai/codex/blob/c376cf7396eff83ce4c6ac61b9553df142e7a0be/codex-rs/core-plugins/src/store.rs#L112-L158)・[有効設定と採用版](https://github.com/openai/codex/blob/c376cf7396eff83ce4c6ac61b9553df142e7a0be/codex-rs/core-plugins/src/loader.rs#L856-L939)・[版選択](https://github.com/openai/codex/blob/c376cf7396eff83ce4c6ac61b9553df142e7a0be/codex-rs/core-plugin-common/src/installed.rs#L40-L68)・[形式別の置き場](https://github.com/openai/codex/blob/c376cf7396eff83ce4c6ac61b9553df142e7a0be/codex-rs/core-plugins/src/loader.rs#L1077-L1142)］ |

1. 再帰探索では、置き場の下の隠しディレクトリを除き、0.169.1 の深さ上限に従う。ユーザー・プロジェクト・管理者配布のディレクトリリンクをたどり、内蔵では置き場の下のディレクトリリンクを除く。循環は訪問中の実体パスで打ち切る。リンク切れで対象ファイルが存在しないものは対象外。Agent Plugin では実体がプラグイン外に出る skill も対象外。探索経路と実体を記録し、最終的な無効化候補は通常ファイルの `SKILL.md` の実体絶対パスで重複を除く。`~/.claude/skills` の項目には共用の置き場などのリンクから到達する。［[探索の深さと隠しディレクトリ](https://github.com/openai/codex/blob/c376cf7396eff83ce4c6ac61b9553df142e7a0be/codex-rs/ext/skills/src/loader/discovery.rs#L67-L85)・[リンクと実体の扱い](https://github.com/openai/codex/blob/c376cf7396eff83ce4c6ac61b9553df142e7a0be/codex-rs/ext/skills/src/loader/host.rs#L146-L258)］
2. 残す一覧と追加指定は、`SKILL.md` の先頭のメタデータとプラグイン定義から求めた掲載名で照合する。0.169.1 の名前の代替規則と名前空間（`プラグイン名:skill名`）に従う。初期項目では提供元と実体も照合し、既存の無効化はユーザー設定など 0.169.1 が読む規則を順に適用して確認する。表の置き場、名前、既存の有効・無効を判定するために必要なローカル設定だけを読む。絞り込みを行うときは、追加指定が有効と確定できなければ起動前に知らせて止める。［[掲載名の元になるメタデータ](https://github.com/openai/codex/blob/c376cf7396eff83ce4c6ac61b9553df142e7a0be/codex-rs/ext/skills/src/loader/host.rs#L347-L405)・[名前空間の決定](https://github.com/openai/codex/blob/c376cf7396eff83ce4c6ac61b9553df142e7a0be/codex-rs/ext/skills/src/loader/namespace.rs#L118-L180)・[既存の有効化規則](https://github.com/openai/codex/blob/c376cf7396eff83ce4c6ac61b9553df142e7a0be/codex-rs/config/src/skills_config.rs#L99-L134)］
3. 無効化は列挙した実体パスにのみ効く。将来 Codex に新しい置き場が増えたり、同期や内蔵展開で起動時に新しいパスが作られたりした場合、その skill が絞り込みから外れて普段どおりに使えるだけで、作業や既存設定は壊れない。0.169.1 にも別の実行環境や実行時に追加される置き場があるため、この設計の対象は表にある起動前のローカル配置。列挙から起動までに採用版や設定の変更を検知したら起動を止める。起動後も含めた利用制限は実行権限の既存設定が担う。［[実行環境・追加の置き場](https://github.com/openai/codex/blob/c376cf7396eff83ce4c6ac61b9553df142e7a0be/codex-rs/ext/skills/src/host_roots.rs#L90-L124)・[内蔵の配置タイミング](https://github.com/openai/codex/blob/c376cf7396eff83ce4c6ac61b9553df142e7a0be/codex-rs/ext/skills/src/host_service.rs#L287-L309)］

### 実作業は現在の設定に `-c` で追記する

- 0.169.1 では `-c`（＝かんたんに言うと、その起動だけに設定を重ねる引数）を TOML として解釈し、ドットで区切った設定先へ入れる。配列内に表を置く形と真偽値の両方を渡せる。後述の二つの値はそれぞれ1引数。公式説明と、タグが指すコミット `c376cf7396eff83ce4c6ac61b9553df142e7a0be` のソースで確認した。［[公式の起動時上書き](https://learn.chatgpt.com/docs/config-file/config-advanced#one-off-overrides-from-the-cli)・[値の解釈](https://github.com/openai/codex/blob/c376cf7396eff83ce4c6ac61b9553df142e7a0be/codex-rs/utils/cli/src/config_override.rs#L49)・[起動時設定への取り込み](https://github.com/openai/codex/blob/c376cf7396eff83ce4c6ac61b9553df142e7a0be/codex-rs/config/src/loader/mod.rs#L445)］
- skill は `-c 'skills.config=[{path="/absolute/path/SKILL.md", enabled=false}]'` の形で、`[[skills.config]]` と同じ内容を1つの配列で渡す。列挙した実体パスから、その回に残す実体パスを除いた全件に `enabled=false` を指定する。0.169.1 の skill 専用処理は、ユーザー設定と起動時設定のルールを順に読み、同じ skill に当たる後の指定を優先する。追加は `enabled=false` のみで、許可内の既存無効化も引き継ぐ。プラグイン本体の有効設定には触れず、同梱の連携やフックを保つ。［[skill ルールの重ね方とパスの正規化](https://github.com/openai/codex/blob/c376cf7396eff83ce4c6ac61b9553df142e7a0be/codex-rs/config/src/skills_config.rs#L99-L218)・[プラグイン個別 skill への適用](https://github.com/openai/codex/blob/c376cf7396eff83ce4c6ac61b9553df142e7a0be/codex-rs/core-plugins/src/loader.rs#L1041-L1051)］
- 記憶は `-c memories.use_memories=false` を渡す。0.169.1 の読み込み側の条件と、先行実験の差し込み1→0がこの選択の根拠。［[公式の記憶設定](https://learn.chatgpt.com/docs/customization/memories#configure-local-memories)・[0.169.1 の差し込み条件](https://github.com/openai/codex/blob/c376cf7396eff83ce4c6ac61b9553df142e7a0be/codex-rs/ext/memories/src/extension.rs#L43)］
- `bin/_codex_common.sh` の共通処理から、両起動口の既存の実行引数に追加する。`python3` で文字列を TOML として組み立て、`tomllib` で読み直して期待したパスと型・値に一致することを確認する。引数配列として渡し、名前やパスをシェルで再解釈させない。列挙・検証は実行の予約やバックグラウンド起動の前に完了させ、既存の作業権限、GitHub/AWS の名義、モデル設定を引き継ぐ。

**実装メモ**　絞り込みは費用削減のため、未検証版・版不明・置き場の読み取り失敗では、skill と記憶の上書きを省いて既存の経路で起動する。
絞り込みを省いた理由を標準エラー1行と状態ファイルの1項目に記録する。
レビューの読み込み禁止は安全のため、追加指定がリンク経由で抵触する場合や、禁止対象か確認できない場合は起動前に止める。

### 対応する CLI の版

絞り込みを使う場合は、実作業と同じ CLI の版を列挙前に識別する。最初の検証対象は 0.169.1。置き場、名前の照合、上書きの動作を確認した版を通す。未検証版や版を識別できない場合は、版・理由・確認方法を標準エラーに1行出し、`launch_skills_filter=skipped:unverified_version` を状態ファイルに記録する。通常は列挙を省き、既存の経路で起動する。明示の `CODEX_SKILLS_FILTER=off` は絞り込み用の版判定を省き、既存の経路で起動する。

## 入切りと失敗時の扱い

| 発注時の設定 | skill | 記憶 |
| --- | --- | --- |
| 指定なし、または `CODEX_SKILLS_FILTER=on` | 初期11件と発注時の追加分 | 差し込みを切る |
| `CODEX_SKILLS_FILTER=on CODEX_MEMORIES=keep` | 初期11件と発注時の追加分 | 普段の設定を引き継ぐ |
| `CODEX_SKILLS_FILTER=off` | 普段の設定を引き継ぐ | 普段の設定を引き継ぐ |

`CODEX_MEMORIES` は未指定時に `off`、指定値は `off` または `keep`。全体を戻す `CODEX_SKILLS_FILTER=off` は両方の上書きと列挙を省く。全体 off と空でない追加指定の併用や、定義外の値は設定ミスとして起動前に返す。

未作成の置き場は0件として続行する。既知の置き場に読み取り失敗がある場合は、対象・版・理由・確認方法を標準エラーに1行出し、`launch_skills_filter=skipped:inventory_unreadable` を状態ファイルに記録して既存の経路で起動する。

- **起動前の失敗**。読み込み禁止に当たるレビューの追加指定、追加指定の形式不正、列挙の期限切れや実行中の設定変更、上書きの組み立て失敗や引数の上限超過などでは、起動口が標準エラーに理由を出して非0で終了する。
- **実作業の子プロセス起動後の設定エラー**。発注者は親が返した実行IDで `codex-status <run id>` を開き、「異常終了（判定行なし・ログを確認）」と表示されたら、ログ末尾または「ログ」欄のファイルで設定エラーの内容を確認する。［[終了診断とログの表示](../bin/codex-status#L64)］

発注者は標準エラーまたは実行ログを確認して原因を修正できる。絞り込みを明示的に省く場合は、`CODEX_SKILLS_FILTER=off` を指定し、`CODEX_SKILLS_ALLOW` があれば外す。起動口の失敗ログには設定本文や資格情報を出さない。日常ログに残すのはモード、列挙件数、残す件数、外す件数、列挙時間と短いエラー理由。

## 守る条件といまの件数

| 守る条件 | 現時点の件数・根拠 |
| --- | --- |
| 実際に使った手順を残せる | 316掲載件のうち読まれた11件・522回を全件採用。残る305掲載件の確認済み読み込みは0回。掲載外の読み込み例は少なくとも1種類（`test-design`）。必要だったのに使えなかった件数は未測定で、今後も0件とは置かない |
| 新しい手順と同名の別実体を区別できる | 同名11組のうち9組は同一内容の別ファイルで、残る2組は内容が異なる。実体を確認できた307行で同一実体の二重掲載は0組。キャッシュ版消失で実体未確認の掲載は9件 |
| 普段の作業手順を動かさない | 影響を避ける対象として、共用から Claude 側へのリンク経由が30掲載件、Claude 側から共用へのリンクが8件。対象の起動口は2本。新方式での直接起動・Claude Code への影響は確認0回 |
| 意図したときだけ記憶が入る | 基準と skill のみでは各3/3回で差し込み1件、記憶を切った2条件では計6/6回で0件。記憶だけ戻す新しいモードの確認は0回 |
| 読み取り・上書き失敗を起動前に検出する | 今回の設計方式での失敗発生数・復帰数は未測定（実起動0回）。先行計測で無効な設定値を渡した対照は1回拒否。置き場の読み取り失敗や名前指定の誤りは実装後に確認する |
| 置き場を読み取り専用で扱う | 直接列挙の時間と、列挙前後で設定・skill・リンクに差分がないことを実装後に確認する |

## 実装後の検査

1. **単体試験**ではテスト用のディレクトリと設定を使い、各置き場、新規 skill、作業場所と祖先、未作成の置き場、同名の別実体、プラグインの採用版・旧版、リンクの循環・欠損、既存の無効化を再現する。引数は TOML として再読込し、許可外だけに `false` が追加されること、空配列、日本語や空白の入ったパス、モードごとの記憶設定を確認する。未検証版・版不明・置き場の読み取り失敗では、両起動口が上書きを省いて起動し、警告1行と状態を記録することを確かめる。読み込みを禁じるレビューに追加指定があれば、未検証版でもリンクの探索経路と実体を検査する。列挙の期限切れ、曖昧名、引数の上限超過では理由付きで起動前に止める。明示 off は列挙を省き、記憶だけ keep は skill の上書きだけを渡す。実作業側の設定エラーは、返された実行IDから `codex-status` で異常終了とログを確認できることを確かめる。既存の [`tests/test_codex_launch_skills.py`](../tests/test_codex_launch_skills.py)（`58c38fe`）のうち、旧方式の一覧応答や専用プロセスに依存する試験は、実装時に置き場とファイルを使う試験へ差し替える。
2. **陰性試験**（＝かんたんに言うと、わざと壊して検査が失敗するかを確かめる試験）を独立に2本行う。許可リスト判定を無視して全件を通す変更では、既知の許可外1件が実行引数から漏れて失敗すること。既定時の記憶上書きだけを落とす変更では、起動引数の `memories.use_memories=false` が欠けて失敗すること。起動口が受け取った引数を検査し、ログ表示だけで合格を決めない。
3. **陽性対照**（＝かんたんに言うと、残すべきものが使えることの確認）では、通常版 `agent-browser` や `commit`、発注時の追加1件が有効のまま残り、同名の別パスと無関係な新規項目が無効になることを確認する。既存設定が無効にした skill は引き続き無効。`codex-review` では、禁止対象の追加指定だけなら理由と `CODEX_REVIEW_ALLOW_SKILLS=1` の案内を出して非0で終了し、実作業の子を起動しないことを確認する。同じ追加指定に `CODEX_REVIEW_ALLOW_SKILLS=1` を添えた陽性対照では、追加した skill が有効で、起動コマンドの標準入力に実際に渡る依頼文に禁止の前置きが付かず、元の依頼本文が届くことを確認する。追加指定なしの既定レビューでは、実際に渡る依頼文に禁止の前置きが付くことも確認する。列挙の前後で設定、元の skill、リンクに差分がないことを確認する。
4. **実機での最終確認**は実装担当とは別に取りまとめ側が実行する。両起動口をテスト用コマンドで通した後、本人の通常構成に相当する検証環境で、同じ起動口・作業場所・モデル・依頼を使い、既定と明示の `CODEX_SKILLS_FILTER=off` を各3回、新規セッションで測る。実行IDと会話記録を突き合わせ、初回 `host_skills.instructions` の件数とパス集合、`memories.instructions` の有無、最初の `input_tokens` とキャッシュ分、列挙時間を記録する。機能の合格条件は、既定で予定した有効 skill が残り、許可外が0件で、記憶の差し込みが0件であること。効果の報告には両条件の `input_tokens` 各3回の値と平均、削減率（`(off の平均 − 既定の平均) ÷ off の平均 × 100`）を載せる。削減率の合格条件は25%以上。先行実験の31.1%から、起動口の前置きや残す skill の違いによる変動分として約6ポイントの幅を見込んだ下限とする。単独の測定で判断できるのは測ったモードの機能までとし、各3回の比較がそろうまでは削減効果を「未判定」と報告する。

## 7段で止めた場所

1 そもそも要るか → 2 既にあるか → 3 標準ライブラリ → 4 プラットフォームの標準機能 → 5 導入済みの依存 → 6 1行で書けるか → 7 最小のコード。各行は左から調べ、採用できた段で止める。

| 足す仕組み | 止めた段 | 理由 |
| --- | --- | --- |
| 初期11件と発注時の追加・入切り | **7 最小のコード** | 依頼ごとに追加・復帰する口が要る。既存の起動口にこの指定はなく、標準のファイル・環境変数で入出力できても、名前の曖昧さや矛盾を1行で検証できない。1ファイルと両起動口の共通処理に収める |
| 対象の探索 | **3 標準ライブラリ** | 0.169.1 の置き場を標準ライブラリで列挙し、`SKILL.md` の実体パスを集める。置き場の選択と名前の照合には同版の規則を使う |
| パス解決・設定文字列の検証 | **3 標準ライブラリ** | 既存の Python 3.11 で `pathlib` と `tomllib` を使える。信頼の境目にあるパス・型・値・引数境界は検査を残す |
| skill と記憶をその回だけ切る | **4 プラットフォームの標準機能** | 既存の起動口にある `-c` の渡し方を使い、Codex が解釈する配列と真偽値を追加する |
| 失敗時の通知 | **7 最小のコード** | 標準エラーと既存の状態ファイルで絞り込みを省略した理由を伝え、レビューの読み込み禁止には終了コードを使う |
| 検査 | **2 既にあるか／7 最小のコード** | 起動口を偽コマンドで検査する既存テスト、会話記録を数える既存の計測方法を再利用する。明示依頼の陰性2本と陽性対照はその仕組みに追加する |

## 巡の履歴

設計巡1のレビュー（`0-skill-allow-drev1-20261118-110219-79587`）を反映。

- 指摘1 [Must] 実機での最終確認に、同条件で既定と off を各3回測る方法、報告値、削減率25%以上の合格条件と未判定の扱いを追記。
- 指摘2 [Must] 発注時の指定と陽性対照に、レビュー既定の読み込み禁止と追加指定の衝突時の停止、既存設定で許可したときに実際に渡る依頼文の確認を追記。
- 指摘3 [Should] 探索を完了できない場合の停止と検査を追記。
- 指摘4 [Should] 版の扱いと失敗時の節、単体試験に、未検証版の列挙前停止、明示 off の既存経路、親の終了コード・標準エラーと子の終了後の診断・ログを使う再発注手順を追記。
- 三回目の設計: 方式変更（本人承認・2026-11-18）
