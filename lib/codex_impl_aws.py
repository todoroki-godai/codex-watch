"""Emit shell-quoted environment updates in memory only; never log AWS output."""
import datetime as dt
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tomllib


def check_codex_config(workdir):
    """Reject AWS set overrides before launch; never include config values in errors."""
    paths = [Path.home() / '.codex/config.toml']
    if os.environ.get('CODEX_HOME'):
        paths.append(Path(os.environ['CODEX_HOME']) / 'config.toml')
    # Codex can load project config from ancestors as well as the working directory.
    work = Path(workdir).resolve()
    paths.extend(parent / '.codex/config.toml' for parent in (work, *work.parents))
    for path in dict.fromkeys(paths):
        try:
            try:
                with path.open('rb') as stream:
                    data = tomllib.load(stream)
            except FileNotFoundError:
                if path.is_symlink():
                    raise ValueError('dangling config') from None
                continue  # An absent optional config is normal.
            profiles = data.get('profiles', {})
            if not isinstance(profiles, dict):
                raise ValueError('invalid profiles')
            for scope in (data, *profiles.values()):
                if not isinstance(scope, dict):
                    raise ValueError('invalid profile')
                policy = scope.get('shell_environment_policy', {})
                if not isinstance(policy, dict):
                    raise ValueError('invalid policy')
                overrides = policy.get('set', {})
                if not isinstance(overrides, dict):
                    raise ValueError('invalid set')
                if any(key.startswith('AWS_') and key != 'AWS_PROFILE' for key in overrides):
                    sys.exit('拒否: Codex 設定の set に AWS_PROFILE 以外の AWS_ キーがあります')
        except (OSError, ValueError):
            sys.exit('拒否: Codex 設定を読み取り・解析できず判定不能です')


def prepare(config):
    updates = {
        'AWS_CONFIG_FILE': config, 'AWS_SHARED_CREDENTIALS_FILE': '/dev/null',
        'AWS_REGION': 'ap-northeast-1', 'AWS_DEFAULT_REGION': 'ap-northeast-1',
        'AWS_PROFILE': 'codex-dev', 'AWS_EC2_METADATA_DISABLED': 'true',
        'CODEX_IMPL_AWS_STATE': 'none', 'CODEX_IMPL_AWS_EXPIRATION': '',
    }
    try:
        # Disallow inherited endpoint redirection for the account check/export.
        probe_env = {k: v for k, v in os.environ.items()
                     if not k.startswith('AWS_ENDPOINT_URL')}
        probe_env['AWS_IGNORE_CONFIGURED_ENDPOINT_URLS'] = 'true'
        data = json.loads(subprocess.run(
            ['aws', 'configure', 'export-credentials', '--format', 'process',
             '--profile', 'aws-updater-index-stg'], env=probe_env,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30, check=True).stdout)
        keys = {'AWS_ACCESS_KEY_ID': 'AccessKeyId',
                'AWS_SECRET_ACCESS_KEY': 'SecretAccessKey', 'AWS_SESSION_TOKEN': 'SessionToken'}
        credentials = {name: data[field] for name, field in keys.items()}
        if not all(isinstance(v, str) and v and all(33 <= ord(c) <= 126 for c in v)
                   for v in credentials.values()):
            raise ValueError('invalid credentials')
        expiration = dt.datetime.fromisoformat(data['Expiration'].replace('Z', '+00:00'))
        if expiration.tzinfo is None or expiration <= dt.datetime.now(dt.timezone.utc):
            raise ValueError('invalid expiration')
        # Freeze one export. STS must authenticate precisely these credentials;
        # no profile, parent AWS variable, endpoint, or on-disk credential source.
        identity_env = {k: v for k, v in os.environ.items() if not k.startswith('AWS_')}
        identity_env.update(updates)
        identity_env.pop('AWS_PROFILE')
        identity_env.update(credentials)
        identity_env['AWS_IGNORE_CONFIGURED_ENDPOINT_URLS'] = 'true'
        account = subprocess.run(
            ['aws', 'sts', 'get-caller-identity', '--query', 'Account', '--output', 'text'],
            env=identity_env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=30, check=True).stdout
        if account.decode().strip() == '669126230735':
            # STS may take time; do not publish credentials that expired during it.
            if expiration <= dt.datetime.now(dt.timezone.utc):
                raise ValueError('invalid expiration')
            updates.update(credentials)
            updates['CODEX_IMPL_AWS_STATE'] = 'dev-669126230735'
            updates['CODEX_IMPL_AWS_EXPIRATION'] = expiration.isoformat()
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError, AttributeError):
        pass  # No raw exception/output: either can contain credentials.
    return updates


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--check-config':
        check_codex_config(sys.argv[2])
        sys.exit(0)
    config = str(Path(__file__).resolve().parents[1] / 'templates/codex-dev.aws-config')
    updates = prepare(config)
    # The only eval input is generated statements with shlex-quoted values.
    for name in os.environ:
        if name.startswith('AWS_') and name.isidentifier() and name.isascii():
            print('unset ' + name)
    for name, value in updates.items():
        print('export ' + name + '=' + shlex.quote(value))
