#!/usr/bin/env python3
"""Run the browser contract tests against traced mutations of isolated launcher copies."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import mkdtemp

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.tmp/auto-browser-cdp/mutations'
LAUNCHER = Path('bin/codex-impl')
TRIGGER = 'test_trigger and PlAyWrIgHt'
CASES = (
    ('M1-trigger-gate', 'if not any(word in body for word in words):', 'if False:',
     'test_skip and no-word'),
    ('M2-prompt-suffix', "write_bytes(prompt + ('\\n\\n' + suffix + '\\n').encode('utf-8'))",
     'write_bytes(prompt)', TRIGGER),
    ('M3-timeout-wrapper', "'nohup', 'timeout', '-k', '10', '5400', str(chromium.absolute())",
     "'nohup', str(chromium.absolute())", TRIGGER),
    ('M4-browser-path', 'if remote_path != browser_path:', 'if False:',
     'test_browser_failure and mismatch'),
    ('N1-delete-argument', "'--no-first-run', 'about:blank'", "'about:blank'", TRIGGER),
    ('N2-bind-address', "'--remote-debugging-address=127.0.0.1'",
     "'--remote-debugging-address=127.0.0.1'.replace('127.0.0.1', '0.0.0.0')", TRIGGER),
    ('N3-swap-marker-lines', 'port, browser_path = lines[:2]', 'browser_path, port = lines[:2]',
     'test_manual_requires_numeric_port'),
    ('N4-ignore-browser-exit', "sys.exit(f'Chromium が準備前に終了しました: {log}')",
     'sys.exit(0)', 'test_browser_failure and exit'),
    ('X1-lexicographic-revision', "int(path.name.rsplit('-', 1)[1])",
     "path.name.rsplit('-', 1)[1]", 'test_highest_numeric_revision'),
    ('X2-invert-manual-port', "if 'connectovercdp' in body and re.search(",
     "if 'connectovercdp' in body and not re.search(", 'test_skip and connectovercdp and 41000'),
    ('P1-equivalent-trigger', 'if not any(word in body for word in words):',
     'if all(word not in body for word in words):', f'({TRIGGER}) or (test_skip and no-word)'),
)

# Trace only the browser heredoc. Keep stderr and the launcher's stdin/stdout unchanged.
TRACE_PYTHON = r'''
import os
from pathlib import Path
import sys

args = sys.argv[1:]
if len(args) != 4 or args[0] != '-' or not args[-1].endswith('/templates/browser-cdp.md'):
    os.execv(sys.executable, [sys.executable, *args])
source = sys.stdin.read()
sys.argv = args
seen = set()


def trace(frame, event, arg):
    if frame.f_code.co_filename == '<browser>' and event == 'line':
        seen.add(frame.f_lineno)
    return trace


sys.settrace(trace)
try:
    exec(compile(source, '<browser>', 'exec'), {'__name__': '__main__'})
finally:
    sys.settrace(None)
    dest = Path(os.environ['CODEX_BROWSER_TRACE'])
    (dest / f'{os.getpid()}.lines').write_text('\n'.join(map(str, sorted(seen))))
'''


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def check_case(case, out, base, original):
    name, old, new, select = case
    folder = out / name
    folder.mkdir()
    for directory in ('bin', 'lib', 'templates'):
        shutil.copytree(ROOT / directory, folder / directory, ignore=shutil.ignore_patterns('__pycache__'))
    assert original.count(old) == 1, (name, old)
    mutated = original.replace(old, new)
    diff = ''.join(difflib.unified_diff(original.splitlines(True), mutated.splitlines(True),
                                       fromfile=str(LAUNCHER), tofile=str(LAUNCHER)))
    assert diff, name
    (folder / 'mutation.diff').write_text(diff)
    (folder / LAUNCHER).write_text(mutated)

    wrapper = folder / 'trace-bin/python3'
    wrapper.parent.mkdir()
    wrapper.write_text(f'#!{sys.executable}\n' + TRACE_PYTHON)
    wrapper.chmod(0o755)
    cmd = [sys.executable, '-m', 'pytest', '-q', '--tb=short', '-p', 'no:cacheprovider',
           'tests/test_codex_impl_browser.py', '-k', select, '--basetemp', str(folder / 'pytest')]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', CODEX_BROWSER_TEST_ROOT=str(folder),
               CODEX_BROWSER_TRACE=str(folder), PATH=str(wrapper.parent) + os.pathsep + os.environ['PATH'])
    result = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    (folder / 'pytest.log').write_text(result.stdout + result.stderr)

    first_source_line = mutated[:mutated.index("<<'PYBROWSER'")].count('\n') + 2
    changed_line = mutated[:original.index(old)].count('\n') + 1
    executed = {first_source_line + int(line) - 1 for trace in folder.glob('*.lines')
                for line in trace.read_text().splitlines()}
    hit = changed_line in executed
    positive = name.startswith('P')
    assertion_failed = 'E   AssertionError' in result.stdout or 'E   assert' in result.stdout
    expected = (result.returncode == 0 and '2 passed' in result.stdout if positive else
                result.returncode == 1 and '1 failed' in result.stdout and
                assertion_failed and 'ERROR ' not in result.stdout)
    return dict(name=name, base=base, diff_sha256=hashlib.sha256(diff.encode()).hexdigest(),
                changed_line=changed_line, executed_changed_line=hit, command=cmd,
                exit=result.returncode, summary=result.stdout.strip().splitlines()[-1],
                ok=hit and expected)


def main():
    assert not git('status', '--porcelain'), 'commit the implementation and tests first'
    base = git('rev-parse', 'HEAD').decode().strip()
    original = (ROOT / LAUNCHER).read_text()
    OUT.mkdir(parents=True, exist_ok=True)
    # Write each run separately so evidence from prior runs cannot supply a trace.
    out = Path(mkdtemp(prefix='run-', dir=OUT))
    print(f'Evidence: {out}', flush=True)
    records = []
    for case in CASES:
        row = check_case(case, out, base, original)
        records.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    (out / 'results.json').write_text(json.dumps(records, indent=2, ensure_ascii=False))
    assert git('rev-parse', 'HEAD').decode().strip() == base
    assert not git('status', '--porcelain'), 'working tree changed during mutation testing'
    print(f'{sum(row["ok"] for row in records)}/{len(records)} results verified')
    return 0 if all(row['ok'] for row in records) else 1


if __name__ == '__main__':
    sys.exit(main())
