"""Contract checks: fake git/AWS/Codex only; never persist credential values."""
import json
import os
from pathlib import Path
import subprocess
import time
import tomllib

import pytest

ROOT = Path(os.environ.get('CODEX_AWS_TEST_ROOT', Path(__file__).resolve().parents[1]))
SECRETS = ['AKIA_FAKE_SENTINEL', 'secret_FAKE_SENTINEL', 'token_FAKE_SENTINEL']


def executable(path, source):
    path.write_text('#!/usr/bin/env python3\n' + source)
    path.chmod(0o755)


@pytest.fixture
def launch(tmp_path):
    fake = tmp_path / 'bin'
    fake.mkdir()
    work = tmp_path / 'work'
    work.mkdir()
    prompt = tmp_path / 'prompt'
    prompt.write_text('offline test')
    common = str(tmp_path / 'shared "repo" \\ dir/.git')
    gitdir = common + '/worktrees/test'
    executable(fake / 'git', '''import os,sys
if '--absolute-git-dir' in sys.argv: print(os.environ['TEST_GITDIR'])
elif '--git-common-dir' in sys.argv: print(os.environ['TEST_COMMON'])
else: sys.exit(128)
''')
    executable(fake / 'aws', '''import json,os,sys
from pathlib import Path
with Path(os.environ['TEST_CALLS']).open('a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')
assert sys.argv[-2:] == ['--profile','aws-updater-index-stg']
assert 'AWS_ENDPOINT_URL_STS' not in os.environ
mode=os.environ.get('TEST_MODE','ok')
if sys.argv[1]=='sts':
    if mode=='sts-fail':
        print('secret_FAKE_SENTINEL',file=sys.stderr); sys.exit(1)
    print('682251233834' if mode=='wrong' else '669126230735'); sys.exit(0)
if mode=='export-fail':
    print('secret_FAKE_SENTINEL'); print('token_FAKE_SENTINEL',file=sys.stderr); sys.exit(1)
v={'Version':1,'AccessKeyId':'AKIA_FAKE_SENTINEL','SecretAccessKey':'secret_FAKE_SENTINEL','SessionToken':'token_FAKE_SENTINEL','Expiration':'2099-01-02T03:04:05Z'}
if mode=='expired': v['Expiration']='2000-01-01T00:00:00Z'
if mode=='missing': del v['SessionToken']
if mode=='bad-time': v['Expiration']='token_FAKE_SENTINEL'
if mode=='injection': v['SecretAccessKey']="quote$(touch${IFS}" + os.environ['TEST_MARKER'] + ")"
if mode=='malformed': print('{'); sys.exit(0)
print(json.dumps(v))
''')
    executable(fake / 'codex', '''import json,os,sys
from pathlib import Path
sys.stdin.read()
expected=['AKIA_FAKE_SENTINEL','secret_FAKE_SENTINEL','token_FAKE_SENTINEL']
if os.environ.get('TEST_MODE')=='injection': expected[1]="quote$(touch${IFS}" + os.environ['TEST_MARKER'] + ")"
names=['AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','AWS_SESSION_TOKEN']
# Booleans only: capture never writes credentials, even in a failing test.
r={'argv':sys.argv[1:], 'keys_match':all(os.environ.get(k)==v for k,v in zip(names,expected)),
   'keys_absent':all(k not in os.environ for k in names),
   'env':{k:v for k,v in os.environ.items() if k.startswith('AWS_') and k not in names}}
p=Path(os.environ['TEST_CAPTURE'])
p.write_text(json.dumps(r))
Path(os.environ['TEST_DONE']).touch()
''')
    def run(mode='ok', extra=None):
        state = tmp_path / 'state'
        env = {k:v for k,v in os.environ.items() if not k.startswith(('AWS_', 'CODEX_', 'GH_', 'GITHUB_'))}
        env.update(PATH=f'{fake}:{env["PATH"]}', HOME=str(tmp_path / 'home'),
                   CODEX_WATCH_DIR=str(state), CODEX_IMPL_ALLOW_MISSING_NODE_MODULES='1',
                   TEST_GITDIR=gitdir, TEST_COMMON=common, TEST_MODE=mode,
                   TEST_CAPTURE=str(tmp_path / 'capture'), TEST_CALLS=str(tmp_path / 'calls'),
                   TEST_MARKER=str(tmp_path / 'injected'), TEST_DONE=str(tmp_path / 'done'),
                   AWS_ACCESS_KEY_ID='parent_key', AWS_SECRET_ACCESS_KEY='parent_secret',
                   AWS_SESSION_TOKEN='parent_token', AWS_PROFILE='wrong-profile',
                   AWS_DEFAULT_PROFILE='prod', AWS_CONTAINER_CREDENTIALS_FULL_URI='http://unwanted',
                   AWS_ENDPOINT_URL_STS='http://unwanted')
        env.update(extra or {})
        result = subprocess.run(['bash', '-x', str(ROOT / 'bin/codex-impl'), str(work), str(prompt)],
                                env=env, capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stdout + result.stderr
        deadline = time.monotonic() + 8
        while not (tmp_path / 'done').exists() and time.monotonic() < deadline:
            time.sleep(.02)
        assert (tmp_path / 'done').exists(), result.stderr
        child = json.loads((tmp_path / 'capture').read_text())
        fields = dict(line.split('=',1) for line in next(state.glob('*.state')).read_text().splitlines())
        emitted = (result.stdout + result.stderr).encode() + b''.join(p.read_bytes() for p in state.rglob('*') if p.is_file())
        for secret in SECRETS + ['parent_key','parent_secret','parent_token']:
            assert secret.encode() not in emitted
            assert secret not in json.dumps(child['argv'])
        assert not (tmp_path / 'injected').exists()
        calls = [json.loads(line) for line in (tmp_path / 'calls').read_text().splitlines()]
        return child, fields, calls
    run.common, run.gitdir = common, gitdir
    return run


def settings(child):
    argv = child['argv']
    values = {}
    for i, arg in enumerate(argv):
        if arg == '-c':
            # Each override is parsed with TOML, so quoted/spaced paths are checked semantically.
            values.update(tomllib.loads(argv[i+1]))
    return values


def test_positive_permissions_environment(launch):
    child, fields, calls = launch()
    assert child['keys_match']
    assert fields['aws'] == 'dev-669126230735'
    assert fields['aws_expiration'] == '2099-01-02T03:04:05+00:00'
    assert len(calls) == 2
    argv = child['argv']
    assert '-s' not in argv and '--sandbox' not in argv
    assert not any('sandbox_workspace_write' in a for a in argv)
    config = settings(child)
    assert config['default_permissions'] == 'codex-impl-dev'
    fs = next(tomllib.loads(a)['permissions']['codex-impl-dev']['filesystem'] for a in argv if a.startswith('permissions.codex-impl-dev.filesystem='))
    assert fs == {'~/.aws':'deny',launch.common:'write',launch.gitdir:'write'}
    assert 'permissions.codex-impl-dev.extends=":workspace"' in argv
    assert 'permissions.codex-impl-dev.network.enabled=true' in argv
    assert 'shell_environment_policy.inherit="all"' in argv
    assert 'shell_environment_policy.ignore_default_excludes=true' in argv
    assert 'shell_environment_policy.set.AWS_PROFILE="codex-dev"' in argv
    env = child['env']
    assert env['AWS_PROFILE'] == 'codex-dev'
    assert 'AWS_DEFAULT_PROFILE' not in env
    assert 'AWS_CONTAINER_CREDENTIALS_FULL_URI' not in env
    assert 'AWS_ENDPOINT_URL_STS' not in env
    assert env['AWS_SHARED_CREDENTIALS_FILE'] == '/dev/null'
    assert Path(env['AWS_CONFIG_FILE']).read_text() == '[profile codex-dev]\nregion = ap-northeast-1\n'
    assert env['AWS_REGION'] == 'ap-northeast-1'
    assert env['AWS_EC2_METADATA_DISABLED'] == 'true'
    assert argv[argv.index('-m')+1] == 'gpt-6.1-sol'
    assert fields['mode'] == 'workspace-write'


@pytest.mark.parametrize('mode', ['wrong','sts-fail','export-fail','expired','missing','bad-time','malformed'])
def test_failure_has_no_credentials(launch, mode):
    child, fields, calls = launch(mode)
    assert child['keys_absent']
    assert fields['aws'] == 'none' and fields['aws_expiration'] == ''
    assert child['env']['AWS_PROFILE'] == 'codex-dev'
    assert 'AWS_DEFAULT_PROFILE' not in child['env']
    assert len(calls) == (1 if mode in ('wrong','sts-fail') else 2)


def test_export_is_data_not_shell(launch):
    child, fields, _ = launch('injection')
    assert child['keys_match']
    assert fields['aws'] == 'dev-669126230735'
