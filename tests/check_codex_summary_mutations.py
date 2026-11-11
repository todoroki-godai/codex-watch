"""Apply real faults in temporary copies, require an executed marker AND red tests.

Usage: python3 tests/check_codex_summary_mutations.py
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NORMALIZE = '  summary="$(sanitize_single_line "${CODEX_SUMMARY:-}")"'
TRIM = "    value = sys.argv[1].strip()\n    value.encode(\"utf-8\")\n    summary = value[:60]"
WRITE = '  [[ -n "$summary" ]] && printf \'summary=%s\\n\' "$summary"'
MUTATIONS = [
    ('M1 narrow normalization', 'bin/_codex_common.sh', NORMALIZE,
     '''  summary="$(python3 -c 'import os; print(os.environ.get("CODEX_SUMMARY", "").replace(chr(10), " ").replace(chr(13), " ").replace(chr(9), " "))')"''',
     'negative_line_injection'),
    ('M2 normalize wrong value', 'bin/_codex_common.sh', NORMALIZE,
     '''  summary="$(sanitize_single_line "${CODEX_IMPL_MODEL:-}")"
  summary="${CODEX_SUMMARY:-}"''', 'negative_line_injection'),
    ('M3 empty check before normalization', 'bin/_codex_common.sh', WRITE,
     '''  [[ -n "${CODEX_SUMMARY:-}" ]] && printf 'summary=%s\\n' "$summary"''',
     'negative_empty_after_normalization'),
    ('M4 truncate before trim', 'bin/_codex_common.sh', TRIM,
     '    value = sys.argv[1][:60].strip()\n    value.encode("utf-8")\n    summary = value', 'negative_trim_and_codepoint_limit'),
    ('M5 drop impl wiring', 'bin/codex-impl', '  codex_summary_state',
     '  : # summary omitted', 'positive_controls'),
    ('M6 drop review wiring', 'bin/codex-review', '  codex_summary_state',
     '  : # summary omitted', 'positive_controls'),
]


def main():
    for name, target, old, new, selection in MUTATIONS:
        with tempfile.TemporaryDirectory(prefix='summary-mutation-') as temporary:
            folder = Path(temporary)
            for directory in ('bin', 'lib', 'tests', 'templates'):
                shutil.copytree(ROOT / directory, folder / directory,
                                ignore=shutil.ignore_patterns('__pycache__'))
            path = folder / target
            source = path.read_text()
            assert source.count(old) == 1, (name, 'mutation must apply exactly once')
            # This marker executes in the mutated helper/writer, not just on import.
            # Python normalization mutations mark inside the executed try block.
            if old == TRIM:
                new = '    open(__import__("os").environ["SUMMARY_MUTATION_TRACE"], "a").write("hit\\n")\n' + new
            else:
                new = '  printf "hit\\n" >> "$SUMMARY_MUTATION_TRACE"\n' + new
            path.write_text(source.replace(old, new))
            trace = folder / 'trace'
            result = subprocess.run(
                ['python3', '-m', 'pytest', '-q', 'tests/test_codex_summary.py', '-k', selection],
                cwd=folder, env={**os.environ, 'SUMMARY_MUTATION_TRACE': str(trace)},
                capture_output=True, text=True, timeout=180)
            assert trace.exists() and trace.read_text().splitlines(), (name, 'branch not read', result.stdout, result.stderr)
            # Exit 1 is assertion failure; syntax/collection errors do not count.
            assert (result.returncode == 1 and 'AssertionError' in result.stdout
                    and any(point in result.stdout for point in
                            ('assert_preserved', 'summary_state', 'assert result.returncode == 0'))), (name, result.stdout, result.stderr)
            summary = result.stdout.strip().splitlines()[-1]
            print(f'{name}: RED; branch hits={len(trace.read_text().splitlines())}; {summary}', flush=True)


if __name__ == '__main__':
    main()
