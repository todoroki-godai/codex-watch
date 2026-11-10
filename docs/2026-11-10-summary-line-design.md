# 設計: Codex の走行に「何をしているか」の日本語1行を付け、見回りの画面に出す

- 状態: 設計（レビュー前）。ユーザー合意 2026-11-10「最小案」（1行は任意・必須にしない）
- 変更先: 2リポジトリ
  - `todoroki-godai/codex-watch`（本 worktree: `feat/codex-summary-line`、起点 origin/main `aa393cd`）
  - `todoroki-godai/claude-config`（worktree `/Users/matsukaze-takashi/.claude-wt.noindex/board-codex-summary`、枝 `feat/board-codex-summary`、起点 origin/main `9b2d7c5`）

## 困りごと（根拠つき）
- session-board の一覧で、走っている Codex が `rev9-l2design` のような英字ラベルで出て、何をしているか分からない（2026-11-10 ユーザー指摘）。
- 原因: `mods/session-board/hooks/register.tsx:202-220`（claude-config 9b2d7c5 時点）の `codexInfo`/`codexText` は、課題番号（名前の先頭の数字か `review_target` の `#N`）が取れないと `reviewer || run_id` から日時を外した英字ラベルをそのまま出す。起動口 `bin/codex-impl:28` / `bin/codex-review:18` は第3引数のラベルしか受け取らず、説明を書く欄が無い。
- 規模: 直近24時間の走行 101件のうち 98件が、状態ファイル上で課題番号が取れない件数（＝英字ラベルで出る潜在対象。board の表示選別は通していない。取得 2026-11-10 11:44、再現手段は末尾の script）。

## 変更（最小案）
1. **起動口**（codex-watch）: `codex-impl`・`codex-review` が環境変数 `CODEX_SUMMARY` を読み、空でなければ状態ファイルへ `summary=<値>` を1行書く。
   - 正規化: **新しい規則を作らず既存の `sanitize_single_line()`（`bin/_codex_common.sh:43-54`。判定源は `lib/round_gate.py` の `is_single_line`＝Python の `splitlines()` が行境界とみなす全文字を空白にする）を通す**。その後に前後空白を除去し、60コードポイントで切る。`=` は値の中にあってよい（状態は先頭の `=` で分割＝`register.tsx` `parseState`・`round_gate.py` `read_state_file`）。
   - 正規化**後**に空なら何も書かない（空白だけの値も同じ）。**起動は拒否しない**（合意: 必須にしない）。
   - 「1行」は状態ファイルの論理行1行の意味。画面上で折り返すことはある。
2. **board**（claude-config）: `codexInfo` が `summary` を返し、`codexText` は `summary` が非空ならそれを主語に使う:
   `Codex が「<summary>」を<実装|設計レビュー|コードレビュー>中（3分）` / 終了時 `Codex の<work>が<elapsed>前に終了: 「<summary>」`。
   - 優先順: summary → 課題番号（従来）→ 英字ラベル（従来）。summary が無い古い走行は従来どおり。
   - summary と課題番号の両方があるときは `Codex が 課題 #N「<summary>」を…中` と並べて出す（2026-11-10 ユーザー選択「番号も並べて出す」。コードレビュー巡1の [Should]1 由来）。
   - 名前の衝突に注意: `codexText(c, summary, elapsed)` の第2引数 `summary` は既に「課題の要約」の意味で使われている（`register.tsx:213-216`、呼び出し 1845行）。board 側では新しい値を `CodexRow.doing` として持ち、既存の `summary` 引数の意味は変えない。検査は既存の `hooks/register.test.ts` に足す。
   - 画面に出す前に、行境界になる文字（LF・CR・VT・FF・U+001C〜001E・U+0085・U+2028・U+2029）と他の制御文字を空白にし、前後空白を除き、`Array.from(v).slice(0, 60).join('')` でコードポイント単位に切る（UTF-16 の途中で切って孤立サロゲートを作らない）。状態ファイルは起動口以外でも書けるため、読む側でも守る。正規化後に空なら summary 無しとして扱う。
   - 配線: `collectCodex`（`register.tsx:937-948`）で状態の `summary` を `CodexRow.doing` へ入れ、行生成（1844-1849行の `codexText` 呼び出し）まで渡す。
3. **手順書**（claude-config）: `refs/pipeline-routing.md` 44行目（codex-impl の起動の正典。2026-11-06 に rules 旧27行から移動済み）と `refs/codex-exec.md` 18行目（codex-review の起動）に、「起動時に `CODEX_SUMMARY='<何をしているか30字ほど・名詞で終える>'` を付ける」を1文ずつ。

## 完成条件（round 0）
- ①守る対象: (a) 新しく起こした走行が、`CODEX_SUMMARY` を付ければ見回りの画面で日本語1行で読めること (b) 付けない起動・古い状態ファイルの表示と起動の成否が今と変わらないこと (c) 状態ファイルの既存キーの値が変わらないこと（codex-status・codex-watch・board の他の読み手を壊さない）
- ②信頼境界: `CODEX_SUMMARY` を書くのは同じ利用者の窓（CC・Codex のセッション）。悪意ある第三者は数えない。ただし誤記（改行・長文・制御文字）は数える。
- ③対象外: 1行を必須にすること／既存の走行への後付け／`review_target` 等の既存キーを表示に流用すること／`~/.claude` 手元の版を GitHub に合わせる作業（反映の手番で別に決める）
- ④blocking: ①(a)(b)(c) のどれかが破れること、改行入りの値で状態ファイルの行が増えること（＝別キーを偽装できる）
- ⑤検証: 起動口は既存 `tests/` の流儀でシェル検査（codex 本体は起動しない差し替え）。board は既存の `hooks/register.test.ts` に足す。
  - 陰性試験（起動口）: 値に行境界10種（LF・CR・VT・FF・U+001C・U+001D・U+001E・U+0085・U+2028・U+2029）それぞれ＋`review_target=none:other` を混ぜて起動し、書かれた状態ファイルを `round_gate.read_state_file` と board の `parseState` の両方で読んで、**`summary` を除くキー集合と既存キーの値が summary 無しの起動と同じで、追加キーは `summary` だけ**であること（新キーの追加・既存キーの上書きの両方を見る）。
  - 陰性試験（board）: 同じ10種を含む状態文字列で、表示が1行・孤立サロゲート無し・60コードポイント以内。空白だけの summary で従来表示。
  - 結合試験: 状態文字列 → `parseState` → `collectCodex` 相当 → 行の文字列まで通して、summary が出ること（純粋関数だけの検査では配線漏れを拾えないため）。
  - 陽性対照: 普通の日本語1行、および `日本語=a=b` がそのまま出て、`pid` 等の既存キーが保たれる。summary 無しの旧状態で従来表示（`Codex が old を実装中（1分）`）。
  - 変異: 正規化を `\n\r\t` だけの置換に戻す／優先順を反転する／`slice` を UTF-16 単位に戻す、の3つを当てて、それぞれ赤くなることを確認する。
- 今日済ませた計測（measure-now の3問）: ①既存の行境界処理と読み手の食い違いは、設計レビュー巡1で既存関数への入力だけで再現・確定済み（`round_gate.py:426` は `splitlines()`、board は LF 分割）。②片側だけの結論: 既存の `sanitize_single_line` を通せば両方の読み手で同じ結果になることは、同巡1の対照実験で確認済み。③新機能の結合試験は実装前には実行できないので、実装と同じ commit で上の検査を足す（延期ではなく実装の一部）。
- ⑥この成果物が削る量: **潜在対象数**として、状態ファイル上で課題番号が取れない走行 直近24時間 98件/101件（取得 2026-11-10 11:44。巡1の再集計では 102件中98件＝時間窓の差）。board の表示選別（期間・生存・終了時刻、`register.tsx:930,951-956`）を通した件数ではない。**削減実績ではない**: 実際に減るのは起動者が `CODEX_SUMMARY` を付けた走行の分で、付ける率は未測定（①現状件数は今日測った ②説明付きで読めることは陽性対照で先に確かめる ③既存ラベルの分布は対象規模の代理になるが、付ける率の代理にはならない）。設計文書なので実装の削減量として数える＝この設計が無いと上記3変更の仕様（キー名・正規化・優先順）が決まらず実装できない。実現する作業: 本設計の2枝の実装（見積もり 起動口 約8行＋検査、board 約12行＋検査、手順書 2文）。

## 前提と根拠
| 前提 | 根拠（値／取得方法／取得日） |
|---|---|
| board は summary を表示に使っていない | `grep -n summary ~/.claude-wt.noindex/board-codex-summary/mods/session-board/hooks/register.tsx` の codexInfo 内に無し（203-208行）／2026-11-10 |
| 状態ファイルは1行1キー、先頭 `=` で分割 | `register.tsx` `parseState`（58-64行、調査担当の報告。頭は 202-220 を実物で確認）／2026-11-10 |
| 起動口のラベルは第3引数のみ | `bin/codex-impl:28 LABEL="${3:-impl}"`（頭が実物で確認）・`bin/codex-review:18`（調査担当の報告）／2026-11-10 |
| 状態ファイル上で課題番号が取れない件数 | 下の script ／2026-11-10 11:44 で 101件中98件 |

```python
# python3 -I で実行
import glob,os,re,time
now=time.time(); tot=eng=0
for f in glob.glob(os.path.expanduser('~/.codex-watch/*.state')):
    if now-os.path.getmtime(f)>86400: continue
    s={}
    for l in open(f,errors='replace'):
        if '=' in l: k,v=l.rstrip('\n').split('=',1); s.setdefault(k,v)
    name=re.sub(r'-\d{8}-\d{6}-\d+$','',s.get('reviewer') or s.get('run_id',''))
    tot+=1
    if not (re.match(r'^(\d+)(?:-|$)',name) or re.search(r'#(\d+)',s.get('review_target',''))): eng+=1
print(tot,eng)
```
