#!/usr/bin/env python3
"""Break isolated copies; negative survivors fail this command. Never run real AWS/Codex."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.tmp/awsdev2-mutations'
OUT.mkdir(parents=True, exist_ok=True)
cases = [
    ('wrong-account', 'lib/codex_impl_aws.py', "== '669126230735'", "!= '669126230735'", 'failure_has_no_credentials and wrong'),
    ('remove-deny', 'bin/codex-impl', '"~/.aws"="deny"', '', 'positive_permissions'),
    ('remove-gitdir', 'bin/codex-impl', 'sys.argv[1:] if p', 'sys.argv[1:2] if p', 'positive_permissions'),
    ('leak-stdout', 'bin/codex-impl', 'unset AWS_ENV_UPDATES', 'echo "$AWS_ENV_UPDATES"\nunset AWS_ENV_UPDATES', 'positive_permissions'),
    ('restore-sandbox', 'bin/codex-impl', 'nohup codex exec -C', 'nohup codex exec -s workspace-write -C', 'positive_permissions'),
    # Additional bypass classes: ambient authority, time validity, code/data confusion.
    ('retain-parent-credentials', 'lib/codex_impl_aws.py', "if name.startswith('AWS_') and", "if False and name.startswith('AWS_') and", 'failure_has_no_credentials and wrong'),
    ('accept-expired', 'lib/codex_impl_aws.py', 'expiration <= dt.datetime.now(dt.timezone.utc)', 'False', 'failure_has_no_credentials and expired'),
    ('shell-expansion', 'lib/codex_impl_aws.py', 'shlex.quote(value)', 'value', 'export_is_data_not_shell'),
    ('leak-log', 'bin/codex-impl', 'CODEX_PID=$!', 'CODEX_PID=$!\nwhile [[ ! -f \"$TEST_DONE\" ]]; do sleep 0.01; done\nprintf "%s" "$AWS_SECRET_ACCESS_KEY" >> "$LOG_FILE"', 'positive_permissions'),
    ('leak-state', 'bin/codex-impl', '  echo "aws=$CODEX_IMPL_AWS_STATE"', '  echo "leaked=$AWS_SECRET_ACCESS_KEY"\n  echo "aws=$CODEX_IMPL_AWS_STATE"', 'positive_permissions'),
    ('leak-stderr', 'bin/codex-impl', 'unset AWS_ENV_UPDATES', 'echo "$AWS_ENV_UPDATES" >&2\nunset AWS_ENV_UPDATES', 'positive_permissions'),
    ('positive-equivalent', 'lib/codex_impl_aws.py', "== '669126230735'", "in ('669126230735',)", 'positive_permissions'),
]
results = []
for name, filename, old, new, select in cases:
    folder = OUT / name
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir()
    for sub in ('bin', 'lib', 'templates'):
        shutil.copytree(ROOT / sub, folder / sub, ignore=shutil.ignore_patterns('__pycache__'))
    original = (folder / filename).read_text()
    assert original.count(old) == 1, (name, old)
    (folder / filename).write_text(original.replace(old, new))
    command = [sys.executable, '-m', 'pytest', str(ROOT / 'tests/test_codex_impl_aws.py'),
               '-q', '--tb=short', '-k', select, '--basetemp', str(folder / 'tmp')]
    env = dict(os.environ, CODEX_AWS_TEST_ROOT=str(folder), PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=45)
    (folder / 'pytest.log').write_text(result.stdout + result.stderr)
    expected = 0 if name.startswith('positive-') else 1
    # Require assertion failure, not a setup/import/collection failure.
    ok = result.returncode == expected and ('FAILED ' in result.stdout if expected else '1 passed' in result.stdout)
    record = dict(name=name, command=command, exit=result.returncode, ok=ok,
                  transformation={'file':filename,'old':old,'new':new},
                  summary=result.stdout.strip().splitlines()[-1])
    results.append(record)
    print(json.dumps(record, ensure_ascii=False), flush=True)
    (OUT / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
    if not ok:
        sys.exit(1)
