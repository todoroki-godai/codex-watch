#!/usr/bin/env python3
"""Break isolated copies; negative survivors fail this command. Never run real AWS/Codex."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.tmp/awsdev4-mutations'
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT), 'commit first'
BASE = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
OUT.mkdir(parents=True, exist_ok=True)
cases = [
    ('remove-config-check', 'lib/codex_impl_aws.py', '        check_codex_config(sys.argv[2])', '        pass', 'config_rejected_before_launch or existing_set_cannot_reinject_prod'),
    ('weaken-aws-prefix', 'lib/codex_impl_aws.py', "key.startswith('AWS_')", "key.startswith('AWS_ACCESS_')", 'config_rejected_before_launch'),
    ('enumerate-known-aws-keys', 'lib/codex_impl_aws.py', "key.startswith('AWS_')", "key in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN', 'AWS_ENDPOINT_URL')", 'config_rejected_before_launch'),
    ('skip-profiles', 'lib/codex_impl_aws.py', '(data, *profiles.values())', '(data,)', 'config_rejected_before_launch'),
    ('ignore-invalid-config', 'lib/codex_impl_aws.py', "sys.exit('拒否: Codex 設定を読み取り・解析できず判定不能です')", 'pass', 'config_rejected_before_launch or unreadable_config_rejected'),
    ('wrong-account', 'lib/codex_impl_aws.py', "== '669126230735'", "!= '669126230735'", 'failure_has_no_credentials and wrong'),
    ('remove-deny', 'bin/codex-impl', "print('permissions.codex-impl-dev.filesystem={\"~/.aws\"=\"deny\"' +\n      ''.join(', ' + json.dumps(p, ensure_ascii=False) + '=\"write\"' for p in paths) + '}')", "print('permissions.codex-impl-dev.filesystem={' + ', '.join(json.dumps(p, ensure_ascii=False) + '=\"write\"' for p in paths) + '}')", 'positive_permissions'),
    ('remove-gitdir', 'bin/codex-impl', 'sys.argv[1:] if p', 'sys.argv[1:2] if p', 'positive_permissions'),
    ('leak-stdout', 'bin/codex-impl', 'unset AWS_ENV_UPDATES', 'echo "$AWS_ENV_UPDATES"\nunset AWS_ENV_UPDATES', 'positive_permissions'),
    ('restore-sandbox', 'bin/codex-impl', 'nohup codex exec -C', 'nohup codex exec -s workspace-write -C', 'positive_permissions'),
    # Additional bypass classes: ambient authority, time validity, code/data confusion.
    ('retain-parent-credentials', 'lib/codex_impl_aws.py', "if name.startswith(('AWS_', 'CODEX_AWS_DOCS_')) and", "if False and name.startswith(('AWS_', 'CODEX_AWS_DOCS_')) and", 'failure_has_no_credentials and wrong'),
    ('accept-expired', 'lib/codex_impl_aws.py', 'expiration <= dt.datetime.now(dt.timezone.utc)', 'False', 'failure_has_no_credentials and expired'),
    ('shell-expansion', 'lib/codex_impl_aws.py', 'shlex.quote(value)', 'value', 'export_is_data_not_shell'),
    ('leak-log', 'bin/codex-impl', 'CODEX_PID=$!', 'CODEX_PID=$!\nwhile [[ ! -f \"$TEST_DONE\" ]]; do sleep 0.01; done\nprintf "%s" "$AWS_SECRET_ACCESS_KEY" >> "$LOG_FILE"', 'positive_permissions'),
    ('leak-state', 'bin/codex-impl', '  echo "aws=$CODEX_IMPL_AWS_STATE"', '  echo "leaked=$AWS_SECRET_ACCESS_KEY"\n  echo "aws=$CODEX_IMPL_AWS_STATE"', 'positive_permissions'),
    ('leak-stderr', 'bin/codex-impl', 'unset AWS_ENV_UPDATES', 'echo "$AWS_ENV_UPDATES" >&2\nunset AWS_ENV_UPDATES', 'positive_permissions'),
    ('positive-equivalent', 'lib/codex_impl_aws.py', "== '669126230735'", "in ('669126230735',)", 'positive_permissions'),
    ('docs-remove-account', 'lib/codex_impl_aws.py', "identity['Account'] == '670352692792'", 'True', 'docs_failure_never_falls_back and (669126230735 or 682251233834)'),
    ('docs-remove-arn', 'lib/codex_impl_aws.py', "identity['Arn'].startswith('arn:aws:sts::670352692792:assumed-role/codex-readonly/')", 'True', 'docs_failure_never_falls_back and admin'),
    ('docs-export-head-profile', 'lib/codex_impl_aws.py', "['aws', 'sts', 'assume-role', '--profile', 'aws-updater-bc-dev',\n                    '--role-arn', 'arn:aws:iam::670352692792:role/codex-readonly',\n                    '--role-session-name', 'codex-impl', '--duration-seconds', '3600',\n                    '--output', 'json']", "['aws', 'configure', 'export-credentials', '--profile', 'aws-updater-bc-dev', '--format', 'process']", 'docs_verified_credentials_and_aliases and ok'),
    ('docs-retain-parent', 'lib/codex_impl_aws.py', 'del os.environ[name]', 'pass', 'docs_failure_never_falls_back and assume-fail'),
    ('docs-set-reinjection', 'lib/codex_impl_aws.py', "key.startswith('CODEX_AWS_DOCS_')", 'False', 'docs_config_reinjection_rejected'),
    # Independently explored input classes: namespace confusion and code/data confusion.
    ('docs-prefix-collision', 'lib/codex_impl_aws.py', "assumed-role/codex-readonly/'", "assumed-role/codex-readonly'", 'docs_failure_never_falls_back and prefix'),
    ('docs-partition-confusion', 'lib/codex_impl_aws.py', "identity['Arn'].startswith('arn:aws:sts::670352692792:assumed-role/codex-readonly/')", "'assumed-role/codex-readonly/' in identity['Arn']", 'docs_failure_never_falls_back and (partition or arn-account)'),

    ('docs-also-get-dev', 'lib/codex_impl_aws.py', '    updates = prepare(config, docs=docs)', '    prepare(config)\n    updates = prepare(config, docs=docs)', 'docs_verified_credentials_and_aliases and ok'),
    ('docs-fallback-dev', 'lib/codex_impl_aws.py', '    updates = prepare(config, docs=docs)', "    updates = prepare(config, docs=docs)\n    if 'AWS_ACCESS_KEY_ID' not in updates: updates.update(prepare(config))", 'docs_failure_never_falls_back and assume-fail'),
    ('docs-invalid-declaration', 'bin/_codex_common.sh', "if account != 'docs-ro':", 'if False:', 'invalid_declaration_rejected and dev'),
    ('docs-select-dev', 'lib/codex_impl_aws.py', "    docs = sys.argv[1:] == ['docs-ro']", '    docs = False', 'docs_verified_credentials_and_aliases and ok'),
    ('docs-standard-dev-credentials', 'lib/codex_impl_aws.py', '    updates = prepare(config, docs=docs)', "    updates = prepare(config, docs=docs)\n    if docs: updates.update(AWS_ACCESS_KEY_ID='DEVFAKEKEY', AWS_SECRET_ACCESS_KEY='devsecret', AWS_SESSION_TOKEN='devtok')", 'docs_launch_real_export'),
    # Additional bypass classes: declaration filesystem type and byte decoding.
    ('docs-unreadable-declaration', 'bin/_codex_common.sh', 'except (OSError, UnicodeError):\n    sys.exit(1)\nif account', "except (OSError, UnicodeError):\n    account = 'docs-ro'\nif account", 'invalid_declaration_rejected and (directory or dangling)'),
    ('docs-invalid-encoding', 'bin/_codex_common.sh', 'read_text().strip()\nexcept (OSError, UnicodeError):\n    sys.exit(1)\nif account', "read_text(errors='ignore').strip()\nexcept (OSError, UnicodeError):\n    sys.exit(1)\nif account", 'invalid_declaration_rejected'),
    ('docs-template-dev-key', 'templates/codex-docs-ro.aws-config', '$AWS_ACCESS_KEY_ID', '${DEV_KEY:-DEVFAKEKEY}', 'real_export_credentials and flag and True'),
    ('positive-docs-json-space', 'templates/codex-docs-ro.aws-config', '{"Version":1,', '{"Version": 1, ', 'real_export_credentials and flag and True'),

]
TRACE_WRAPPER = r'''import json,os,runpy,sys
from pathlib import Path
args=sys.argv[1:]
if not args or not (args[0] in ('-', '-c') or args[0].endswith('/lib/codex_impl_aws.py')):
    os.execv(sys.executable, [sys.executable, *args])
filename=args[0] if args[0] not in ('-', '-c') else ('<stdin>' if args[0]=='-' else '<string>')
source=(sys.stdin.read() if args[0]=='-' else args[1]) if filename.startswith('<') else Path(filename).read_text()
lines=set()
def trace(frame,event,arg):
    if event=='line' and frame.f_code.co_filename==filename: lines.add(frame.f_lineno)
    return trace
sys.argv=args if args[0]!='-c' else ['-c',*args[2:]]
sys.settrace(trace)
try:
    if filename.startswith('<'): exec(compile(source,filename,'exec'), {'__name__':'__main__'})
    else: runpy.run_path(filename,run_name='__main__')
finally:
    sys.settrace(None)
    Path(os.environ['CODEX_MUTATION_TRACE'],str(os.getpid())+'.json').write_text(json.dumps({'filename':filename,'source':source,'lines':sorted(lines)}))
'''
results = []
for name, filename, old, new, select in cases:
    folder = OUT / name
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir()
    for sub in ('bin', 'lib', 'templates'):
        shutil.copytree(ROOT / sub, folder / sub, ignore=shutil.ignore_patterns('__pycache__'))
    original = (folder / filename).read_text()
    assert original.count(old) == (2 if name == 'accept-expired' else 3 if filename == 'templates/codex-docs-ro.aws-config' else 1), (name, old)
    mutated = original.replace(old, new)
    if name == 'docs-export-head-profile':
        mutated = mutated.replace("data = data['Credentials']", "data = data.get('Credentials', data)")
    diff = ''.join(difflib.unified_diff(original.splitlines(True), mutated.splitlines(True), fromfile=filename, tofile=filename))
    assert diff and original != mutated
    (folder / 'mutation.diff').write_text(diff)
    changed = {i+1 for tag, a, b, c, d in difflib.SequenceMatcher(None, original.splitlines(), mutated.splitlines()).get_opcodes() if tag != 'equal' for i in range(c,d)}
    (folder / filename).write_text(mutated)
    trace_dir = folder / 'trace'
    trace_dir.mkdir()
    if filename.startswith('templates/'):
        # Absolute /bin/sh bypasses PATH wrappers. A line marker inside each
        # actually executed credential_process observes that exact shell line.
        import configparser, shlex
        cfg = configparser.ConfigParser(interpolation=None)
        cfg.read(folder / filename)
        for section in cfg.sections():
            command = shlex.split(cfg[section]['credential_process'])
            line = next(i+1 for i,l in enumerate(mutated.splitlines()) if cfg[section]['credential_process'] in l)
            command[2] = 'printf "%s\\n" ' + str(line) + ' >> "$CODEX_MUTATION_TRACE/template-lines"; ' + command[2]
            cfg[section]['credential_process'] = shlex.join(command)
        with (folder / filename).open('w') as stream: cfg.write(stream)
    wrapper_dir = folder / 'trace-bin'
    wrapper_dir.mkdir()
    # Trace code lines without recording locals, environment values, or AWS output.
    wrapper = wrapper_dir / 'python3'
    wrapper.write_text('#!' + sys.executable + '\n' + TRACE_WRAPPER)
    wrapper.chmod(0o755)
    # Shell DEBUG observes line numbers only. Python stdin tracing covers heredocs.
    shell = folder / 'bin/codex-impl'
    shell.write_text(shell.read_text().replace('set -euo pipefail', 'set -euo pipefail\ntrap \'printf "%s\\n" "$LINENO" >> "$CODEX_MUTATION_TRACE/bash-lines"\' DEBUG'))
    command = [sys.executable, '-m', 'pytest', str(ROOT / 'tests/test_codex_impl_aws.py'),
               '-q', '--tb=short', '-k', select, '--basetemp', str(folder / 'tmp')]
    env = dict(os.environ, CODEX_AWS_TEST_ROOT=str(folder), PYTHONDONTWRITEBYTECODE='1',
               CODEX_MUTATION_TRACE=str(trace_dir), PATH=str(wrapper_dir)+os.pathsep+os.environ['PATH'])
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=45)
    (folder / 'pytest.log').write_text(result.stdout + result.stderr)
    expected = 0 if name.startswith('positive-') else 1
    # Require assertion failure, not a setup/import/collection failure.
    ok = result.returncode == expected and ((('AssertionError' in result.stdout or 'E   assert' in result.stdout) and 'TOMLDecodeError' not in result.stdout and 'ERROR ' not in result.stdout) if expected else 'passed' in result.stdout)
    reached = set()
    for trace_file in trace_dir.glob('*.json'):
        trace = json.loads(trace_file.read_text())
        if trace['filename'] == str(folder / filename):
            reached.update(trace['lines'])
        elif trace['filename'] in ('<stdin>', '<string>'):
            source = trace['source']
            if filename.startswith('bin/') and source in mutated:
                start = mutated[:mutated.index(source)].count('\n')
                reached.update(start + line for line in trace['lines'])
            elif filename.startswith('templates/') and source in mutated:
                # credential_process is a one-line Python program, executed by the test.
                reached.update(i+1 for i,line in enumerate(mutated.splitlines()) if source in line)
    if filename.startswith('bin/') and (trace_dir / 'bash-lines').exists():
        # Instrumentation inserted exactly one line after set -euo pipefail.
        reached.update(int(line)-1 for line in (trace_dir / 'bash-lines').read_text().splitlines())
    if (trace_dir / 'template-lines').exists():
        reached.update(int(line) for line in (trace_dir / 'template-lines').read_text().splitlines())
    hit = sorted(changed & reached)
    ok = ok and bool(hit)
    record = dict(name=name, baseline=BASE, diff_sha256=hashlib.sha256(diff.encode()).hexdigest(),
                  changed_lines=sorted(changed), executed_changed_lines=hit, command=command, exit=result.returncode, ok=ok,
                  transformation={'file':filename,'old':old,'new':new},
                  summary=result.stdout.strip().splitlines()[-1])
    # Restore the isolated copy too; preserve only diff/trace/test evidence.
    restored = []
    for relative in dict.fromkeys((filename, 'bin/codex-impl')):
        target = folder / relative
        target.write_bytes((ROOT / relative).read_bytes())
        restored.append(target.read_bytes() == (ROOT / relative).read_bytes())
    record['restored'] = all(restored)
    record['ok'] = record['ok'] and record['restored']
    results.append(record)
    print(json.dumps(record, ensure_ascii=False), flush=True)
    (OUT / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip() == BASE
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT), 'dirty after mutations'
print(f"{sum(r['ok'] for r in results)}/{len(results)} mutations verified; worktree clean")
sys.exit(0 if all(record['ok'] for record in results) else 1)
