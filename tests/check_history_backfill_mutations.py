"""Committed-archive mutations with separate diffs and executed-line witnesses.

Run after committing: python3 tests/check_history_backfill_mutations.py
No LLM, network, live state or original source mutations.
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
OUT = ROOT / '.tmp/history-backfill-mutations'
FILE = 'lib/history_backfill.py'
CASES = [
    ('N1-remove-output', "        lines[i] = content + f' <!-- dispatch_id={found[0]} -->' + ending",
     '        lines[i] = content + ending', 'real_history_gate', 'lines[i] = content + ending', '①守る処理を消す・全行未補完'),
    ('N2-wrong-run', "        lines[i] = content + f' <!-- dispatch_id={found[0]} -->' + ending",
     "        lines[i] = content + ' <!-- dispatch_id=another-run -->' + ending", 'real_history_gate',
     "lines[i] = content + ' <!-- dispatch_id=another-run -->'", '②意味を壊す・別run'),
    ('N3-swap-id', "        lines[i] = content + f' <!-- dispatch_id={found[0]} -->' + ending",
     "        lines[i] = content + f' <!-- dispatch_id={states[-1][1]} -->' + ending", 'real_history_gate',
     'lines[i] = content +', '③入れ替える・2行のIDを取り違える'),
    ('N4-disable-status', '        return 1 if warnings else 0', '        return 0',
     'description or ambiguous', 'return 0', '④検査そのものを無効化・成功合図'),
    ('N5-partial-only', '    for i, key in rows:', '    for i, key in rows[:1]:',
     'real_history_gate', 'for i, key in rows[:1]:', '一部の行だけ補う'),
    ('N6-ignore-target', "        if data.get('review_target') != target:", '        if False:',
     'ambiguous and other-target', 'if False:', '別種の回避1・対象の境界を除去'),
    ('N7-tolerate-duplicate-key', "        if any('=' not in line for line in raw) or len(keys) != len(set(keys)):",
     "        if any('=' not in line for line in raw):", 'bad_state and duplicate-key',
     "if any('=' not in line for line in raw):", '別種の回避2・state上書きキー許容'),
    ('N8-reuse-id', 'or ids[found[0]] != 1 or found[0] in used):', 'or ids[found[0]] != 1):',
     'ambiguous and used-id', 'if (counts[key] != 1', '使用済みID再利用'),
    ('N9-invalid-id', 'or not RE_ID.fullmatch(found[0])', 'or False', 'ambiguous and invalid-id', 'or False', '別種の回避3・ID書式を無視'),
    ('N10-existing-id', "        if '<!-- dispatch_id=' in line:", '        if False:', 'existing', 'if False:', '別種の回避4・既存IDの保護を無効化'),
    ('P1-equivalent-status', '        return 1 if warnings else 0', '        return int(bool(warnings))',
     '', 'return int(bool(warnings))', 'positive'),
    ('P2-equivalent-key-order', "        states.append((key, data.get('run_id', '')))",
     "        states.insert(0, (key, data.get('run_id', '')))", '', 'states.insert(0', 'positive'),
]


def main():
    assert not subprocess.check_output(['git', 'diff', 'HEAD'], cwd=ROOT).strip()
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    archive = subprocess.check_output(['git', 'archive', sha], cwd=ROOT)
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for name, old, new, selection, anchor, category in CASES:
        folder = OUT / name
        if folder.exists(): shutil.rmtree(folder)
        folder.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(folder, filter='data')
        path = folder / FILE
        before = path.read_text()
        assert before.count(old) == 1, (name, before.count(old))
        after = before.replace(old, new)
        delta = ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                              fromfile=FILE, tofile=FILE))
        assert delta and before != after
        path.write_text(after)
        (folder / 'mutation.diff').write_text(delta)
        trace = folder / 'executed.jsonl'
        # Independent line tracer also loads in CLI subprocesses.
        (folder / 'sitecustomize.py').write_text('''import sys,os,linecache,json
seen=set()
def witness(frame,event,arg):
    if event=='line' and frame.f_code.co_filename.endswith('lib/history_backfill.py'):
        source=linecache.getline(frame.f_code.co_filename,frame.f_lineno).strip()
        if os.environ['HB_ANCHOR'] in source and (frame.f_code.co_filename,frame.f_lineno) not in seen:
            seen.add((frame.f_code.co_filename,frame.f_lineno))
            data={'file':frame.f_code.co_filename,'line':frame.f_lineno,'source':source}
            for key in ('key','found','warnings','target','i'):
                if key in frame.f_locals: data[key]=frame.f_locals[key]
            with open(os.environ['HB_TRACE'],'a') as stream: stream.write(json.dumps(data, default=repr)+'\\n')
    return witness
sys.settrace(witness)
''')
        env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(folder), str(Path(pytest.__file__).resolve().parents[1]))),
                   PYTHONDONTWRITEBYTECODE='1', HB_ANCHOR=anchor, HB_TRACE=str(trace),
                   GIT_CEILING_DIRECTORIES=str(folder))
        command = [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                   '--basetemp=' + str(folder / 'temp'), 'tests/test_history_backfill.py']
        if selection: command += ['-k', selection]
        run = subprocess.run(command, cwd=folder, env=env, capture_output=True, text=True, timeout=120)
        output = run.stdout + run.stderr
        (folder / 'pytest.log').write_text(output)
        hits = trace.read_text().splitlines() if trace.exists() else []
        assert hits, (name, 'no executed branch', output)
        expected = 0 if category == 'positive' else 1
        assert run.returncode == expected, (name, 'survivor or unexpected failure', output)
        assert ('passed' if expected == 0 else 'failed') in output
        assert 'ERROR at setup' not in output and 'ERROR collecting' not in output
        results.append(dict(name=name, category=category, sha=sha, exit=run.returncode,
                            diff_file=str(folder / 'mutation.diff'), execution_file=str(trace),
                            execution_hits=len(hits), witness=json.loads(hits[0]),
                            command=command, summary=output.strip().splitlines()[-1]))
        print(name, results[-1]['summary'], 'hits=' + str(len(hits)), flush=True)
        shutil.rmtree(folder / 'temp', ignore_errors=True)
    (OUT / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')
    assert not subprocess.check_output(['git', 'diff'], cwd=ROOT).strip()
    assert not subprocess.check_output(['git', 'diff', 'HEAD'], cwd=ROOT).strip()


if __name__ == '__main__': main()
