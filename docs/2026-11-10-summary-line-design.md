# 設計: Codex の走行に「何をしているか」の日本語1行を付け、見回りの画面に出す

- 状態: 設計（レビュー前）。ユーザー合意 2026-11-10「最小案」（1行は任意・必須にしない）
- 変更先: 2リポジトリ
  - `todoroki-godai/codex-watch`（本 worktree: `feat/codex-summary-line`、起点 origin/main `aa393cd`）
  - `todoroki-godai/claude-config`（worktree `/Users/matsukaze-takashi/.claude-wt.noindex/board-codex-summary`、枝 `feat/board-codex-summary`、起点 origin/main `9b2d7c5`）

## 困りごと（根拠つき）
- session-board の一覧で、走っている Codex が `rev9-l2design` のような英字ラベルで出て、何をしているか分からない（2026-11-10 ユーザー指摘）。
- 原因: `mods/session-board/hooks/register.tsx:202-220`（claude-config 9b2d7c5 時点）の `codexInfo`/`codexText` は、課題番号（名前の先頭の数字か `review_target` の `#N`）が取れないと `reviewer || run_id` から日時を外した英字ラベルをそのまま出す。起動口 `bin/codex-impl:28` / `bin/codex-review:18` は第3引数のラベルしか受け取らず、説明を書く欄が無い。
- 規模: 直近24時間の走行 101件のうち 98件が英字ラベル表示（取得 2026-11-10 11:44、再現手段は末尾の script）。

## 変更（最小案）
1. **起動口**（codex-watch）: `codex-impl`・`codex-review` が環境変数 `CODEX_SUMMARY` を読み、空でなければ状態ファイルへ `summary=<値>` を1行書く。
   - 正規化: 改行・CR・タブを空白に置換、前後空白を除去、60文字（コードポイント）で切る。`=` は値の中にあってよい（状態は先頭の `=` で分割＝`register.tsx` `parseState`）。
   - 未指定・空なら何も書かない。**起動は拒否しない**（合意: 必須にしない）。
2. **board**（claude-config）: `codexInfo` が `summary` を返し、`codexText` は `summary` が非空ならそれを主語に使う:
   `Codex が「<summary>」を<実装|設計レビュー|コードレビュー>中（3分）` / 終了時 `Codex の<work>が<elapsed>前に終了: 「<summary>」`。
   - 優先順: summary → 課題番号（従来）→ 英字ラベル（従来）。summary が無い古い走行は従来どおり。
   - 名前の衝突に注意: `codexText(c, summary, elapsed)` の第2引数 `summary` は既に「課題の要約」の意味で使われている（`register.tsx:213-216`、呼び出し 1845行）。board 側では新しい値を `CodexRow.doing` として持ち、既存の `summary` 引数の意味は変えない。検査は既存の `hooks/register.test.ts` に足す。
   - 画面に出す前に、制御文字を除き 60 文字で切る（状態ファイルは起動口以外でも書けるため、読む側でも守る）。
3. **手順書**（claude-config）: `rules/pipeline-routing.md` 27行目（codex-impl の起動の正典）と `refs/codex-exec.md` 18行目（codex-review の起動）に、「起動時に `CODEX_SUMMARY='<何をしているか30字ほど・名詞で終える>'` を付ける」を1文ずつ。

## 完成条件（round 0）
- ①守る対象: (a) 新しく起こした走行が、`CODEX_SUMMARY` を付ければ見回りの画面で日本語1行で読めること (b) 付けない起動・古い状態ファイルの表示と起動の成否が今と変わらないこと (c) 状態ファイルの既存キーの値が変わらないこと（codex-status・codex-watch・board の他の読み手を壊さない）
- ②信頼境界: `CODEX_SUMMARY` を書くのは同じ利用者の窓（CC・Codex のセッション）。悪意ある第三者は数えない。ただし誤記（改行・長文・制御文字）は数える。
- ③対象外: 1行を必須にすること／既存の走行への後付け／`review_target` 等の既存キーを表示に流用すること／`~/.claude` 手元の版を GitHub に合わせる作業（反映の手番で別に決める）
- ④blocking: ①(a)(b)(c) のどれかが破れること、改行入りの値で状態ファイルの行が増えること（＝別キーを偽装できる）
- ⑤検証: 起動口は既存 `tests/` の流儀でシェル検査（codex 本体は起動しない差し替え）。board は既存のテスト（`mods/session-board` 配下）に `codexInfo`/`codexText` の表を足す。陰性試験: 改行入り値でキーが増えない／summary 無しで従来表示／60字超で切れる。陽性対照: 普通の日本語1行がそのまま出る。変異（正規化の除去・優先順の反転）を当てて赤くなることを確認する。
- ⑥この成果物が削る量: 「英字ラベルでしか読めない走行」直近24時間で 98件/101件（観測値、取得 2026-11-10 11:44）。削れるのは手順書どおり `CODEX_SUMMARY` を付けた走行の分。設計文書なので実装の削減量として数える＝この設計が無いと上記3変更の仕様（キー名・正規化・優先順）が決まらず実装できない。実現する作業: 本設計の2枝の実装（見積もり 起動口 約8行＋検査、board 約12行＋検査、手順書 2文）。

## 前提と根拠
| 前提 | 根拠（値／取得方法／取得日） |
|---|---|
| board は summary を表示に使っていない | `grep -n summary ~/.claude-wt.noindex/board-codex-summary/mods/session-board/hooks/register.tsx` の codexInfo 内に無し（203-208行）／2026-11-10 |
| 状態ファイルは1行1キー、先頭 `=` で分割 | `register.tsx` `parseState`（58-64行、調査担当の報告。頭は 202-220 を実物で確認）／2026-11-10 |
| 起動口のラベルは第3引数のみ | `bin/codex-impl:28 LABEL="${3:-impl}"`（頭が実物で確認）・`bin/codex-review:18`（調査担当の報告）／2026-11-10 |
| 英字表示の件数 | 下の script ／2026-11-10 11:44 で 101件中98件 |

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
