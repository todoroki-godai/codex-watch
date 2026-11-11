#!/usr/bin/env python3
"""Isolated copies only; retain diffs, execution traces, states and restored hashes."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.tmp/progress-overdue-fix1/mutations'
OUT.mkdir(parents=True, exist_ok=True)
files = ['bin/codex-impl', 'bin/codex-watch', 'bin/codex-status', 'tests/test_progress_overdue.py']
snapshot = {f: (ROOT / f).read_bytes() for f in files}
backup = OUT / 'backup'
for f, data in snapshot.items():
    p = backup / f
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
cases = [
    ('positive-equivalent', 'bin/codex-watch', '> 2 * int(estimate) * 60', '> int(estimate) * 120', 'test_boundary', True),
    ('01-remove-overdue', 'bin/codex-watch', 'if [[ ! -e "$OVERDUE_FILE" ]]; then', 'if false; then', 'test_boundary', False),
    ('02-one-times', 'bin/codex-watch', '> 2 * int(estimate) * 60', '> 1 * int(estimate) * 60', 'test_boundary', False),
    ('03-watch-start', 'bin/codex-watch', '"$ESTIMATE_MIN" "$STARTED_AT" "$now"', '"$ESTIMATE_MIN" "$started" "$now"', 'test_run_start_and_repeat', False),
    ('04-remove-marker-check', 'bin/codex-watch', 'if [[ ! -e "$OVERDUE_FILE" ]]; then', 'if true; then', 'test_marker_keeps_watching', False),
    ('05-disable-input-check', 'bin/codex-impl', "if not re.fullmatch(r'-?[0-9]+', value):", 'if False:', 'test_estimate_record', False),
    ('06-swap-priority', 'bin/codex-impl', "value = os.environ.get('CODEX_IMPL_ESTIMATE_MIN')", 'value = None', 'test_estimate_record', False),
    ('07-inclusive-boundary', 'bin/codex-watch', '> 2 * int(estimate) * 60', '>= 2 * int(estimate) * 60', 'test_boundary', False),
    ('08-exit-order', 'bin/codex-watch', 'if ! kill -0 "$PID" 2>/dev/null; then', 'if false; then', 'test_exit_wins', False),
    ('09-remove-inline', 'bin/codex-impl', "re.search(label + r'約?([0-9]+)\\s*分', body)", 'None', 'test_estimate_record', False),
    ('10-remove-fullwidth', 'bin/codex-impl', '見込み[:：]', '見込み:', 'test_estimate_record', False),
    ('11-swap-heading-priority', 'bin/codex-impl', "heading = re.search(r'^(?:## )?' + label + r'(.*)$', body, re.MULTILINE)", 'heading = None', 'test_estimate_record', False),
    ('positive-parser-equivalent', 'bin/codex-impl', "heading = re.search(r'^(?:## )?' + label + r'(.*)$', body, re.MULTILINE)", "heading = re.search(r'(?m)^(?:## )?' + label + r'(.*)$', body)", 'test_estimate_record', True),
]
results = []
for name, filename, old, new, select, green in cases:
    folder = OUT / name
    folder.mkdir(exist_ok=True)
    tree = folder / 'source'
    for directory in ('bin', 'lib'):
        shutil.copytree(ROOT / directory, tree / directory, dirs_exist_ok=True)
    original = (tree / filename).read_text()
    assert original.count(old) == 1, (name, old)
    changed = original.replace(old, new)
    (folder / 'invariant.diff').write_text(''.join(difflib.unified_diff(
        original.splitlines(True), changed.splitlines(True), fromfile=filename, tofile=filename)))
    (tree / filename).write_text(changed)
    env = dict(os.environ, CODEX_OVERDUE_TEST_ROOT=str(tree.resolve()),
               CODEX_OVERDUE_TRACE_DIR=str((folder / 'execution').resolve()), PYTHONDONTWRITEBYTECODE='1')
    r = subprocess.run([sys.executable, '-m', 'pytest', str(ROOT / 'tests/test_progress_overdue.py'),
                        '-q', '--tb=short', '-k', select, '--basetemp', str(folder / 'tmp')],
                       env=env, capture_output=True, text=True, timeout=180)
    (folder / 'execution-pytest.log').write_text(r.stdout + r.stderr)
    (tree / filename).write_text(original)
    assert (tree / filename).read_text() == original
    ok = r.returncode == (0 if green else 1)
    result = dict(name=name, expected='green' if green else 'red', exit=r.returncode, ok=ok,
                  summary=r.stdout.splitlines()[-1], restored=True)
    results.append(result)
    (OUT / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result), flush=True)
    if not ok:
        sys.exit(1)
assert all((ROOT / f).read_bytes() == data for f, data in snapshot.items())
(OUT / 'restoration.json').write_text(json.dumps(
    {f: hashlib.sha256(data).hexdigest() for f, data in snapshot.items()}, indent=2) + '\n')
