"""Mutate isolated copies after commit attempt; retain diffs and executed-line proof."""
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
OUT = ROOT / '.tmp/routing-record-fix1/mutations'
FILE = 'lib/routing_record.py'
TEST_FILE = 'tests/test_routing_record.py'
CASES = [
 ('N1-history-omission', "        record['history'] = history(body, state_dir, target, run_id)", "        record['history'] = []", 'history_grouping', "record['history'] = []", '①履歴欠落検査の除去'),
 ('N2-whole-tree-hash', "        record['current'].update({k: data[k] for k in ('content_hash', 'target_list_hash', 'target_sha')})", "        record['current'].update({k: data[k] for k in ('content_hash', 'target_list_hash', 'target_sha')})\n        from round_gate import git_content_hash\n        record['current']['content_hash'] = git_content_hash(workdir)", 'complete_identity', "record['current']['content_hash'] = git_content_hash", '②別レシピへの意味破壊'),
 ('N3-series-predecessor-swap', "                record[key] = value", "                record[{'series_id':'predecessor_ids','predecessor_ids':'series_id'}.get(key,key)] = value", 'complete_identity', "record[{'series_id'", '③系列と前身入替'),
 ('N4-always-valid', 'def valid(key, value):', 'def valid(key, value):\n    return True', 'structured_invalid', 'return True', '④入力検査常時成功'),
 ('N5-canonical-duplicate-fallback', "        if key in declared:", "        if key in canonical:", 'canonical_conflict', 'if key in canonical:', '別種1 正本の無効項目を依頼で補う'),
 ('N7-delete-external', "        yield os.environ.get('REVIEW_GATE_RECORD', '')\n        return", "        yield os.environ.get('REVIEW_GATE_RECORD', '')\n        Path(os.environ['REVIEW_GATE_RECORD']).unlink()\n        return", 'external_file', "Path(os.environ['REVIEW_GATE_RECORD']).unlink()", '別種3 外部記録消去'),
 ('N8-incomplete-targets', "        record['target_paths'] = data.pop('target_paths')", "        record['target_paths'] = [p for p in data.pop('target_paths') if p != 'untracked']", 'complete_identity', "record['target_paths'] = [p", '対象の一部省略'),
 ('F1-inode-unchecked', '(info.st_dev, info.st_ino) != path.file_identity', 'False', 'inode_replacement', 'if (False', '①inode照合除去'),
 ('F2-path-reopen', "out = os.open(Path(path).name, os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=path.dir_fd)", "out = os.open(str(path), os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK)", 'fd_write', 'out = os.open(str(path)', '②FD書込をパスへ戻す'),
 ('F3-before-read-unchecked', '            check_record(record)  # before adapter reads its path', '            pass  # before adapter reads its path', 'read_replacement and before', 'pass  # before', '③読込前照合除去', 'lib/routing_warn.py'),
 ('F4-whitespace-split', 'matches = list(fields(tail))', "matches = list(re.finditer(r'(?:^|\\s)([a-z_]+)=', tail))", 'structured_quoted', 'matches = list(re.finditer', '④構造化行の分割検査を戻す'),
 ('F5-directory-unchecked', '(parent.st_dev, parent.st_ino) != path.parent_identity', 'False', 'ordinary_parent', 'if False:', '別種 通常ディレクトリ置換'),
 ('F6-after-read-unchecked', '            check_record(record)  # after adapter reads its path', '            pass  # after adapter reads its path', 'read_replacement and after', 'pass  # after', '別種 読込後置換', 'lib/routing_warn.py'),
 ('F7-unclosed-rescue', "and not raw.startswith(('\\\"', '[', '{')) ", '', 'structured_unclosed', 'value = raw if', '別種 未閉鎖文字列を裸値として救済'),
 ('F8-false-declaration', "for m in fields(line[len('routing-record:'):])", "for m in re.finditer(r'(?:^|\\s)([a-z_]+)=', line[len('routing-record:'):])", 'structured_quoted_keys', 'for m in re.finditer', '別種 JSON文字列内の偽キー宣言'),
 ('P1-equivalent', '    return present(value)', '    return present(value) is True', '', 'return present(value) is True', 'positive'),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    files = subprocess.check_output(['git','ls-files','-co','--exclude-standard'],cwd=ROOT,text=True).splitlines()
    files = sorted(set(f for f in files if not f.startswith(('.tmp/', '_work/')) and (ROOT/f).is_file()))
    manifest = {f:sha(ROOT/f) for f in files}
    head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    (OUT/'baseline.log').write_text(json.dumps(dict(head=head, files=manifest),indent=2))
    results = []
    for name, old, new, selection, anchor, category, *target in CASES:
        source = target[0] if target else FILE
        folder = OUT/name
        if folder.exists(): shutil.rmtree(folder)
        folder.mkdir()
        for f in files:
            dest = folder/f
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/f,dest)
        path = folder/source
        before = path.read_text()
        assert before.count(old) == 1, (name,before.count(old))
        after = before.replace(old,new)
        delta = ''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=source,tofile=source))
        assert delta and sha(path) == manifest[source]
        assert old != new and old in before and new in after
        path.write_text(after)
        (OUT/(name+'.diff.log')).write_text(delta)
        trace = OUT/(name+'.executed.log')
        trace.write_text('')
        (folder/'sitecustomize.py').write_text('''import sys,os,linecache,json
seen=set()
def witness(frame,event,arg):
    if event=='line' and frame.f_code.co_filename.endswith('/'+os.environ['RR_SOURCE']):
        source=linecache.getline(frame.f_code.co_filename,frame.f_lineno).strip()
        if os.environ['RR_ANCHOR'] in source and frame.f_lineno not in seen:
            seen.add(frame.f_lineno)
            with open(os.environ['RR_TRACE'],'a') as f: f.write(json.dumps({'line':frame.f_lineno,'source':source})+'\\n')
    return witness
sys.settrace(witness)
''')
        command=[sys.executable,'-m','pytest',TEST_FILE,'-q','-p','no:cacheprovider']
        if selection: command += ['-k',selection]
        env=dict(os.environ,PYTHONPATH=os.pathsep.join((str(folder), str(Path(pytest.__file__).resolve().parents[1]))),PYTHONDONTWRITEBYTECODE='1',RR_ANCHOR=anchor,RR_TRACE=str(trace),RR_SOURCE=source,GIT_CEILING_DIRECTORIES=str(folder))
        run=subprocess.run(command,cwd=folder,env=env,capture_output=True,text=True,timeout=60)
        (OUT/(name+'.test.log')).write_text(json.dumps(command)+'\n'+run.stdout+run.stderr)
        executed = bool(trace.read_text().strip())
        expected = run.returncode == 0 if category == 'positive' else run.returncode == 1 and ' failed' in run.stdout
        results.append(dict(name=name,category=category,exit=run.returncode,executed=executed,expected=expected,diff_sha256=sha(OUT/(name+'.diff.log'))))
        # Keep small evidence, remove fixture repos and source copies.
        shutil.rmtree(folder)
        assert executed and expected, results[-1]
    assert manifest == {f:sha(ROOT/f) for f in files}, 'original checkout changed'
    (OUT/'results.log').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(negative=sum(r['category']!='positive' for r in results),positive=sum(r['category']=='positive' for r in results),survivors=0,restored=True),ensure_ascii=False))

if __name__=='__main__': main()
