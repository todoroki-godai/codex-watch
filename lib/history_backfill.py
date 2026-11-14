"""Propose dispatch IDs using a one-to-one legacy row/state match; never edit GitHub."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import re
import sys

from prerelease import RE_ID, section
from round_gate import Indeterminate, ROUND_ROW_HEADER, gh_fetch_body, parse_target, read_state_file


def backfill(body: str, state_dir: Path, target: str) -> tuple[str, list[str]]:
    text = section(body, '巡の履歴')
    # Locate the exact section span while preserving all bytes around it.
    start = re.search(r'^## 巡の履歴\s*$', body, re.M).end()
    lines = text.splitlines(keepends=True)
    states = []
    if not state_dir.is_dir():
        raise ValueError('state directory unavailable')
    for path in sorted(state_dir.glob('*.state')):
        raw = path.read_text().splitlines()
        keys = [line.partition('=')[0] for line in raw]
        if any('=' not in line for line in raw) or len(keys) != len(set(keys)):
            raise ValueError('broken state: ' + path.name)
        data = read_state_file(path, strict=True)
        if data.get('review_target') != target:
            continue
        key = (data.get('round', ''), data.get('kind_label', ''),
               data.get('started_at_human', ''), data.get('head_sha', '')[:7],
               data.get('reviewer', ''))
        states.append((key, data.get('run_id', '')))
    rows = []
    warnings = []
    for i, line in enumerate(lines):
        if (not line.strip() or line.strip() == ROUND_ROW_HEADER
                or re.fullmatch(r'\|(?:\s*:?-{3,}:?\s*\|)+', line.strip())):
            continue
        if re.match(r'^\|\s*\d+\s*\|', line):
            rows.append((i, tuple(cell.strip() for cell in line.split('|')[1:6])))
        else:
            warnings.append('説明文または解釈できない行: ' + line.rstrip('\r\n'))
    counts = Counter(key for _, key in rows)
    ids = Counter(rid for _, rid in states)
    used = set(re.findall(r'<!-- dispatch_id=([^\r\n]*?) -->', text))
    for i, key in rows:
        line = lines[i]
        if '<!-- dispatch_id=' in line:
            continue
        found = [rid for skey, rid in states if all(skey) and skey == key]
        if (counts[key] != 1 or len(found) != 1 or not RE_ID.fullmatch(found[0])
                or ids[found[0]] != 1 or found[0] in used):
            warnings.append('未補完: ' + line.rstrip('\r\n') + f' (候補 {len(found)}件)')
            continue
        ending = '\r\n' if line.endswith('\r\n') else ('\n' if line.endswith('\n') else '')
        content = line.removesuffix(ending) if ending else line
        lines[i] = content + f' <!-- dispatch_id={found[0]} -->' + ending
        used.add(found[0])
    return body[:start] + ''.join(lines) + body[start + len(text):], warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', help='issue:owner/repo#N or pr:owner/repo#N')
    parser.add_argument('--state-dir', type=Path, default=Path.home() / '.codex-watch')
    parser.add_argument('--output', type=Path, help='proposed body file (default: stdout)')
    args = parser.parse_args(argv)
    try:
        target = parse_target(args.target)
        if args.output and any(args.output.resolve().is_relative_to(folder.resolve())
                               for folder in (args.state_dir, Path.home() / '.codex-watch')):
            raise ValueError('output must be outside state directory')
        body = gh_fetch_body(target)
        proposed, warnings = backfill(body, args.state_dir, target.key())
        if args.output:
            args.output.write_text(proposed)
        else:
            sys.stdout.write(proposed)
        for warning in warnings:
            print(warning, file=sys.stderr)
        return 1 if warnings else 0
    except (ValueError, OSError, Indeterminate) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
