"""HEAD archive + explicit uncommitted fix overlay; never mutate the originals.

The fixA request forbids commits. Preserve the overlay independently of each
mutation diff, with line traces and pytest output as separate evidence.
"""
import difflib
import hashlib
import importlib.util
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
OUT = ROOT / '.tmp/fixA/mutations'
PRODUCT = ('lib/prerelease.py', 'lib/round_gate.py')
TESTS = ('tests/test_prerelease.py', 'tests/test_prerelease_fixA.py')


def main():
    before = subprocess.check_output(['git', 'diff', '--binary'], cwd=ROOT)
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    archive = subprocess.check_output(['git', 'archive', sha], cwd=ROOT)
    spec = importlib.util.spec_from_file_location('prior', ROOT / 'tests/check_prerelease_implA3_mutations.py')
    prior = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prior)
    cases = prior.CASES + [
        ('F1-conflict-removed', 'lib/prerelease.py',
         "raise ConflictingHistory('同じ発注IDの履歴内容が矛盾しています')", 'pass',
         'conflicting_id', 'pass', '① remove conflict rejection'),
        ('F2-history-error-ignored', 'lib/round_gate.py',
         'if history_error and not (', 'if False and not (',
         'malformed_history', 'if False and not (', '② lose body-only rounds'),
        ('F3-authority-swapped', 'lib/prerelease.py',
         "saved.get('authority') != 'project_prerelease'", "saved.get('authority') != 'ordinary'",
         'ordinary_empty_evidence or saved_exception_cap', "saved.get('authority') != 'ordinary'", '③ swap authority'),
        ('F4-conflict-comparison-disabled', 'lib/prerelease.py',
         'rows_by_id[match[1]] != fingerprint', 'fingerprint != fingerprint',
         'conflicting_id', 'fingerprint != fingerprint', '④ disable comparison'),
        ('F5-approval-without-cap', 'lib/round_gate.py',
         'if history_error and not (total >= 3 and decision.status == "pass"',
         'if history_error and not (total >= 3 or decision.status == "pass"',
         'malformed_history', 'if history_error and not (total >= 3 or', 'extra: widen boolean authorization'),
        ('F6-sha-only-identity', 'lib/prerelease.py',
         'rows_by_id[match[1]] != fingerprint', 'rows_by_id[match[1]][3] != fingerprint[3]',
         'conflicting_id', 'rows_by_id[match[1]][3] != fingerprint[3]', 'extra: project identity onto SHA only'),
        ('F7-reservation-authority-lost', 'lib/round_gate.py',
         "authority={result['authority']}\\n", '',
         'reservation_keeps_authority', 'stream.write(f"run_id=', '① lose saved reservation authority'),
        ('positive-fixA', 'lib/prerelease.py',
         'rows_by_id[match[1]] != fingerprint', 'not rows_by_id[match[1]] == fingerprint',
         'identical_duplicate or normal_human or ordinary_empty_evidence',
         'not rows_by_id[match[1]] == fingerprint', 'positive'),
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'fix-overlay.diff').write_bytes(before)
    results = []
    for name, relative, old, new, selection, anchor, category in cases:
        folder = OUT / name
        if folder.exists(): shutil.rmtree(folder)
        folder.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(folder, filter='data')
        for path in PRODUCT + TESTS:
            shutil.copy2(ROOT / path, folder / path)
        path = folder / relative
        source = path.read_text()
        assert source.count(old) == 1, (name, source.count(old))
        changed = source.replace(old, new)
        path.write_text(changed)
        (folder / 'mutation.diff').write_text(''.join(difflib.unified_diff(
            source.splitlines(True), changed.splitlines(True), fromfile=relative, tofile=relative)))
        trace = folder / 'executed.log'
        (folder / 'sitecustomize.py').write_text('''import os,sys,linecache,json
def witness(frame,event,arg):
    if event=='line' and frame.f_code.co_filename.endswith(os.environ['TRACE_FILE']):
        source=linecache.getline(frame.f_code.co_filename,frame.f_lineno).strip()
        if os.environ['TRACE_ANCHOR'] in source:
            with open(os.environ['TRACE_OUT'],'a') as out:
                out.write(json.dumps(dict(file=frame.f_code.co_filename,line=frame.f_lineno,source=source))+'\\n')
    return witness
sys.settrace(witness)
''')
        env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(folder), str(Path(pytest.__file__).resolve().parents[1]))),
            PYTHONDONTWRITEBYTECODE='1', TRACE_FILE=relative, TRACE_ANCHOR=anchor, TRACE_OUT=str(trace),
            GIT_CEILING_DIRECTORIES=str(folder))
        command = [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
            '--basetemp=' + str(folder / 'temp'), 'tests/test_prerelease.py',
            'tests/test_prerelease_implA3.py', 'tests/test_prerelease_fixA.py', '-k', selection]
        run = subprocess.run(command, cwd=folder, env=env, capture_output=True, text=True, timeout=180)
        output = run.stdout + run.stderr
        (folder / 'pytest.log').write_text(output)
        hits = trace.read_text().splitlines() if trace.exists() else []
        expected = 0 if category == 'positive' else 1
        assert hits and run.returncode == expected, (name, run.returncode, output)
        assert ('passed' if expected == 0 else 'failed') in output
        assert 'ERROR at setup' not in output and 'ERROR collecting' not in output
        results.append(dict(name=name, category=category, base_sha=sha,
            overlay_sha256=hashlib.sha256(before).hexdigest(), exit=run.returncode,
            execution_hits=len(hits), command=command, summary=output.strip().splitlines()[-1]))
        print(name, results[-1]['summary'], 'hits=' + str(len(hits)), flush=True)
        shutil.rmtree(folder / 'temp', ignore_errors=True)
    (OUT / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')
    assert subprocess.check_output(['git', 'diff', '--binary'], cwd=ROOT) == before


if __name__ == '__main__': main()
