"""Read only frozen prompt paths; emit metadata/counts, never prompt bodies."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PATTERNS = {
    'requested': r'巡[0-9]|\[Must\]|指摘を反映',
    'without_must': r'巡[0-9]|指摘を反映',
    'review_and_fix': r'レビュー[^\n]{0,40}(?:指摘|直す|修正)',
}

if __name__ == '__main__':
    rows = json.loads((ROOT / 'corpus-paths.json').read_text())
    result = {}
    for name, pattern in PATTERNS.items():
        groups = {k: [] for k in ('A', 'B', '?')}
        hits = {k: [] for k in groups}
        for row in rows:
            body = Path(row['prompt']).read_bytes()
            assert hashlib.sha256(body).hexdigest() == row['sha256'], f"changed prompt id={row['id']}"
            groups[row['class']].append(row['id'])
            if re.search(pattern, body.decode()):
                hits[row['class']].append(row['id'])
        result[name] = {'A': len(groups['A']), 'B': len(groups['B']), 'ambiguous': groups['?'],
                        'false_positive_ids': hits['B'],
                        'false_positive_percent': 100 * len(hits['B']) / len(groups['B']),
                        'false_negative_ids': sorted(set(groups['A']) - set(hits['A']))}
    print(json.dumps(result, ensure_ascii=False, indent=2))
