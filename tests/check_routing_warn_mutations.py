#!/usr/bin/env python3
"""Run actual mutations in local isolated copies; never mutate the checkout/index."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.tmp/review-routing-warn-fix1/mutations'
OUT.mkdir(parents=True, exist_ok=True)
HELPER = 'lib/routing_warn.py'
CLI = 'bin/codex-review'
TEST = 'tests/test_routing_warn.py'
cases = [
    ('positive-comment', [(HELPER, 'BUDGET_SECONDS = 30', 'BUDGET_SECONDS = 30  # equivalent')], 'test_dispatch_outcomes and pass', True),
    ('01-no-whole-bound', [(HELPER, 'child.wait(timeout=BUDGET_SECONDS + 1)', 'child.wait(timeout=None)')], 'test_whole_budget', False),
    ('02-no-sigint-reset', [(HELPER, 'signal.signal(signal.SIGINT, signal.SIG_DFL)', 'signal.signal(signal.SIGINT, signal.SIG_IGN)')], 'test_detached_worker_cleanup', False),
    ('03-short-write', [(HELPER, 'line = line[written:]', "line = b''")], 'test_short_write', False),
    ('04-weaken-bound', [(HELPER, 'child.wait(timeout=BUDGET_SECONDS + 1)', 'child.wait(timeout=BUDGET_SECONDS + 100)')], 'test_whole_budget', False),
    ('05-swap-fields', [(HELPER, 'target=target, kind=kind,', 'target=kind, kind=target,')], 'test_record_arguments', False),
    ('06-disable-test', [(TEST, "    assert [r['dispatch_id'] for r in rows] ==", "    assert True or [r['dispatch_id'] for r in rows] =="),
                         (HELPER, 'line = line[written:]', "line = b''")], 'test_short_write', False),
    ('07-zero-write-loop', [(HELPER, 'if written <= 0:', 'if written < 0:')], 'test_short_write', False),
    ('08-aggregate-stop', [('README.md', '        broken += 1', '        raise')], 'test_readme_aggregation', False),
    ('09-no-record', [(HELPER, 'written = os.write(fd, line)', 'written = len(line)')], 'test_dispatch_outcomes and pass', False),
]
# The disable-test mutation must still be caught by an independent write-progress assertion.
# All copies have the current uncommitted implementation as base (commits forbidden for this run).
files = [CLI, HELPER, TEST, 'README.md', 'tests/check_routing_warn_mutations.py']
snapshot = {f: (ROOT / f).read_bytes() for f in files}
(OUT / 'baseline.log').write_text(json.dumps({'head': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
    'files': {f: hashlib.sha256(data).hexdigest() for f,data in snapshot.items()}}, indent=2))
results = []
for name, edits, select, positive in cases:
    folder = OUT / name
    tree = folder / 'source'
    for directory in ('bin', 'lib', 'templates', 'tests'):
        shutil.copytree(ROOT / directory, tree / directory, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(ROOT / 'README.md', tree / 'README.md')
    changes = {}
    for filename, old, new in edits:
        path = tree / filename
        original = path.read_text()
        assert old in original, (name, old)
        changed = original.replace(old, new)
        path.write_text(changed)
        changes[filename] = (original, changed)
    diff = ''.join(''.join(difflib.unified_diff(a.splitlines(True),b.splitlines(True),fromfile=f,tofile=f)) for f,(a,b) in changes.items())
    assert diff
    (folder / 'invariant.diff.log').write_text(diff)
    touched = {}
    for f,(a,b) in changes.items():
        touched[str((tree / f).resolve())] = sorted({i+1 for tag,_,_,j,k in difflib.SequenceMatcher(None,a.splitlines(),b.splitlines()).get_opcodes() if tag!='equal' for i in range(j,k)})
    tracer = folder / 'tracer'
    tracer.mkdir(exist_ok=True)
    trace = folder / 'landing.log'
    trace.write_text('')
    (tracer / 'sitecustomize.py').write_text(f'''import sys,os,json
paths={touched!r}
fd=os.open({str(trace)!r},os.O_WRONLY|os.O_APPEND)
write=os.write
def tracer(frame,event,arg):
    if event=='line' and frame.f_code.co_filename in paths and frame.f_lineno in paths[frame.f_code.co_filename]:
        write(fd,(json.dumps(dict(file=frame.f_code.co_filename,line=frame.f_lineno))+"\\n").encode())
    return tracer
sys.settrace(tracer)
''')
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(folder.resolve()), ROUTING_WARN_TEST_ROOT=str(tree), PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=os.pathsep.join([str(tracer), *sys.path]))
    argv = [sys.executable,'-m','pytest',str(tree / TEST),'-q','--tb=short','-k',select,'--basetemp',str(folder / 'tmp')]
    r = subprocess.run(argv,cwd=tree,env=env,capture_output=True,text=True,timeout=80)
    (folder / 'execution.log').write_text('argv='+repr(argv)+'\n'+r.stdout+r.stderr)
    landed = [json.loads(line) for line in trace.read_text().splitlines()]
    assert landed, name
    for filename in changes:
        assert any(row['file'] == str((tree / filename).resolve()) for row in landed), (name, filename)
    # At least one changed product/test line was read by the selected test process.
    ok = r.returncode == (0 if positive else 1)
    results.append(dict(name=name,positive=positive,exit=r.returncode,landed=len(landed),ok=ok))
    (OUT / 'results.log').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(results[-1]),flush=True)
    # Restore the copy and prove byte equality to the fixed implementation snapshot.
    for f,data in snapshot.items():
        (tree / f).write_bytes(data)
        assert (tree / f).read_bytes()==data
    shutil.rmtree(tree)
    shutil.rmtree(folder / 'tmp', ignore_errors=True)
    if not ok:
        sys.exit(1)
assert all((ROOT / f).read_bytes()==data for f,data in snapshot.items())
(OUT / 'restoration.log').write_text('original checkout bytes unchanged; all isolated sources restored and removed\n')
