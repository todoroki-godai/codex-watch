#!/usr/bin/env python3
"""Mutate isolated copies, prove changed lines executed, require assertion failures."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.tmp/rge-mutations'
CASES = [
    ('missing-condition', "for name in FIELDS), '完成条件", "for name in FIELDS if name != '信頼境界'), '完成条件", 'test_missing_field'),
    ('zero-findings', "require(count != 0 or addition.startswith('あり: ')", 'require(True', 'test_zero_without_addition'),
    ('two-repairs', 'require(not (first & second)', 'require(True', 'test_two_repairs_stop'),
    ('unreadable-pass', "raise Indeterminate('受付拒否: 前巡または依頼文を判定できません (' + type(exc).__name__ + ')') from exc", "return 'なし'", 'test_unreadable_previous'),
    ('wrong-version-receipt', "require(receipt.status == 'ok'", 'require(True', 'test_bad_history and receipt'),
    ('running-previous', "require(False, '前巡が実行中または終了未確認です')", "require(True, '前巡が実行中または終了未確認です')", 'test_running_previous'),
    ('fenced-headings', '        if fence:', '        if False:', 'test_heading_transforms and fence'),
    ('subdivide-family', 'all(tag in FAMILIES for tag in tags)', "all(tag.split('.')[0] in FAMILIES for tag in tags)", 'test_family_subdivision'),
    ('duplicate-result-key', "require(key not in out, '前巡JSONの重複キー')", "require(True, '前巡JSONの重複キー')", 'test_bad_history and duplicate_json'),
    ('duplicate-state-key', 'bool(sep) and key not in result', 'bool(sep)', 'test_bad_history and broken_state'),
]
results = []
for name, old, new, select in CASES:
    folder = OUT / name
    if folder.exists(): shutil.rmtree(folder)
    folder.mkdir(parents=True)
    for sub in ('bin', 'lib', 'templates'):
        shutil.copytree(ROOT / sub, folder / sub, ignore=shutil.ignore_patterns('__pycache__'))
    path = folder / 'lib/review_admission.py'
    original = path.read_text()
    assert original.count(old) == 1, (name, original.count(old))
    line = original[:original.index(old)].count('\n') + 1
    path.write_text(original.replace(old, new))
    assert path.read_text() != original and new in path.read_text()
    trace = folder / 'executed.jsonl'
    command = [sys.executable, '-m', 'pytest', str(ROOT / 'tests/test_review_admission.py'),
               '-q', '--tb=short', '-k', select, '--basetemp', str(folder / 'tmp')]
    env = dict(os.environ, RGE_TEST_ROOT=str(folder), RGE_TRACE=str(trace), PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run(command, env=env, text=True, capture_output=True, timeout=30)
    log = result.stdout + result.stderr
    (folder / 'pytest.log').write_text(log)
    executed = set()
    if trace.exists():
        for entry in trace.read_text().splitlines(): executed.update(json.loads(entry))
    ok = result.returncode == 1 and line in executed and ('DID NOT RAISE' in log or 'AssertionError' in log) and 'ERROR ' not in log
    record = dict(name=name, ok=ok, changed_line=line, executed=line in executed,
                  transformation={'old':old, 'new':new}, exit=result.returncode,
                  command=command, summary=log.strip().splitlines()[-1])
    results.append(record)
    print(json.dumps(record, ensure_ascii=False), flush=True)
(OUT / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
sys.exit(0 if all(r['ok'] for r in results) else 1)
