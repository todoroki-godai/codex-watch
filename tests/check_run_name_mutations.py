"""Disposable mutants; independently verify applied diff and executed changed line.

Run from the checkout: python3 tests/check_run_name_mutations.py
Full pytest output, applied diffs, and shell/Python traces stay in .tmp/*.log.
No real codex/LLM is invoked. All temporary files stay inside this checkout.
"""
import difflib
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
COMMON = 'bin/_codex_common.sh'
PREFIX = '''    printf '%s-%s\\n' "$issue" "$label"'''
BOUNDARY = 'if m.end() <= len(summary)'
EXTRACT = 'match = next((m for m in re.finditer(r"#[0-9]+", value) if m.end() <= len(summary)), None)'
RUN_ID = 'RUN_ID="$(codex_label_with_issue "$LABEL")-$(date +%Y%m%d-%H%M%S)-$$"'
PLAIN_ID = 'RUN_ID="${LABEL}-$(date +%Y%m%d-%H%M%S)-$$"'
# name, file, exact old, exact new, pytest selection, execution witness
MUTATIONS = [
    ('M1 omit prefix', COMMON, PREFIX, '''    printf '%s\\n' "$label"''',
     'test_label_issue', "printf '%s\\n' tally"),
    ('M2 double prefix', COMMON,
     'if [[ "$label" =~ (^|[^0-9])${issue}([^0-9]|$) ]]; then',
     'if [[ "$label" == __never_equal__ ]]; then',
     'test_label_issue', '== __never_equal__'),
    ('M3 substring match', COMMON,
     'if [[ "$label" =~ (^|[^0-9])${issue}([^0-9]|$) ]]; then',
     'if [[ "$label" == *"$issue"* ]]; then',
     'test_label_issue', r'== *\1\9\8\7*'),
    ('M4 ignore 60 boundary', COMMON, BOUNDARY, 'if True',
     'test_label_issue', 'PY_MUTATED_LINE'),
    ('M5a disconnect impl', 'bin/codex-impl', RUN_ID, PLAIN_ID,
     'test_real_run_identity', 'RUN_ID=tally-'),
    ('M5b disconnect review', 'bin/codex-review', RUN_ID, PLAIN_ID,
     'test_real_run_identity', 'RUN_ID=tally-'),
    ('M6 remove abnormal fallback', COMMON, '|| issue=0', '|| issue=""',
     'test_real_run_identity or test_label_issue or test_issue_number_checker_failure_allows_launch or test_issue_number_invalid_utf8_allows_launch', 'issue=\n'),
    ('M7 search truncated text', COMMON, 're.finditer(r"#[0-9]+", value)',
     're.finditer(r"#[0-9]+", summary)', 'test_label_issue', 'PY_MUTATED_LINE'),
    ('M8 select second number', COMMON, EXTRACT,
     'matches = [m for m in re.finditer(r"#[0-9]+", value) if m.end() <= len(summary)]\n'
     '        match = matches[1] if len(matches) > 1 else next(iter(matches), None)',
     'test_label_issue', 'PY_MUTATED_LINE'),
    # Preserve the first child; corrupt its report only during the second startup.
    ('M9 corrupt existing live report', 'bin/codex-review', RUN_ID,
     'for old_report in "$STATE_DIR"/*.report; do\n'
     '  [[ ! -f "$old_report" ]] || printf "corrupted\\n" > "$old_report"\ndone\n' + RUN_ID,
     'test_existing_live_run_preserved', "printf 'corrupted\\n'"),
    # Additional fault classes: label destruction and numeric representation loss.
    ('X1 strip non ASCII label', COMMON, 'local label="$1" issue',
     'local label="$(printf "%s" "$1" | LC_ALL=C tr -cd "\\\\000-\\\\177")" issue',
     'test_label_issue', r"tr -cd '\000-\177'"),
    ('X2 normalize leading zeros', COMMON, 'print(match.group()[1:])',
     'print(int(match.group()[1:]))', 'test_label_issue', 'PY_MUTATED_LINE'),
    ('X3 use review target as authority', COMMON,
     'issue="$(_codex_summary_normalized issue_value)" || issue=0',
     'issue="$(_codex_summary_normalized issue_value)" || issue=0\n'
     '  issue="${REVIEW_TARGET:-issue:other/repo#53}"; issue="${issue##*#}"',
     'test_label_issue', 'issue=53'),
]
CONTROL = ('P equivalent rewrite', COMMON, 'print(match.group()[1:])',
           'print(match.group()[1:][::1])', '', 'PY_MUTATED_LINE')


def python_tracer(path):
    # Trace the actual -c program in an independent interpreter wrapper. No changes
    # to the tested production source and no marker that substitutes for execution.
    path.write_text(f'''#!{sys.executable}
import json, os, sys
real = {sys.executable!r}
if len(sys.argv) > 2 and sys.argv[1] == '-c' and 'import re, sys' in sys.argv[2]:
    code = sys.argv[2]
    sys.argv = ['-c', *sys.argv[3:]]
    def trace(frame, event, arg):
        if event == 'line' and frame.f_code.co_filename == '<summary>':
            with open(os.environ['RUN_NAME_TRACE'], 'a') as output:
                output.write('PY ' + json.dumps({{
                    'line': frame.f_lineno, 'mode': sys.argv[-1],
                    'value': repr(frame.f_locals.get('value')),
                    'match': repr(frame.f_locals.get('match')),
                }}) + '\\n')
        return trace
    sys.settrace(trace)
    exec(compile(code, '<summary>', 'exec'), {{'__name__': '__main__'}})
else:
    os.execv(real, [real, *sys.argv[1:]])
''')
    path.chmod(0o755)


def check(case, expected):
    name, relative, old, new, selection, witness = case
    logs = ROOT / '.tmp'
    slug = name.split()[0]
    with tempfile.TemporaryDirectory(prefix=f'run-name-{slug}-', dir=logs) as temporary:
        folder = Path(temporary)
        for directory in ('bin', 'lib', 'tests', 'templates'):
            shutil.copytree(ROOT / directory, folder / directory,
                            ignore=shutil.ignore_patterns('__pycache__'))
        path = folder / relative
        before = path.read_text()
        assert before.count(old) == 1, (name, 'target must occur exactly once')
        after = before.replace(old, new)
        path.write_text(after)
        # (a) Re-read disk and compare expected complete contents and hashes.
        applied = path.read_text()
        assert applied == after and before != applied and old != new
        diff = ''.join(difflib.unified_diff(before.splitlines(True), applied.splitlines(True),
                                           fromfile=relative, tofile=relative))
        assert any(line.startswith('+') and not line.startswith('+++')
                   for line in diff.splitlines())
        (logs / f'{slug}-diff.log').write_text(diff)
        trace = logs / f'{slug}-trace.log'
        trace.write_text('')
        wrapper = folder / 'tracebin'
        wrapper.mkdir()
        python_tracer(wrapper / 'python3')
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(('CODEX_', 'REVIEW_', 'GH_', 'GITHUB_', 'AWS_'))}
        env.update(PATH=str(wrapper) + os.pathsep + os.environ['PATH'],
                   RUN_NAME_TRACE=str(trace), TMPDIR=str(folder),
                   GIT_CEILING_DIRECTORIES=str(ROOT))
        command = [sys.executable, '-m', 'pytest', '-vv',
                   'tests/test_run_name_issue.py', '--basetemp=' + str(folder / 'pytest'),
                   '--junitxml=' + str(logs / f'{slug}-junit.log')]
        if slug == 'M6':
            command += ['tests/test_codex_summary.py']
        if selection:
            command += ['-k', selection]
        result = subprocess.run(command, cwd=folder, env=env, capture_output=True,
                                text=True, timeout=240)
        (logs / f'{slug}-pytest.log').write_text(result.stdout + result.stderr)
        executed = trace.read_text()
        # (b) Python line events identify exactly the changed statement in the
        # -c source (issue_value, not merely the earlier boolean check).
        if witness == 'PY_MUTATED_LINE':
            code = applied.split("python3 -c '\nimport re, sys\n", 1)[1].split("\n' ", 1)[0]
            code = 'import re, sys\n' + code
            needle = new.splitlines()[-1].strip()
            line = next(i for i, text in enumerate(code.splitlines(), 1) if needle in text)
            events = [json.loads(row[3:]) for row in executed.splitlines() if row.startswith('PY ')]
            hits = sum(event['line'] == line and event['mode'] == 'issue_value' for event in events)
            evidence = f'Python issue_value line={line} hits={hits}'
        elif witness == 'RUN_ID=tally-':
            hits = len(re.findall(r'^STUB_REPORT:.*/tally-[0-9]', executed, re.M))
            evidence = f'offline child read numberless report path hits={hits}'
        else:
            hits = executed.count(witness)
            evidence = f'shell {witness.strip()!r} hits={hits}'
        assert hits, (name, 'changed line not executed', evidence)
        assert result.returncode == expected, (name, 'survived or infrastructure error', result.stdout)
        if slug == 'M6':
            legacy = [row for row in result.stdout.splitlines() if row.startswith('tests/test_codex_summary.py::')]
            assert len(legacy) == 10 and all(' PASSED' in row for row in legacy), legacy
        if expected == 1:
            reports = ET.parse(logs / f'{slug}-junit.log')
            failures = reports.findall('.//failure')
            assert failures and not reports.findall('.//error')
            assert all(failure.get('message', '').startswith(('assert ', 'AssertionError'))
                       for failure in failures), [failure.attrib for failure in failures]
        print(f'{name}: {"RED" if expected else "GREEN"}; '
              f'diff sha256={hashlib.sha256(applied.encode()).hexdigest()[:12]}; '
              f'{evidence}; {result.stdout.strip().splitlines()[-1]}', flush=True)


def main():
    (ROOT / '.tmp').mkdir(exist_ok=True)
    print('read_sha=' + subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), flush=True)
    for relative in (COMMON, 'bin/codex-impl', 'bin/codex-review',
                     'tests/test_run_name_issue.py', 'tests/check_run_name_mutations.py'):
        print('source_sha256=' + relative + ':' + hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), flush=True)
    for case in MUTATIONS:
        check(case, 1)
    check(CONTROL, 0)


if __name__ == '__main__':
    main()
