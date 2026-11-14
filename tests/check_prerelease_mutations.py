"""Reproduce A's mutations from a committed archive; no live source is changed.

Run: python3 tests/check_prerelease_mutations.py
Full outputs, independent diffs and executed-line witnesses stay in .tmp.
The tracing approach is reused from check_preview_checks_mutations.py.
"""
import difflib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.tmp/implA2-mutations'
CASES = [
    ('M1-other-project', 'lib/prerelease.py',
     "and Path(row['common_dir']).resolve() == common]", 'and True]',
     'authority_boundaries and other-project', 'and True]', '① remove project identity'),
    ('M2-published-policy', 'lib/prerelease.py',
     "if git(workdir, 'rev-parse', f'{ref}:{path}') != expected:", 'if False:',
     'policy_and_history_fail_closed and published-rule', 'if False:', '② ignore policy meaning'),
    ('M3-missing-policy', 'lib/prerelease.py',
     "for path, expected in project['policies'].items():", 'for path, expected in []:',
     'policy_and_history_fail_closed and missing-rule', 'for path, expected in []:', '① remove policy source'),
    ('M4-claim-fail-open', 'lib/round_gate.py',
     'decision.message += "。公開前特例不成立: " + str(error)',
     'decision = Decision("pass", EXIT_PASS, total, "claim accepted")',
     'authority_boundaries and claim-only', 'decision = Decision("pass", EXIT_PASS, total, "claim accepted")', '④ disable rejection'),
    ('M5-body-history-lost', 'lib/prerelease.py',
     'return len(ids) + anonymous + len(legacy_rows)',
     "return len(list(state_dir.glob('*.state')))",
     'completed_history_round3_dispatch or union_body_only_and_state_only',
     "return len(list(state_dir.glob('*.state')))", '② discard body-only events'),
    ('M6-future-time', 'lib/prerelease.py',
     'if when.tzinfo is None or when > now:', 'if when.tzinfo is None:',
     'decision_time', 'if when.tzinfo is None:', '② temporal bypass'),
    ('M7-stale-snapshot', 'lib/round_gate.py',
     'result.get(key) != snapshot.get(key) for key in keys', 'False for key in keys',
     'recheck_and_reservation', 'False for key in keys', '④ disable freshness comparison'),
    ('M8-cap-swap', 'lib/prerelease.py',
     "3 <= total <= data['total_cap'] <= 5", "3 <= data['total_cap'] <= total <= 5",
     'round_cap_boundaries', "if type(data.get('total_cap')) is not int", '③ swap cap and round'),
    ('positive-equivalent-time', 'lib/prerelease.py',
     'if when.tzinfo is None or when > now:', 'if when.tzinfo is None or not when <= now:',
     'completed_history_round3_dispatch or human_approval_ignores_policy_failure or semantic_positive_control or decision_time',
     'if when.tzinfo is None or not when <= now:', 'positive'),
]


def main():
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT).strip(), 'commit first'
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    archive = subprocess.check_output(['git', 'archive', sha], cwd=ROOT)
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for name, relative, old, new, selection, anchor, category in CASES:
        folder = OUT / name
        if folder.exists(): shutil.rmtree(folder)
        folder.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(folder, filter='data')
        path = folder / relative
        before = path.read_text()
        assert before.count(old) == 1, (name, before.count(old))
        after = before.replace(old, new)
        assert before != after
        path.write_text(after)
        delta = ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile=relative, tofile=relative))
        (folder / 'mutation.diff').write_text(delta)
        trace = folder / 'executed.log'
        # An independent Python line tracer: not a marker in the mutated code.
        (folder / 'sitecustomize.py').write_text('''import os,sys,linecache,json
anchor=os.environ['A2_ANCHOR']
def witness(frame,event,arg):
    if event=='line' and frame.f_code.co_filename.endswith(os.environ['A2_FILE']):
        source=linecache.getline(frame.f_code.co_filename,frame.f_lineno).strip()
        if anchor in source:
            data={'file':frame.f_code.co_filename,'line':frame.f_lineno,'source':source}
            for key in ('total','total_for_decision','expected','now','when'):
                if key in frame.f_locals: data[key]=str(frame.f_locals[key])
            if 'data' in frame.f_locals and isinstance(frame.f_locals['data'],dict):
                data['cap']=frame.f_locals['data'].get('total_cap')
                if type(data['cap']) is int and 'total' in frame.f_locals:
                    data['comparison_result']=3 <= data['cap'] <= frame.f_locals['total'] <= 5
            with open(os.environ['A2_TRACE'],'a') as stream: stream.write(json.dumps(data)+'\\n')
    return witness
sys.settrace(witness)
''')
        env = dict(os.environ, PYTHONPATH=str(folder), PYTHONDONTWRITEBYTECODE='1',
                   A2_ANCHOR=anchor, A2_FILE=relative, A2_TRACE=str(trace),
                   GIT_CEILING_DIRECTORIES=str(folder))
        command = [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                   '--basetemp=' + str(folder / 'temp'), 'tests/test_prerelease.py', '-k', selection]
        run = subprocess.run(command, cwd=folder, env=env, capture_output=True, text=True, timeout=180)
        output = run.stdout + run.stderr
        (folder / 'pytest.log').write_text(output)
        hits = trace.read_text().splitlines() if trace.exists() else []
        assert hits, (name, 'changed branch not executed', output)
        expected_exit = 0 if category == 'positive' else 1
        assert run.returncode == expected_exit, (name, 'survivor or unexpected failure', output)
        assert ('passed' if expected_exit == 0 else 'failed') in output
        assert 'ERROR at setup' not in output and 'ERROR collecting' not in output
        results.append(dict(name=name, category=category, sha=sha, exit=run.returncode,
                            command=command, diff_file=str(folder / 'mutation.diff'),
                            execution_hits=len(hits), witness=json.loads(hits[0]),
                            summary=output.strip().splitlines()[-1]))
        print(name, results[-1]['summary'], 'hits=' + str(len(hits)), flush=True)
        # Retain evidence and sources, remove pytest's disposable projects.
        shutil.rmtree(folder / 'temp', ignore_errors=True)
    (OUT / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')
    assert not subprocess.check_output(['git', 'diff'], cwd=ROOT).strip()
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT).strip()


if __name__ == '__main__': main()
