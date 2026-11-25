import sys
import argparse
import re
import json
import hashlib
import os
from datetime import datetime
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--entrypoint', choices=('codex', 'cc'), required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--file')
    group.add_argument('--stdin', action='store_true')
    args = parser.parse_args()
    if (args.entrypoint == 'codex') != bool(args.file):
        parser.error('codex requires --file; cc requires --stdin')
    return run(args)


def run(args):
  try:
    prompt_bytes = Path(args.file).read_bytes() if args.file else sys.stdin.buffer.read()
    body = prompt_bytes.decode('utf-8')
    if '\0' in body:
        raise ValueError
    fields = {}
    for key in ('直しの出所', '受領①累計', '受領②件数', '受領③7段'):
        fields[key] = [line[len(key) + 1:].strip() for line in body.splitlines()
                       if line.startswith(key + ':')]
    source = fields['直しの出所']
    reason = ''
    match = None
    if len(source) != 1 or not source[0]:
        reason = '直しの出所: は行頭に、空でない値つきで1行だけ必要です。'
    elif not source[0].startswith(('なし', 'レビュー')):
        reason = '直しの出所は「なし」か「レビュー」で始めてください。'
    elif source[0].startswith('なし'):
        source_line = next(i for i, line in enumerate(body.splitlines())
                           if line.startswith('直しの出所:'))
        match = re.search(r'巡[0-9]|指摘を反映', '\n'.join(body.splitlines()[source_line + 1:]))
        if match:
            reason = '出所を「レビュー…」に直し、受領の3行を書く必要があります。語で見ているだけ・言い換えは通る。'
    elif source[0].startswith('レビュー'):
        match = re.search(r'Should', body, re.IGNORECASE)
        if match:
            reason = 'レビュー由来の直しには [Must] だけを入れる。[Should] は依頼文から外して別課題の候補として頭の報告に並べる（~/.claude/rules/review-receipt.md）。語で見ているだけ・言い換えは通る'
        elif any(len(fields[key]) != 1 or not fields[key][0] for key in fields if key != '直しの出所'):
            reason = 'レビューの直しには、空でない受領の3行がそれぞれ1行必要です。'
    if match:
        log = Path.home() / '.codex-watch' / 'receipt-gate-stops.log'
        stops = log.parent / 'receipt-gate-stops'
        stops.mkdir(parents=True, exist_ok=True, mode=0o700)
        stopped_at = datetime.now().astimezone()
        sha256 = hashlib.sha256(prompt_bytes).hexdigest()
        snapshot = stops / f'{stopped_at.strftime("%Y%m%dT%H%M%S.%f%z")}-{sha256[:12]}.md'
        with os.fdopen(os.open(snapshot, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
            stream.write(prompt_bytes)
        with log.open('a', encoding='utf-8') as stream:
            row = {'time': stopped_at.isoformat(),
                                     'prompt': str(Path(args.file).resolve()) if args.file else None,
                                     'match': match.group(),
                                     'snapshot': str(snapshot), 'sha256': sha256}
            if args.entrypoint == 'cc':
                row['entrypoint'] = 'cc'
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
  except (OSError, UnicodeError, ValueError):
    reason = '依頼文の読取・写しの保存または停止ログの記録に失敗しました（UTF-8必須・NUL不可）。'
  if reason:
    if reason.startswith('出所を「レビュー…」'):
        reason += '調査・集計・下書きなど直しでない依頼なら、該当する語を言い換え、受領の行は書かずに出し直してください。'
    print('拒否: ' + reason + """
~/.claude/rules/review-receipt.md の3手順を、直しの依頼前に済ませてください:
①起点からの累計と未追跡 ②各[Must]の危険の件数・母集団・取得日 ③足す前に7段。
行頭・字下げなし・半角コロンで書く例:
直しの出所: レビュー巡1（対象版・出所）
受領①累計: 起点abc123から1 commit・2ファイル・+10/-2、未追跡0件
受領②件数: M1=対象10件中2件（YYYY-MM-DD取得）
受領③7段: M1は㋑、既存の起動口を再利用
レビュー由来でなければ「直しの出所: なし（新規実装）」を1行。
既知の書き方だけを見る・自己申告なので迂回できる（捕まえるのは書き忘れ）。
「なし」の本文は 巡[0-9]|指摘を反映 で検査します。語で見ているだけ・言い換えは通る。
「レビュー」の依頼文は、出所・受領の行を含む本文全体に Should の語（大文字小文字を問わない）があれば止まります。件数（例: Should 0件）も書かず、本人が承認した中程度の指摘を直すときも語を使わずに書く。""", file=sys.stderr)
    return 2
  print(f'receipt-gate v1 pass sha256={hashlib.sha256(prompt_bytes).hexdigest()}')
  return 0


if __name__ == '__main__':
    sys.exit(main())
