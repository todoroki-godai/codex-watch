"""Mutate disposable copies, require executed faults and assertion failures.

Usage: python3 tests/check_summary_issue_mutations.py
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CHECK = '  _codex_summary_normalized issue || status=$?'
PATTERN = 're.finditer(r"#[0-9]+", value)'
MUTATIONS = [
    ('M1 require number at start', PATTERN,
     PATTERN.replace('#[0-9]+', '^#[0-9]+'), 'issue_number_positive_controls'),
    ('M2 reject numberless escape', PATTERN,
     PATTERN.replace('#[0-9]+', '#[1-9][0-9]*'), 'issue_number_positive_controls'),
    ('M3 check without truncation', 'summary = value[:60]',
     'summary = value', 'issue_number_rejects_outside_saved_boundary'),
    ('M4 shift boundary to 61', 'summary = value[:60]',
     'summary = value[:61]', 'issue_number_rejects_outside_saved_boundary'),
    ('M5 accept a cut number', PATTERN,
     PATTERN.replace(', value)', ', summary)'), 'issue_number_rejects_outside_saved_boundary'),
    ('M6 reject checker failures', 'if [[ "$status" -eq 1 ]]; then',
     'if [[ "$status" -ne 0 ]]; then', 'issue_number_checker_failure_allows_launch or issue_number_invalid_utf8'),
]


def main():
    for name, target, replacement, selection in MUTATIONS:
        with tempfile.TemporaryDirectory(prefix='summary-issue-mutation-') as temporary:
            folder = Path(temporary)
            for directory in ('bin', 'lib', 'tests', 'templates'):
                shutil.copytree(ROOT / directory, folder / directory,
                                ignore=shutil.ignore_patterns('__pycache__'))
            path = folder / 'bin/_codex_common.sh'
            source = path.read_text()
            assert source.count(target) == 1, (name, 'mutation must apply exactly once')
            source = source.replace(target, replacement)
            path.write_text(source.replace(CHECK,
                '  printf "hit\\n" >> "$SUMMARY_MUTATION_TRACE"\n' + CHECK))
            trace = folder / 'trace'
            result = subprocess.run(
                ['python3', '-m', 'pytest', '-q', 'tests/test_codex_summary.py',
                 '-k', selection],
                cwd=folder, env={**os.environ, 'SUMMARY_MUTATION_TRACE': str(trace)},
                capture_output=True, text=True, timeout=180)
            assert trace.exists() and trace.read_text().splitlines(), (name, result.stdout, result.stderr)
            assert result.returncode == 1 and 'AssertionError' in result.stdout, (
                name, 'mutation survived or test infrastructure failed', result.stdout, result.stderr)
            print(f'{name}: RED; branch hits={len(trace.read_text().splitlines())}; '
                  + result.stdout.strip().splitlines()[-1], flush=True)


if __name__ == '__main__':
    main()
