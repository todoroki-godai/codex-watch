"""Both entry points: no real git/Codex, and gh is read-only (optionally real).

Run inside the checkout: python3 -m pytest tests/test_codex_github_account.py
Use CODEX_TEST_REAL_GH=1 for the opt-in local keychain checks.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

import pytest

ROOT = Path(os.environ.get("CODEX_ACCOUNT_TEST_ROOT", Path(__file__).resolve().parents[1]))
TOKEN_SHAPE = re.compile(rb'(?:gho_|ghp_|github_pat_)[A-Za-z0-9_]+')


def executable(path, text):
    path.write_text(text)
    path.chmod(0o755)


def wait_for(predicate, timeout=8):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(.02)
    assert predicate(), 'background process did not reach expected state'


@pytest.fixture(params=['codex-impl', 'codex-review'])
def launch(tmp_path, request):
    # Everything, including fake shared HOME, remains below --basetemp.
    work = tmp_path / 'project'
    (work / '.claude').mkdir(parents=True)
    (work / 'subdir').mkdir()
    prompt = tmp_path / 'prompt'
    prompt.write_text('prompt must reach codex\n')
    state = tmp_path / 'state'
    state.mkdir()
    home = tmp_path / 'home'
    shared = home / '.config/gh'
    shared.mkdir(parents=True)
    hosts = shared / 'hosts.yml'
    hosts.write_text('github.com:\n    user: shared-user\n')
    (shared / 'config.yml').write_text('version: 1\nprompt: disabled\n')
    before = hosts.read_bytes()
    fake = tmp_path / 'fakebin'
    fake.mkdir()
    executable(fake / 'git', '''#!/usr/bin/env python3
import os,sys
from pathlib import Path
if os.environ.get('FAKE_NON_GIT'): sys.exit(128)
if '--show-toplevel' in sys.argv: print(os.environ['FAKE_GIT_ROOT'])
elif '--absolute-git-dir' in sys.argv: print(os.environ['FAKE_GIT_ROOT']+'/.git/worktrees/test')
elif '--git-common-dir' in sys.argv: print(os.environ['FAKE_GIT_ROOT']+'/.git')
elif sys.argv[-3:]==['remote','get-url','origin']: print('https://github.com/todoroki-godai/claude-config.git')
elif sys.argv[-2:]==['rev-parse','HEAD']: print('1'*40)
elif sys.argv[1] in ('status','diff','ls-files'): pass
else: sys.exit(128)
''')
    executable(fake / 'gh', '''#!/usr/bin/env python3
import json,os,re,sys,time
from pathlib import Path
if sys.argv[1:3]==['issue','view'] or 'PATCH' in sys.argv:
    assert os.environ.get('FAKE_RECORD'), 'unexpected body access'
    state=Path(os.environ['CODEX_WATCH_DIR'])
    states=list(state.glob('*.state'))
    if states:
        # Ensure record runs after Codex has exited, reproducing the old cleanup race.
        end=time.monotonic()+5
        while not Path(os.environ['CAPTURE']).with_suffix('.done').exists():
            assert time.monotonic()<end, 'Codex did not exit before record'
            time.sleep(.01)
        pid=json.loads(Path(os.environ['CAPTURE']).read_text())['pid']
        while True:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            assert time.monotonic()<end, 'Codex still alive during record'
            time.sleep(.01)
    folder=Path(os.environ['GH_CONFIG_DIR'])
    hosts=(folder/'hosts.yml').read_text()
    if states:
        assert folder==state/'gh-account'/'matsukaze-minden', 'record not using permanent account directory'
    assert hosts=='github.com:\\n    users:\\n        matsukaze-minden:\\n    user: matsukaze-minden\\n'
    body=state/'fake-body'
    with (state/'gh-calls.jsonl').open('a') as out:
        out.write(json.dumps({'method':'PATCH' if 'PATCH' in sys.argv else 'GET', 'record':bool(states), 'directory':str(folder), 'hosts':hosts})+'\\n')
    if 'PATCH' in sys.argv:
        assert sys.argv[1:]==['api','repos/todoroki-godai/claude-config/issues/55','-X','PATCH','--input','-']
        body.write_text(json.load(sys.stdin)['body'])
    else:
        assert sys.argv[1:]==['issue','view','55','-R','todoroki-godai/claude-config','--json','body','-q','.body']
        print(body.read_text() if body.exists() else '')
    sys.exit(0)
if os.environ.get('FAKE_FORBID_GH'):
    Path(os.environ['CODEX_WATCH_DIR'],'unexpected-gh').touch()
    sys.exit(9)
assert sys.argv[1:] in (['api','--hostname','github.com','user','--jq','.login'], ['api','user','--jq','.login']), sys.argv[1:]
mode=os.environ.get('FAKE_GH_MODE','')
if mode=='fail':
    print('gh'+'p_'+'FAKE_SENTINEL',file=sys.stderr)
    sys.exit(1)
if mode=='bad-output':
    print('github_'+'pat_'+'FAKE_SENTINEL'); sys.exit(0)
if mode=='wrong': print('wrong-user'); sys.exit(0)
if os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN'):
    print('env-user'); sys.exit(0)
d=os.environ.get('GH_CONFIG_DIR')
if not d: print('shared-user'); sys.exit(0)
p=Path(d)
s=(p/'hosts.yml').read_text()
assert 'oauth_token' not in s
m=re.search(r'^    user: (.+)$',s,re.M)
assert m
user=m[1]
if user=='no-such-user-xyz': print('fallback-user'); sys.exit(0)
assert s==f'github.com:\\n    users:\\n        {user}:\\n    user: {user}\\n'
assert (p/'config.yml').read_bytes() == b'version: "1"\\n'
print(user)
''')
    executable(fake / 'codex', '''#!/usr/bin/env python3
import json,os,subprocess,sys,time,tomllib,signal
from pathlib import Path
p=Path(os.environ['CAPTURE'])
parent=os.environ.get('GH_CONFIG_DIR')
# Model the real CLI's configured inherit=core and explicit set overrides.
env={k:v for k,v in os.environ.items() if k in ('HOME','PATH','USER','SHELL')}
for i,arg in enumerate(sys.argv):
    if arg=='-c' and sys.argv[i+1].startswith('shell_environment_policy.set.'):
        setting=tomllib.loads(sys.argv[i+1])
        env.update(setting['shell_environment_policy']['set'])
cmd=['gh','api','user','--jq','.login']
r=subprocess.run(cmd,env=env,capture_output=True,text=True) if not os.environ.get('FAKE_FORBID_GH') else subprocess.CompletedProcess(cmd,0,'','')
value={'parent_dir':parent,'shell_dir':env.get('GH_CONFIG_DIR'),'login':r.stdout.strip(),'gh_exit':r.returncode,'argv':sys.argv[1:],'stdin':sys.stdin.read(),'pid':os.getpid()}
p.with_suffix('.tmp').write_text(json.dumps(value))
p.with_suffix('.tmp').replace(p)
signal.signal(signal.SIGTERM,lambda *_:sys.exit(143))
release=Path(os.environ['RELEASE'])
while not release.exists(): time.sleep(.02)
p.with_suffix('.done').touch()
sys.exit(int(os.environ.get('FAKE_CODEX_EXIT','0')))
''')
    env = dict(os.environ)
    for k in list(env):
        if k.startswith(('CODEX_', 'REVIEW_', 'GH_', 'GITHUB_')):
            env.pop(k)
    env.update(PATH=f'{fake}:{env["PATH"]}', HOME=str(home),
               FAKE_GIT_ROOT=str(work), CODEX_WATCH_DIR=str(state),
               CODEX_IMPL_ALLOW_MISSING_NODE_MODULES='1',
               CODEX_REVIEW_KIND_LABEL='コード', REVIEW_TARGET='none:account-test',
               CAPTURE=str(tmp_path / 'capture.json'), RELEASE=str(tmp_path / 'release'))
    children = []

    def run(account=None, *, changes=None, cwd=None, real_gh=False):
        declaration = work / '.claude/codex-github-account'
        if account is not None:
            declaration.write_bytes(account if isinstance(account, bytes) else account.encode())
        current = dict(env, **(changes or {}))
        if real_gh:
            (fake / 'gh').unlink()
            # Read real shared config; no settings are written there.
            current['HOME'] = os.environ['HOME']
        result = subprocess.run([str(ROOT / 'bin' / request.param), str(cwd or work / 'subdir'), str(prompt)],
                                env=current, capture_output=True, text=True, timeout=15)
        states = list(state.glob('*.state'))
        if states:
            fields = dict(line.split('=',1) for line in states[-1].read_text().splitlines())
            children.append(int(fields['pid']))
        else:
            fields = {}
        return result, fields

    run.entry = request.param
    run.work, run.state, run.env = work, state, env
    run.capture, run.release = Path(env['CAPTURE']), Path(env['RELEASE'])
    run.shared, run.before = hosts, before
    yield run
    run.release.touch()
    for pid in children:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    assert hosts.read_bytes() == before, 'shared hosts.yml changed'
    assert hashlib.sha256(hosts.read_bytes()).digest() == hashlib.sha256(before).digest()
    # Scan every emitted artifact, not the fixtures containing synthetic sentinels.
    for p in [*state.rglob('*'), run.capture]:
        if p.is_file():
            assert not TOKEN_SHAPE.search(p.read_bytes()), f'token-shaped output in {p.name}'


def capture(launch):
    wait_for(launch.capture.exists)
    return json.loads(launch.capture.read_text())


@pytest.mark.parametrize('account', ['matsukaze-minden', 'todoroki-godai'])
def test_pinned_child_and_persistence(launch, account):
    result, fields = launch(' \t' + account + '\r\n')
    assert result.returncode == 0, result.stderr
    child = capture(launch)
    assert child['login'] == account and child['gh_exit'] == 0
    assert child['parent_dir'] == child['shell_dir']
    directory = Path(child['shell_dir'])
    assert directory.is_dir(), 'must remain alive after entry point returns'
    assert directory == launch.state / 'gh-account' / account
    assert int(fields['pid']) == child['pid']
    assert directory.stat().st_mode & 0o777 == 0o700
    assert fields['github_account'] == account
    assert 'prompt must reach codex' in child['stdin']
    launch.release.touch()
    wait_for(lambda: launch.capture.with_suffix('.done').exists())
    assert directory.is_dir()
    assert {p.name for p in directory.iterdir()} == {'hosts.yml', 'config.yml'}


@pytest.mark.parametrize('non_git', [False, True])
def test_undeclared_preserves_launch(launch, non_git):
    result, fields = launch(changes={'FAKE_NON_GIT':'1', 'CODEX_IMPL_ALLOW_MAIN':'1'} if non_git else {})
    assert result.returncode == 0, result.stderr
    child = capture(launch)
    assert child['parent_dir'] is None and child['shell_dir'] is None
    assert not any('shell_environment_policy' in a for a in child['argv'])
    assert 'github_account' not in fields
    assert not (launch.state / 'gh-account').exists()


def test_undeclared_preserves_inherited_gh_config(launch):
    directory = str(launch.shared.parent)
    result, _ = launch(changes={'GH_CONFIG_DIR':directory})
    assert result.returncode == 0
    child = capture(launch)
    assert child['parent_dir'] == directory
    assert not any('shell_environment_policy' in a for a in child['argv'])


@pytest.mark.parametrize('value', ['no-such-user-xyz', '', 'one two', 'one\ntwo', 'a'*80,
                                  'gh'+'p_'+'FAKE_SENTINEL', 'github_'+'pat_'+'FAKE_SENTINEL',
                                  b'name\x00', b'\xff', '-bad', 'bad-'])
def test_invalid_or_missing_account_stops(launch, value):
    result, fields = launch(value)
    assert result.returncode != 0
    assert len(result.stderr.splitlines()) == 1, result.stderr
    assert not TOKEN_SHAPE.search((result.stdout+result.stderr).encode())
    assert fields == {} and not launch.capture.exists()
    if value != 'no-such-user-xyz':
        assert not (launch.state / 'gh-account').exists()
    if value == 'no-such-user-xyz':
        assert 'requested=no-such-user-xyz returned=fallback-user' in result.stderr


@pytest.mark.parametrize('mode', ['wrong', 'fail', 'bad-output'])
def test_failed_preflight_stops_and_redacts(launch, mode):
    result, fields = launch('matsukaze-minden', changes={'FAKE_GH_MODE':mode})
    assert result.returncode != 0
    assert 'requested=matsukaze-minden' in result.stderr
    assert len(result.stderr.splitlines()) == 1
    assert not TOKEN_SHAPE.search((result.stdout+result.stderr).encode())
    assert fields == {} and not launch.capture.exists()


def test_environment_credentials_cannot_override(launch):
    result, _ = launch('todoroki-godai', changes={'GH_TOKEN':'override-sentinel', 'GITHUB_TOKEN':'override-sentinel', 'GH_DEBUG':'api'})
    assert result.returncode == 0, result.stderr
    child = capture(launch)
    assert child['login'] == 'todoroki-godai'
    settings = [a for a in child['argv'] if a.startswith('shell_environment_policy.set.')]
    assert 'shell_environment_policy.set.GH_TOKEN=""' in settings
    assert 'shell_environment_policy.set.GITHUB_TOKEN=""' in settings
    assert 'shell_environment_policy.set.GH_DEBUG=""' in settings


def test_persistence_after_failed_codex(launch):
    result, fields = launch('matsukaze-minden', changes={'FAKE_CODEX_EXIT':'17'})
    assert result.returncode == 0
    child = capture(launch)
    launch.release.touch()
    wait_for(lambda: launch.capture.with_suffix('.done').exists())
    assert int(fields['pid']) == child['pid']
    assert Path(child['parent_dir']).is_dir()


def test_persistence_after_term(launch):
    result, fields = launch('matsukaze-minden')
    assert result.returncode == 0
    child = capture(launch)
    os.kill(int(fields['pid']), signal.SIGTERM)
    assert int(fields['pid']) == child['pid']
    assert Path(child['parent_dir']).is_dir()
    def stopped():
        try:
            os.kill(child['pid'], 0)
            return False
        except ProcessLookupError:
            return True
    wait_for(stopped)


def test_dangling_declaration_is_error(launch):
    (launch.work / '.claude/codex-github-account').symlink_to('missing')
    result, _ = launch()
    assert result.returncode != 0
    assert len(result.stderr.splitlines()) == 1


def test_concurrent_runs_keep_separate_accounts(launch):
    first_result, _ = launch('matsukaze-minden')
    assert first_result.returncode == 0
    first = capture(launch)
    launch.capture.unlink()
    second_result, _ = launch('todoroki-godai')
    assert second_result.returncode == 0
    second = capture(launch)
    assert first['login'] == 'matsukaze-minden'
    assert second['login'] == 'todoroki-godai'
    assert first['shell_dir'] != second['shell_dir']
    assert Path(first['shell_dir']).is_dir() and Path(second['shell_dir']).is_dir()
    launch.release.touch()
    assert Path(first['shell_dir']).is_dir() and Path(second['shell_dir']).is_dir()


@pytest.mark.skipif(os.environ.get('CODEX_TEST_REAL_GH') != '1', reason='opt-in real local keychain, read-only')
@pytest.mark.parametrize('account', ['matsukaze-minden', 'todoroki-godai'])
def test_real_gh_from_child(launch, account):
    result, fields = launch(account, real_gh=True)
    assert result.returncode == 0, result.stderr
    child = capture(launch)
    assert child['login'] == account and child['gh_exit'] == 0
    assert fields['github_account'] == account


def test_undeclared_never_calls_gh(launch):
    result, fields = launch(changes={'FAKE_FORBID_GH':'1', 'FAKE_GH_MODE':'fail'})
    assert result.returncode == 0, result.stderr
    capture(launch)
    assert 'github_account' not in fields
    assert not (launch.state / 'unexpected-gh').exists()


def test_review_records_after_codex_exit(launch):
    # This is an existing issue referenced by round_gate receipt documentation.
    # Network and real git are replaced; PATCH writes only the local fake body.
    if launch.entry != 'codex-review':
        pytest.skip('record belongs to review only')
    launch.release.touch()
    result, fields = launch('matsukaze-minden', changes={
        'FAKE_RECORD':'1', 'REVIEW_TARGET':'issue:todoroki-godai/claude-config#55',
        'REVIEW_GOAL_CUT':'1分/周 | 根拠: record 回帰試験 | 取得日: 2026-10-23'})
    assert result.returncode == 0, result.stderr
    assert fields.get('round_row_written') == '1', result.stderr
    assert fields['head_sha'] == '1' * 40
    assert re.fullmatch('[0-9a-f]{64}', fields['content_hash'])
    assert launch.capture.with_suffix('.done').exists()
    child = capture(launch)
    assert int(fields['pid']) == child['pid']
    calls = [json.loads(line) for line in (launch.state / 'gh-calls.jsonl').read_text().splitlines()]
    record = [c for c in calls if c['record']]
    assert [c['method'] for c in record] == ['GET', 'PATCH', 'GET']
    assert all(c['directory'] == str(launch.state / 'gh-account' / 'matsukaze-minden') for c in calls)
    assert 'コード' in (launch.state / 'fake-body').read_text()


@pytest.mark.parametrize("stale_config", ['stale invalid config', 'version: "1"\nprompt: disabled\n'])
def test_repeated_account_replaces_files(launch, stale_config):
    result, _ = launch('matsukaze-minden')
    assert result.returncode == 0
    first = capture(launch)
    directory = Path(first['shell_dir'])
    # Stale same-account configuration must be refreshed on each launch.
    inodes = {name: (directory / name).stat().st_ino for name in ('hosts.yml', 'config.yml')}
    (directory / 'hosts.yml').write_text('stale invalid hosts')
    (directory / 'config.yml').write_text(stale_config)
    launch.shared.with_name('config.yml').write_text('version: 1\nprompt: disabled\neditor: refreshed\n')
    launch.capture.unlink()
    result, _ = launch('matsukaze-minden')
    assert result.returncode == 0, result.stderr
    second = capture(launch)
    assert first['shell_dir'] == second['shell_dir']
    assert second['login'] == 'matsukaze-minden'
    assert all((directory / name).stat().st_ino != inode for name, inode in inodes.items())
    assert (directory / 'config.yml').read_bytes() == b'version: "1"\n'
    assert {p.name for p in directory.iterdir()} == {'hosts.yml', 'config.yml'}


@pytest.mark.parametrize('shared_config', [None, 'prompt: disabled\n'])
def test_fixed_config_without_shared_version(launch, shared_config):
    config = launch.shared.with_name('config.yml')
    if shared_config is None:
        config.unlink()
    else:
        config.write_text(shared_config)
    result, _ = launch('matsukaze-minden')
    assert result.returncode == 0, result.stderr
    child = capture(launch)
    assert child['gh_exit'] == 0
    assert (Path(child['shell_dir']) / 'config.yml').read_bytes() == b'version: "1"\n'
    if shared_config is None:
        assert not config.exists()
    else:
        assert config.read_text() == shared_config
