"""Emit shell-quoted environment updates in memory only; never log AWS output."""
import datetime as dt
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys


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
        def aws(*args):
            return subprocess.run(['aws', *args, '--profile', 'aws-updater-index-stg'],
                                  env=probe_env, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, timeout=30, check=True).stdout
        account = aws('sts', 'get-caller-identity', '--query', 'Account', '--output', 'text')
        if account.decode().strip() == '669126230735':
            data = json.loads(aws('configure', 'export-credentials', '--format', 'process'))
            keys = {'AWS_ACCESS_KEY_ID': 'AccessKeyId',
                    'AWS_SECRET_ACCESS_KEY': 'SecretAccessKey', 'AWS_SESSION_TOKEN': 'SessionToken'}
            credentials = {name: data[field] for name, field in keys.items()}
            if not all(isinstance(v, str) and v and all(33 <= ord(c) <= 126 for c in v)
                       for v in credentials.values()):
                raise ValueError('invalid credentials')
            expiration = dt.datetime.fromisoformat(data['Expiration'].replace('Z', '+00:00'))
            if expiration.tzinfo is None or expiration <= dt.datetime.now(dt.timezone.utc):
                raise ValueError('invalid expiration')
            updates.update(credentials)
            updates['CODEX_IMPL_AWS_STATE'] = 'dev-669126230735'
            updates['CODEX_IMPL_AWS_EXPIRATION'] = expiration.isoformat()
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError, AttributeError):
        pass  # No raw exception/output: either can contain credentials.
    return updates


if __name__ == '__main__':
    config = str(Path(__file__).resolve().parents[1] / 'templates/codex-dev.aws-config')
    updates = prepare(config)
    # The only eval input is generated statements with shlex-quoted values.
    for name in os.environ:
        if name.startswith('AWS_') and name.isidentifier() and name.isascii():
            print('unset ' + name)
    for name, value in updates.items():
        print('export ' + name + '=' + shlex.quote(value))
