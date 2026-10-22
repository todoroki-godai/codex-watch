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
import shutil
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
else: sys.exit(128)
''')
    executable(fake / 'gh', '''#!/usr/bin/env python3
import os,re,sys
from pathlib import Path
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
assert (p/'config.yml').read_text().startswith('version: 1')
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
r=subprocess.run(cmd,env=env,capture_output=True,text=True)
value={'parent_dir':parent,'shell_dir':env.get('GH_CONFIG_DIR'),'login':r.stdout.strip(),'gh_exit':r.returncode,'argv':sys.argv[1:],'stdin':sys.stdin.read(),'pid':os.getpid()}
p.with_suffix('.tmp').write_text(json.dumps(value))
p.with_suffix('.tmp').replace(p)
signal.signal(signal.SIGTERM,lambda *_:sys.exit(143))
release=Path(os.environ['RELEASE'])
while not release.exists(): time.sleep(.02)
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
    wait_for(lambda: not list(state.glob('gh-account.*')))
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
def test_pinned_child_and_cleanup(launch, account):
    result, fields = launch(' \t' + account + '\r\n')
    assert result.returncode == 0, result.stderr
    child = capture(launch)
    assert child['login'] == account and child['gh_exit'] == 0
    assert child['parent_dir'] == child['shell_dir']
    directory = Path(child['shell_dir'])
    assert directory.is_dir(), 'must remain alive after entry point returns'
    assert directory.parent == launch.state
    assert directory.stat().st_mode & 0o777 == 0o700
    assert fields['github_account'] == account
    assert 'prompt must reach codex' in child['stdin']
    launch.release.touch()
    wait_for(lambda: not directory.exists())


@pytest.mark.parametrize('non_git', [False, True])
def test_undeclared_preserves_launch(launch, non_git):
    result, fields = launch(changes={'FAKE_NON_GIT':'1', 'CODEX_IMPL_ALLOW_MAIN':'1'} if non_git else {})
    assert result.returncode == 0, result.stderr
    child = capture(launch)
    assert child['parent_dir'] is None and child['shell_dir'] is None
    assert not any('shell_environment_policy' in a for a in child['argv'])
    assert fields['github_account'] == ''
    assert not list(launch.state.glob('gh-account.*'))


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
    assert not list(launch.state.glob('gh-account.*'))
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


def test_cleanup_after_failed_codex(launch):
    result, _ = launch('matsukaze-minden', changes={'FAKE_CODEX_EXIT':'17'})
    assert result.returncode == 0
    child = capture(launch)
    launch.release.touch()
    wait_for(lambda: not Path(child['parent_dir']).exists())


def test_cleanup_after_term(launch):
    result, fields = launch('matsukaze-minden')
    assert result.returncode == 0
    child = capture(launch)
    os.kill(int(fields['pid']), signal.SIGTERM)
    wait_for(lambda: not Path(child['parent_dir']).exists())
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
    wait_for(lambda: not Path(first['shell_dir']).exists() and not Path(second['shell_dir']).exists())


@pytest.mark.skipif(os.environ.get('CODEX_TEST_REAL_GH') != '1', reason='opt-in real local keychain, read-only')
@pytest.mark.parametrize('account', ['matsukaze-minden', 'todoroki-godai'])
def test_real_gh_from_child(launch, account):
    result, fields = launch(account, real_gh=True)
    assert result.returncode == 0, result.stderr
    child = capture(launch)
    assert child['login'] == account and child['gh_exit'] == 0
    assert fields['github_account'] == account
