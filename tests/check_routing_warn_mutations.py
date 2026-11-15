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
OUT = ROOT / '.tmp/review-routing-warn/mutations'
OUT.mkdir(parents=True, exist_ok=True)
HELPER = 'lib/routing_warn.py'
CLI = 'bin/codex-review'
TEST = 'tests/test_routing_warn.py'
wire = '|| echo "routing警告: 処理失敗（発注継続）" >&2'
cases = [
    ('positive-comment', [(HELPER, 'BUDGET_SECONDS = 30', 'BUDGET_SECONDS = 30  # equivalent')], 'test_dispatch_outcomes and pass', True),
    ('01-stop-verdict', [(HELPER, '    entry = dict(', "    if verdict == 'would_block':\n        raise SystemExit(2)\n    entry = dict("), (CLI, wire, '|| exit 2')], 'test_dispatch_outcomes and blockA', False),
    ('02-stop-failure', [(HELPER, '    entry = dict(', "    if verdict == 'error':\n        raise SystemExit(2)\n    entry = dict("), (CLI, wire, '|| exit 2')], 'test_dispatch_outcomes and error', False),
    ('03-no-record', [(HELPER, 'if os.write(fd, line) != len(line):', 'if len(line) != len(line):')], 'test_dispatch_outcomes and pass', False),
    ('04-no-deadline', [(HELPER, 'if time.monotonic() >= deadline:', 'if False:')], 'test_deadline_boundary', False),
    ('05-numeric-bool', [(HELPER, 'stages[s] is True', 'stages[s] == True')], 'test_invalid_outputs', False),
    ('06-swap-fields', [(HELPER, 'target=target, kind=kind,', 'target=kind, kind=target,')], 'test_record_arguments', False),
    ('07-leak-reason', [(HELPER, "category = '系列・前身記録不足'", 'category = reason')], 'test_dispatch_outcomes and blockA', False),
    ('09-no-worker-cleanup', [(HELPER, 'os.killpg(child.pid, signal.SIGINT)', 'os.killpg(child.pid, 0)')], 'test_detached_worker_cleanup', False),
    ('08-disable-test', [(TEST, "    assert entry['verdict'] == verdict", "    assert entry['verdict'] == verdict if False else True"),
                         (HELPER, "return 'pass', None, ['全段通過']", "return 'would_block', None, ['全段通過']")], 'test_dispatch_outcomes and pass', False),
]
# The disable-test mutation must still be caught by an independent verdict/stage consistency assertion.
# All copies have the current uncommitted implementation as base (commits forbidden for this run).
files = [CLI, HELPER, TEST]
snapshot = {f: (ROOT / f).read_bytes() for f in files}
(OUT / 'baseline.log').write_text(json.dumps({'head': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
    'files': {f: hashlib.sha256(data).hexdigest() for f,data in snapshot.items()}}, indent=2))
results = []
for name, edits, select, positive in cases:
    folder = OUT / name
    tree = folder / 'source'
    for directory in ('bin', 'lib', 'templates', 'tests'):
        shutil.copytree(ROOT / directory, tree / directory, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))
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
def tracer(frame,event,arg):
    if event=='line' and frame.f_code.co_filename in paths and frame.f_lineno in paths[frame.f_code.co_filename]:
        os.write(fd,(json.dumps(dict(file=frame.f_code.co_filename,line=frame.f_lineno))+"\\n").encode())
    return tracer
sys.settrace(tracer)
''')
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(folder.resolve()), ROUTING_WARN_TEST_ROOT=str(tree), PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=os.pathsep.join([str(tracer), *sys.path]))
    argv = [sys.executable,'-m','pytest',str(tree / TEST),'-q','--tb=short','-k',select,'--basetemp',str(folder / 'tmp')]
    r = subprocess.run(argv,cwd=tree,env=env,capture_output=True,text=True,timeout=80)
    (folder / 'execution.log').write_text('argv='+repr(argv)+'\n'+r.stdout+r.stderr)
    landed = [json.loads(line) for line in trace.read_text().splitlines()]
    assert landed, name
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
