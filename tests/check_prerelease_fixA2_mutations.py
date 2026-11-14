"""Reproduce A2's mutations from a committed archive; no live source is changed.

Run: python3 tests/check_prerelease_fixA2_mutations.py
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
import pytest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.tmp/fixA2/mutations'
# Child processes also need pytest's installation directory on PYTHONPATH.
CASES = [
    ('N1-union-restored', 'lib/round_gate.py',
     '    decision = decide(total, body)\n    evidence = {}',
     "    from prerelease import history\n    total = max(total, history(body, state_dir, target.key(), strict=False) + 1)\n    decision = decide(total, body)\n    evidence = {}",
     'ordinary_parallel_round2', 'total = max(total, history(', '① restore removed union'),
    ('N2-parser-stop-restored', 'lib/round_gate.py',
     '    decision = decide(total, body)\n    evidence = {}',
     "    from prerelease import history\n    history(body, state_dir, target.key(), strict=False)\n    decision = decide(total, body)\n    evidence = {}",
     'ordinary_prose_round2', 'history(body, state_dir, target.key(), strict=False)', '② ordinary prose stops'),
    ('N3-cap-swapped', 'lib/prerelease.py',
     "3 <= total <= data['total_cap'] <= 5", "3 <= data['total_cap'] <= total <= 5",
     'round_cap_boundaries', "if type(data.get('total_cap')) is not int", '③ swap cap and round'),
    ('N4-blob-disabled', 'lib/prerelease.py',
     "if git(workdir, 'rev-parse', f'{ref}:{path}') != expected:", 'if False:',
     'each_registered_blob_change', 'if False:', '④ disable blob comparison'),
    ('N5-conflict-removed', 'lib/prerelease.py',
     "raise ConflictingHistory('同じ発注IDの履歴内容が矛盾しています')", 'pass',
     'conflicting_id', 'pass', '① undercount conflicting identity'),
    ('N6-malformed-ignored', 'lib/prerelease.py',
     "raise ValueError('巡の履歴に解釈できない行があります')", 'pass',
     'exception_bad_history_falls_back and malformed', 'pass', '② undercount broken row'),
    ('E1-output-corrupted', 'lib/round_gate.py',
     '"history_round": total if evidence else None,', '"history_round": total,',
     'ordinary_parallel_round2 or ordinary_prose_round2', '"history_round": total,',
     'extra: output contract corruption'),
    ('E2-human-precedence-inverted', 'lib/round_gate.py',
     'if decision.status != "pass" and prerelease_record:', 'if prerelease_record:',
     'human_approval_with_bad_history', 'evidence = evaluate(target,',
     'extra: evaluate exception before accepting human approval'),
    ('positive-equivalent-call', 'lib/round_gate.py',
     '    decision = decide(total, body)\n    evidence = {}',
     '    decision = decide(total, body=body)\n    evidence = {}',
     'ordinary_parallel_round2 or ordinary_prose_round2 or human_approval_with_bad_history',
     'decision = decide(total, body=body)', 'positive'),
]

def main():
    assert not subprocess.check_output(['git', 'diff', 'HEAD'], cwd=ROOT).strip(), 'tracked originals must match committed HEAD'
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
        env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(folder), str(Path(pytest.__file__).resolve().parents[1]))), PYTHONDONTWRITEBYTECODE='1',
                   A2_ANCHOR=anchor, A2_FILE=relative, A2_TRACE=str(trace),
                   GIT_CEILING_DIRECTORIES=str(folder))
        command = [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                   '--basetemp=' + str(folder / 'temp'), 'tests/test_prerelease.py', 'tests/test_prerelease_implA3.py', 'tests/test_prerelease_fixA.py', 'tests/test_prerelease_fixA2.py', '-k', selection]
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
    assert not subprocess.check_output(['git', 'diff', 'HEAD'], cwd=ROOT).strip()


if __name__ == '__main__': main()
