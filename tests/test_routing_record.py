"""Only temporary repositories, fake GitHub and the read-only route adapter."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from test_codex_review_cli import fake_bin
import routing_record as rr
import routing_warn as rw

PARTS = Path('/Users/matsukaze-takashi/.claude/_wt.noindex/review-gate-parts/skills/review-gate')

@pytest.fixture
def case(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()
    git('init', '-q')
    for name in ('changed', 'deleted'):
        (repo / name).write_text('old\n')
    git('add', '.')
    git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'base')
    base = git('rev-parse', 'HEAD')
    (repo / 'changed').write_text('new\n')
    (repo / 'deleted').unlink()
    (repo / 'added').write_text('added\n')
    git('add', 'added')
    (repo / 'untracked').write_text('new\n')
    state = tmp_path / 'state'
    state.mkdir()
    body = f'routing-record: series_id=series predecessor_ids=[] base_sha={base}\n## 巡の履歴\n'
    return repo, state, body, git


def build(case, monkeypatch, body=None, prompt='', kind='設計'):
    repo, state, default, _ = case
    monkeypatch.setattr(rr, 'gh_fetch_body', lambda target: default if body is None else body)
    return rr.generate(str(repo), 'issue:org/repo#1', kind, 'next', state, prompt,
                       PARTS / 'route.mjs', time.monotonic() + 10)


def test_complete_identity_and_real_adapter(case, monkeypatch, tmp_path):
    record, reasons = build(case, monkeypatch)
    repo, _, body, git = case
    assert reasons == []
    assert record['series_id'] == 'series' and record['predecessor_ids'] == []
    assert record['target_paths'] == ['added', 'changed', 'deleted', 'untracked']
    assert record['history'] == [] and record['current']['family_tags'] == ['initial']
    assert record['current']['target_sha'] == git('rev-parse', 'HEAD')
    assert record['history_source']['body_hash'] == hashlib.sha256(body.encode()).hexdigest()
    assert record['history_source']['fetched_at'].endswith('+00:00')
    path = tmp_path / 'record.json'
    path.write_text(json.dumps(record))
    assert rw.evaluate(str(PARTS / 'adapter.py'), str(path), str(repo))[0] == 'pass'
    code = "import {collectChanges,contentIdentity} from " + json.dumps((PARTS / 'route.mjs').as_uri()) + ";const c=collectChanges(process.argv[1],process.argv[2]); console.log(JSON.stringify(contentIdentity(process.argv[1],process.argv[2],c.paths)))"
    expected = json.loads(subprocess.check_output(['node', '--input-type=module', '-e', code, str(repo), record['base_sha']], text=True))
    for key in ('content_hash', 'target_list_hash'):
        assert record['current'][key] == expected[key]
    record, _ = build(case, monkeypatch, kind='コード')
    path.write_text(json.dumps(record))
    assert rw.evaluate(str(PARTS / 'adapter.py'), str(path), str(repo))[0] == 'would_block'


@pytest.mark.parametrize('value', ['', '  ', '/does/not/exist'])
def test_external_is_preserved(tmp_path, monkeypatch, value):
    monkeypatch.setenv('REVIEW_GATE_RECORD', value)
    with rr.record_path(True) as path:
        assert path == value
    assert not (tmp_path / 'record.json').exists()


def test_external_file_is_not_deleted(tmp_path, monkeypatch):
    path = tmp_path / 'external'
    path.write_text('external')
    monkeypatch.setenv('REVIEW_GATE_RECORD', str(path))
    with rr.record_path(True) as record:
        assert record == str(path)
    assert path.read_text() == 'external'


@pytest.mark.parametrize('value', ['series_id=one series_id=one', 'series_id=one series_id=two', 'series_id="　 "', 'predecessor_ids=bad', 'base_sha=123', 'family_tags=[]', 'series_id=未確認'])
def test_structured_invalid(value):
    fields = rr.structured('routing-record: ' + value)
    key = value.split('=')[0]
    assert key not in fields


def test_structured_canonical_conflict(case, monkeypatch):
    r, reasons = build(case, monkeypatch, prompt='routing-record: series_id=other predecessor_ids=["past"]')
    assert r['series_id'] == 'series' and r['predecessor_ids'] == []
    assert reasons == ['正本と依頼文の項目不一致']
    r, _ = build(case, monkeypatch, body=case[2].replace('series_id=series', 'series_id=series series_id=other'), prompt='routing-record: series_id=fallback')
    assert 'series_id' not in r


def test_history_grouping_gaps_and_pending(case, monkeypatch):
    body = case[2]
    sha = case[3]('rev-parse', 'HEAD')
    for rid, reviewer, rnd, tags in [('first','A',1,'alpha'), ('second','B',1,'beta'), ('third','C',3,'gamma')]:
        body += f'| {rnd} | 設計 | date | {sha[:7]} | {reviewer} | 1 | {tags} | <!-- dispatch_id={rid} -->\n'
        (case[1] / (rid + '.state')).write_text(f'run_id={rid}\nreview_target=issue:org/repo#1\nround={rnd}\nkind_label=設計\nstarted_at_human=date\nhead_sha={sha}\nreviewer={reviewer}\ncontent_hash=' + 'f'*64 + '\n')
    r, _ = build(case, monkeypatch, body=body)
    assert len(r['history']) == 3
    first, gap, third = r['history']
    assert first['event_id'] == 'first'
    assert first['family_tags'] == ['alpha', 'beta']
    assert first['status'] == 'pending' and 'finding_family_tags' not in first
    assert 'content_hash' not in first  # whole-worktree state hash is incompatible
    assert gap == {'missing': True, 'round': 2, 'kind': '設計'}
    assert third['event_id'] == 'third'
    assert 'family_tags' not in r['current']
    # Ambiguous state and replayed/current IDs cannot disappear into empty history.
    (case[1] / 'duplicate.state').write_text((case[1] / 'first.state').read_text())
    r, _ = build(case, monkeypatch, body=body)
    assert r['history'][0]['missing'] is True
    r, _ = build(case, monkeypatch, body=body.replace('dispatch_id=third', 'dispatch_id=next'))
    assert r['history'][-1]['missing'] is True


def test_failure_is_missing_not_empty(case, monkeypatch):
    def fail(*args):
        raise ValueError('SYNTHETIC_SECRET')
    monkeypatch.setattr(rr, 'gh_fetch_body', fail)
    r, reasons = rr.generate(str(case[0]), 'issue:org/repo#1', '設計', 'next', case[1], '', PARTS/'route.mjs', time.monotonic()+10)
    assert r['history_source'] == {'available': False}
    assert r['history'] == [{'missing': True}]
    assert 'family_tags' not in r['current']
    assert reasons == ['正本取得失敗', '対象同一性未取得']


def test_missing_base_and_git(case, monkeypatch):
    r, reasons = build(case, monkeypatch, body='## 巡の履歴\n')
    assert 'target_paths' not in r and 'content_hash' not in r['current']
    assert '対象同一性未取得' in reasons


def test_temporary_permissions_concurrency_cleanup(monkeypatch):
    monkeypatch.delenv('REVIEW_GATE_RECORD', raising=False)
    with rr.record_path(True) as a, rr.record_path(True) as b:
        assert a != b
        for p in (a,b):
            assert Path(p).stat().st_mode & 0o777 == 0o600
            assert Path(p).parent.stat().st_mode & 0o777 == 0o700
            rr.write_record(p, {'ok': True})
            assert json.loads(Path(p).read_text()) == {'ok': True}
    assert not Path(a).exists() and not Path(b).exists()


def test_temporary_link_replacement(tmp_path, monkeypatch):
    monkeypatch.delenv('REVIEW_GATE_RECORD', raising=False)
    victim = tmp_path / 'victim'
    victim.write_text('safe')
    victim.chmod(0o600)
    with rr.record_path(True) as a:
        Path(a).unlink()
        Path(a).symlink_to(victim)
        with pytest.raises((OSError, ValueError)):
            rr.write_record(a, {})
    assert victim.read_text() == 'safe'


def test_parent_replacement(tmp_path, monkeypatch):
    monkeypatch.delenv('REVIEW_GATE_RECORD', raising=False)
    victim = tmp_path / 'victim'
    victim.mkdir()
    (victim / 'record.json').write_text('safe')
    with rr.record_path(True) as a:
        parent = Path(a).parent
        moved = parent.with_name(parent.name + '-moved')
        parent.rename(moved)
        parent.symlink_to(victim, target_is_directory=True)
        with pytest.raises((OSError, ValueError)):
            rr.write_record(a, {})
    assert (victim / 'record.json').read_text() == 'safe'
    parent.unlink()
    moved.rmdir()


def test_observe_generated_record_and_shared_budget(case, tmp_path, monkeypatch, capsys):
    repo, state, _, _ = case
    monkeypatch.delenv('REVIEW_GATE_RECORD', raising=False)
    monkeypatch.setenv('CODEX_REVIEW_ADAPTER', str(PARTS/'adapter.py'))
    monkeypatch.setattr(rr, 'gh_fetch_body', lambda t: case[2])
    prompt = tmp_path/'prompt'
    prompt.write_text('routing-record: family_tags=["explicit"]')
    original = rw.evaluate
    remaining = []
    def evaluate(adapter, record, work, deadline):
        r = json.loads(Path(record).read_text())
        assert r['current']['family_tags'] == ['explicit']
        remaining.append(deadline - time.monotonic())
        return original(adapter, record, work, deadline)
    monkeypatch.setattr(rw, 'evaluate', evaluate)
    with rr.record_path(True) as path:
        rw.observe(str(state), 'next', 'issue:org/repo#1', '設計', str(repo), str(prompt), path)
    assert 0 < remaining[0] < rw.BUDGET_SECONDS - 0.25
    assert json.loads((state/'routing-warn.jsonl').read_text())['verdict'] == 'pass'
    assert not Path(path).exists()


def test_generation_timeout_cleanup(case, tmp_path, monkeypatch):
    repo, state, _, _ = case
    monkeypatch.delenv('REVIEW_GATE_RECORD', raising=False)
    monkeypatch.setenv('CODEX_REVIEW_ADAPTER', str(PARTS/'adapter.py'))
    monkeypatch.setattr(rw, 'BUDGET_SECONDS', 0.5)
    def fetch(*args):
        time.sleep(2)
        return case[2]
    monkeypatch.setattr(rr, 'gh_fetch_body', fetch)
    prompt = tmp_path/'prompt'
    prompt.write_text('')
    started = time.monotonic()
    with rr.record_path(True) as path:
        rw.observe(str(state), 'next', 'issue:org/repo#1', '設計', str(repo), str(prompt), path)
    assert time.monotonic() - started < 0.6
    assert not Path(path).exists()
    assert json.loads((state/'routing-warn.jsonl').read_text())['verdict'] == 'timeout'


def test_generation_spends_evaluation_budget(case, tmp_path, monkeypatch):
    repo, state, _, _ = case
    monkeypatch.delenv('REVIEW_GATE_RECORD', raising=False)
    monkeypatch.setattr(rw, 'BUDGET_SECONDS', 1.2)
    def fetch(*args):
        time.sleep(0.4)
        return case[2]
    monkeypatch.setattr(rr, 'gh_fetch_body', fetch)
    adapter = tmp_path/'adapter.py'
    adapter.write_text('import time; time.sleep(2)')
    monkeypatch.setenv('CODEX_REVIEW_ADAPTER', str(adapter))
    # Reuse actual identity functions while fake adapter deliberately waits.
    original = rr.generate
    def generate(*args):
        args = list(args)
        args[-2] = PARTS/'route.mjs'
        return original(*args)
    monkeypatch.setattr(rr, 'generate', generate)
    prompt = tmp_path/'prompt'
    prompt.write_text('')
    started = time.monotonic()
    with rr.record_path(True) as path:
        rw.observe(str(state), 'next', 'issue:org/repo#1', '設計', str(repo), str(prompt), path)
    assert 0.8 <= time.monotonic() - started < 1.5
    assert not Path(path).exists()
    assert json.loads((state/'routing-warn.jsonl').read_text())['verdict'] == 'timeout'


@pytest.mark.parametrize('failure', ['read', 'write'])
def test_record_io_failure_cleanup(case, tmp_path, monkeypatch, failure):
    repo, state, _, _ = case
    monkeypatch.delenv('REVIEW_GATE_RECORD', raising=False)
    monkeypatch.setenv('CODEX_REVIEW_ADAPTER', str(PARTS/'adapter.py'))
    monkeypatch.setattr(rr, 'gh_fetch_body', lambda t: case[2])
    prompt = tmp_path/'prompt'
    prompt.write_text('')
    with rr.record_path(True) as path:
        if failure == 'read':
            def evaluate(*args):
                Path(path).write_text('not JSON SYNTHETIC_SECRET')
                return rw_evaluate(*args)
            rw_evaluate = rw.evaluate
            monkeypatch.setattr(rw, 'evaluate', evaluate)
        else:
            Path(path).unlink()
        rw.observe(str(state), 'next', 'issue:org/repo#1', '設計', str(repo), str(prompt), path)
    assert not Path(path).exists()
    text = (state/'routing-warn.jsonl').read_text()
    assert 'SYNTHETIC_SECRET' not in text
    assert json.loads(text)['verdict'] == ('would_block' if failure == 'read' else 'error')


def test_cli_wires_generated_json(case, tmp_path, fake_bin, monkeypatch):
    from test_codex_review_cli import VALID_GOAL_CUT
    repo, state, body, git = case
    git('remote', 'add', 'origin', 'https://github.com/org/repo.git')
    bodyfile = tmp_path/'body'
    bodyfile.write_text(body)
    prompt = tmp_path/'prompt'
    prompt.write_text('点検:\n- 突き合わせ: 済\n- 出所の付記: 済\n- 直し残しの検索: 済\n')
    observed = tmp_path/'seen.json'
    adapter = tmp_path/'adapter.py'
    (tmp_path/'route.mjs').symlink_to(PARTS/'route.mjs')
    adapter.write_text(f'import json,sys,subprocess\nfrom pathlib import Path\nPath({str(observed)!r}).write_text(json.dumps([sys.argv[1],json.loads(Path(sys.argv[1]).read_text())]))\nsys.exit(subprocess.call([sys.executable,{str(PARTS/"adapter.py")!r},*sys.argv[1:]]))\n')
    env = dict(os.environ, PATH=f'{fake_bin}:{os.environ["PATH"]}', CODEX_WATCH_DIR=str(state),
               CODEX_REVIEW_KIND_LABEL='設計', CODEX_SUMMARY='#0', CODEX_REVIEW_ADAPTER=str(adapter),
               REVIEW_TARGET='issue:org/repo#1', REVIEW_GOAL_CUT=VALID_GOAL_CUT,
               FAKE_GH_BODY=str(bodyfile), ARGV_CAPTURE_FILE=str(tmp_path/'sent'))
    for key in ('REVIEW_GATE_RECORD', 'CODEX_REVIEW_GATE_CHECK', 'CODEX_REVIEW_NO_GATE'):
        env.pop(key, None)
    cli = Path(__file__).resolve().parents[1]/'bin/codex-review'
    result = subprocess.run([str(cli),str(repo),str(prompt),'record-test'], env=env, text=True, capture_output=True,timeout=15)
    assert result.returncode == 0, result.stderr
    path, record = json.loads(observed.read_text())
    assert not Path(path).exists()
    assert record['series_id'] == 'series'
    assert record['current']['event_id'] == result.stdout.strip().splitlines()[-1]
    assert json.loads((state/'routing-warn.jsonl').read_text())['verdict'] == 'pass'


def test_state_only_history_cannot_be_initial(case, monkeypatch):
    (case[1]/'past.state').write_text('run_id=past\nreview_target=issue:org/repo#1\n')
    record, _ = build(case, monkeypatch)
    assert record['history'] == [{'missing': True}]
    assert 'family_tags' not in record['current']


def test_nonempty_predecessor_is_not_initial(case, monkeypatch):
    record, _ = build(case, monkeypatch, body=case[2].replace('predecessor_ids=[]', 'predecessor_ids=["past"]'))
    assert 'family_tags' not in record['current']


def test_git_absent_is_classified(tmp_path, monkeypatch):
    monkeypatch.setattr(rr, 'gh_fetch_body', lambda _: '## 巡の履歴\n')
    record, reasons = rr.generate(str(tmp_path), 'issue:org/repo#1', '設計', 'next', tmp_path, '', PARTS/'route.mjs', time.monotonic()+10)
    assert 'target_sha' not in record['current']
    assert '対象SHA未取得' in reasons and '対象同一性未取得' in reasons


def test_real_fetch_failure_is_classified(case, monkeypatch):
    def fail(_):
        raise rr.Indeterminate('SYNTHETIC_SECRET')
    monkeypatch.setattr(rr, 'gh_fetch_body', fail)
    record, reasons = rr.generate(str(case[0]), 'issue:org/repo#1', '設計', 'next', case[1], '', PARTS/'route.mjs', time.monotonic()+10)
    assert record['history_source'] == {'available': False}
    assert record['history'] == [{'missing': True}]
    assert reasons == ['正本取得失敗', '対象同一性未取得']


def test_two_concurrent_observations(case, tmp_path, monkeypatch, fake_bin):
    import concurrent.futures
    repo, state, body, _ = case
    bodyfile = tmp_path/'body'
    bodyfile.write_text(body)
    prompt = tmp_path/'prompt'
    prompt.write_text('')
    adapter = tmp_path/'adapter.py'
    (tmp_path/'route.mjs').symlink_to(PARTS/'route.mjs')
    adapter.write_text(f'import json,sys,subprocess\nfrom pathlib import Path\np=Path(sys.argv[1]); r=json.loads(p.read_text()); Path({str(tmp_path)!r},r["current"]["event_id"]+".seen").write_text(str(p))\nsys.exit(subprocess.call([sys.executable,{str(PARTS/"adapter.py")!r},*sys.argv[1:]]))\n')
    monkeypatch.setenv('PATH', str(fake_bin)+os.pathsep+os.environ['PATH'])
    monkeypatch.setenv('FAKE_GH_BODY',str(bodyfile))
    monkeypatch.setenv('CODEX_REVIEW_ADAPTER',str(adapter))
    monkeypatch.delenv('REVIEW_GATE_RECORD',raising=False)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda rid: rw.run_bounded([str(state),rid,'issue:org/repo#1','設計',str(repo),str(prompt)]), ['one','two']))
    paths = [(tmp_path/(rid+'.seen')).read_text() for rid in ('one','two')]
    assert len(set(paths)) == 2 and all(not Path(p).exists() for p in paths)
    rows = [json.loads(line) for line in (state/'routing-warn.jsonl').read_text().splitlines()]
    assert {row['dispatch_id'] for row in rows} == {'one','two'}
    assert all(row['verdict'] == 'pass' for row in rows)
