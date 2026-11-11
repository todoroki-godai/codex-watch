"""Mutate disposable copies, require executed faults and assertion failures.

Usage: python3 tests/check_summary_issue_mutations.py
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CHECK = '''  LC_ALL=C grep -Eq '#[0-9]+' <<< "${CODEX_SUMMARY:-}" || status=$?'''
MUTATIONS = [
    ('M1 require number at start', CHECK.replace("'#[0-9]+'", "'^#[0-9]+'")),
    ('M2 reject numberless escape', CHECK.replace("'#[0-9]+'", "'#[1-9][0-9]*'")),
    ('M3 truncate before checking', CHECK.replace('${CODEX_SUMMARY:-}', '${CODEX_SUMMARY:0:60}')),
]


def main():
    for name, replacement in MUTATIONS:
        with tempfile.TemporaryDirectory(prefix='summary-issue-mutation-') as temporary:
            folder = Path(temporary)
            for directory in ('bin', 'lib', 'tests', 'templates'):
                shutil.copytree(ROOT / directory, folder / directory,
                                ignore=shutil.ignore_patterns('__pycache__'))
            path = folder / 'bin/_codex_common.sh'
            source = path.read_text()
            assert source.count(CHECK) == 1, (name, 'mutation must apply exactly once')
            path.write_text(source.replace(CHECK,
                '  printf "hit\\n" >> "$SUMMARY_MUTATION_TRACE"\n' + replacement))
            trace = folder / 'trace'
            result = subprocess.run(
                ['python3', '-m', 'pytest', '-q', 'tests/test_codex_summary.py',
                 '-k', 'issue_number_positive_controls'],
                cwd=folder, env={**os.environ, 'SUMMARY_MUTATION_TRACE': str(trace)},
                capture_output=True, text=True, timeout=180)
            assert trace.exists() and trace.read_text().splitlines(), (name, result.stdout, result.stderr)
            assert result.returncode == 1 and 'AssertionError' in result.stdout, (
                name, 'mutation survived or test infrastructure failed', result.stdout, result.stderr)
            print(f'{name}: RED; branch hits={len(trace.read_text().splitlines())}; '
                  + result.stdout.strip().splitlines()[-1], flush=True)


if __name__ == '__main__':
    main()
