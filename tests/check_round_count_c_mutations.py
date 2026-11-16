"""Snapshot mutations, independent diffs and executed-line evidence (impl2)."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.tmp/round-count-c-impl2-mutations'
TEST_FILES = ['tests/test_round_count_c.py', 'tests/test_prerelease.py']
CASES = [
 ('N1-filter-removed','lib/round_gate.py',
  'ledger_head_shas_for_target(state_dir, target_key, kind_label=kind_label):',
  'ledger_head_shas_for_target(state_dir, target_key):', 'boundary or design3_code1 or design_predecessor_filter',
  'for _started, head in ledger_head_shas_for_target', '① remove kind propagation'),
 ('N2-all-kinds-support','lib/round_gate.py',
  '            if completed < n:',
  '''            completed = sum(_target_total_rounds(target, state_dir, fetch_body, env_predecessors, None, kind_label=k, _validate_approvals=False) for k in ("設計", "コード"))
            if completed < n:''', 'attribution_deficit', 'if completed < n:', '② mixed support'),
 ('N3-attribution-swapped','lib/round_gate.py',
  'attributed = next(iter(kinds))', 'attributed = "コード" if "設計" in kinds else "設計"',
  'boundary', 'attributed =', '③ swap kind'),
 ('N4-unattributed-allowed','lib/round_gate.py',
  'raise _UnsupportedApproval(f"{key}: 承認N={n}を一意に帰属できません（候補種別{len(kinds)}）")',
  'return ledger_total', 'invalid', 'return ledger_total', '④ disable attribution guard'),
 ('N5-forged-separator','lib/prerelease.py',
  "has_id = 'dispatch_id=' in line", "has_id = False\n        if line.startswith('|---'): continue",
  'history_invalid', "if line.startswith('|---'):", '④ ignore forged separator'),
 ('N6-prose-rejected','lib/prerelease.py',
  "or not line.startswith('|')):", "):", 'history_heads', 'if not has_id and', '① remove prose skip'),
 ('N7-count-dispatches','lib/prerelease.py',
  '    return len(heads)', '    return len(records)', 'history_heads', 'return len(records)', 'extra1 replace set cardinality with dispatch count'),
 ('N8-max-approval-only','lib/round_gate.py',
  'for n in sorted(set(parse_approval_rounds(body))):',
  'for n in sorted(set(parse_approval_rounds(body)))[-1:]:', 'all_approvals', 'for n in sorted', 'extra2 project multiple approvals onto maximum'),
 ('N9-pred-kind-lost','lib/round_gate.py',
  'None, None, kind_label=kind_label,', 'None, None, kind_label="コード",',
  'design_predecessor_filter', 'pred_total +=', '① recursive propagation removed'),
 ('N10-reservation-guard','lib/round_gate.py',
  "if saved.get('review_target') == args.target:", "if False:",
  'recheck_and_reservation or simultaneous_reservations', 'if False:', '④ disable outstanding reservation check'),
 ('N11-no-legacy-fallback','lib/round_gate.py',
  'pending_new_head, kind_label=None), True',
  'pending_new_head, kind_label=kind_label, _validate_approvals=False), True',
  'invalid or attribution_deficit', 'pending_new_head, kind_label=kind_label, _validate_approvals=False)', '③ use kind count on fallback'),
 ('N12-pending-support','lib/round_gate.py',
  'target, state_dir, fetch_body, env_predecessors, None,\n                kind_label=attributed',
  'target, state_dir, fetch_body, env_predecessors, pending_new_head,\n                kind_label=attributed',
  'pending_cannot_support', 'kind_label=attributed', 'extra3 future work as completed evidence'),
 ('N13-unicode-round','lib/round_gate.py',
  're.fullmatch(r"[0-9]+", recorded)', 're.fullmatch(r"\\d+", recorded)',
  'invalid', 'if not re.fullmatch', 'extra4 normalize non-ASCII candidate number'),
 ('P1-equivalent-comparison','lib/round_gate.py',
  'if completed < n:', 'if n > completed:', 'boundary', 'if n > completed:', 'positive'),
 ('P2-equivalent-head-set','lib/prerelease.py',
  'heads.add(pending_head)', 'heads.update([pending_head])', 'history_heads', 'heads.update', 'positive'),
]


def main():
    baseline_diff = subprocess.check_output(['git','diff','HEAD'])
    baseline_status = subprocess.check_output(['git','status','--porcelain'])
    sha = subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    files = subprocess.check_output(['git','ls-files','-z']).decode().split('\0')
    snapshot = {name: (ROOT/name).read_bytes() for name in files if name and (ROOT/name).is_file()}
    manifest = {name: hashlib.sha256(data).hexdigest() for name,data in snapshot.items()}
    OUT.mkdir(exist_ok=True)
    (OUT/'snapshot.log').write_text(json.dumps(dict(base_sha=sha,files=manifest),indent=2))
    results=[]
    for name,relative,old,new,selection,anchor,category in CASES:
        folder=OUT/name
        if folder.exists(): shutil.rmtree(folder)
        folder.mkdir()
        for filename,data in snapshot.items():
            destination = folder/filename
            destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_bytes(data)
            destination.chmod((ROOT/filename).stat().st_mode)
        # Files are copied before mutation; no stash or working-tree mutation.

        collect_command=[sys.executable,'-m','pytest','--collect-only','-q',*TEST_FILES,'-k',selection]
        collected=subprocess.run(collect_command,cwd=folder,capture_output=True,text=True,timeout=60)
        (OUT/(name+'.collection.log')).write_text(collected.stdout+collected.stderr)
        expected_ids={line.strip() for line in collected.stdout.splitlines() if line.startswith('tests/') and '::' in line}
        assert collected.returncode==0 and expected_ids,(name,'no baseline tests collected')
        path=folder/relative;before=path.read_text()
        # N1 deliberately targets the predecessor helper, not ledger_own_round.
        if name=='N1-filter-removed':
            start=before.index('def ledger_own_round_for_predecessor')
            after=before[:start]+before[start:].replace(old,new,1)
        else:
            assert before.count(old)==1,(name,before.count(old))
            after=before.replace(old,new)
        delta=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=relative,tofile=relative))
        assert delta and before != after
        path.write_text(after)
        (OUT/(name+'.diff.log')).write_text(delta)
        trace=OUT/(name+'.executed.log')
        if trace.exists():trace.unlink()
        (folder/'sitecustomize.py').write_text('''import sys,os,linecache,json
seen=set()
def witness(frame,event,arg):
    if event=='line' and frame.f_code.co_filename.endswith(os.environ['C_FILE']):
        source=linecache.getline(frame.f_code.co_filename,frame.f_lineno).strip()
        if os.environ['C_ANCHOR'] in source and (frame.f_code.co_filename,frame.f_lineno) not in seen:
            seen.add((frame.f_code.co_filename,frame.f_lineno))
            values={k:repr(frame.f_locals[k]) for k in ('kind_label','n','completed','line','kinds','recorded','pending_new_head','ledger_total') if k in frame.f_locals}
            with open(os.environ['C_TRACE'],'a') as out:out.write(json.dumps(dict(file=frame.f_code.co_filename,line=frame.f_lineno,source=source,values=values))+'\\n')
    return witness
sys.settrace(witness)
''')
        reports=OUT/(name+'.reports.log')
        if reports.exists(): reports.unlink()
        (folder/'c_mutation_reports.py').write_text("import json,os\ndef pytest_runtest_logreport(report):\n    if report.when == 'call':\n        with open(os.environ['C_REPORT'],'a') as out: out.write(json.dumps(dict(nodeid=report.nodeid,outcome=report.outcome))+'\\n')\n")
        env=dict(os.environ,PYTHONPATH=os.pathsep.join([str(folder), str(Path(pytest.__file__).resolve().parents[1]), os.environ.get("PYTHONPATH", "")]),PYTHONDONTWRITEBYTECODE='1',C_FILE=relative,C_ANCHOR=anchor,C_TRACE=str(trace),C_REPORT=str(reports),PYTEST_PLUGINS='c_mutation_reports',GIT_CEILING_DIRECTORIES=str(folder))
        command=[sys.executable,'-m','pytest','-q','-rA','-p','no:cacheprovider',*TEST_FILES,'-k',selection,'--basetemp='+str(folder/'temp')]
        run=subprocess.run(command,cwd=folder,env=env,capture_output=True,text=True,timeout=180)
        output=run.stdout+run.stderr;(OUT/(name+'.pytest.log')).write_text(output)
        hits=trace.read_text().splitlines() if trace.exists() else []
        expected=0 if category=='positive' else 1
        outcomes=[json.loads(line) for line in reports.read_text().splitlines()] if reports.exists() else []
        observed_ids={r['nodeid'] for r in outcomes}
        valid=expected_ids==observed_ids and len(outcomes)==len(expected_ids) and all(r['outcome']!='skipped' for r in outcomes) and bool(hits) and run.returncode==expected and ('passed' if expected==0 else 'failed') in output and 'ERROR at setup' not in output and 'ERROR collecting' not in output
        result=dict(name=name,category=category,base_sha=sha,before_sha256=hashlib.sha256(before.encode()).hexdigest(),after_sha256=hashlib.sha256(after.encode()).hexdigest(),expected_test_ids=sorted(expected_ids),observed_test_ids=sorted(observed_ids),exit=run.returncode,hits=len(hits),valid=valid,command=command,summary=output.strip().splitlines()[-1]);results.append(result)
        print(json.dumps(result),flush=True)
        path.write_text(before)
        assert path.read_text() == before
        (OUT/(name+'.restored.log')).write_text(hashlib.sha256(path.read_bytes()).hexdigest()+'\n')
        shutil.rmtree(folder)
    (OUT/'results.log').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    assert all(r['valid'] for r in results)
    assert subprocess.check_output(['git','diff','HEAD']) == baseline_diff
    assert subprocess.check_output(['git','status','--porcelain']) == baseline_status
    assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==value for name,value in manifest.items())
    (OUT/'restoration.log').write_text('snapshot hashes, original git diff and status unchanged\n')

if __name__=='__main__':main()
