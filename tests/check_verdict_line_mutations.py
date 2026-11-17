"""Mutate isolated checkout copies; require every defective variant to turn red."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.tmp/verdict-line-mutations'
SOURCE = 'lib/round_gate.py'
CASES = [
    ('value', 'prefix = "判定保留: "', 'prefix = "判定保留"', 'negative_receipt_cli', True),
    ('condition', 'first in ("実装着手可", "設計修正要")',
     'first in ("実装着手可", "設計修正要", "マージ可")', 'negative_receipt_cli', True),
    ('branch', 'first = lines[0] if lines else ""',
     'first = lines[0] if lines else "実装着手可"', 'negative_receipt_cli', True),
    ('order', 'first = lines[0] if lines else ""',
     'first = next((line for line in lines if line in ("実装着手可", "設計修正要")), lines[0] if lines else "")',
     'negative_receipt_cli', True),
    # Different from input rewriting: disconnect the check from its consumer.
    ('extra-disconnect', 'if verdict.status == "rejected":', 'if False:',
     'negative_receipt_cli or negative_status_and_history', True),
    # Different failure mode again: reverse the exception policy.
    ('extra-fail-closed', 'except Exception:\n        return ReceiptCheck("ok", "")',
     'except Exception:\n        return ReceiptCheck("rejected", "validator error")',
     'fail_open', True),
    ('positive-equivalent', 'first in ("実装着手可", "設計修正要")',
     'first in {"実装着手可", "設計修正要"}', '', False),
]

CONTROL_CASES = [
    (SOURCE, 'control-splitlines', 'lines = text.split("\\n")',
     'lines = text.splitlines()', 'separator_bypass or control_anywhere', True),
    (SOURCE, 'control-disabled', 'if any((ord(c) < 32',
     'if False and any((ord(c) < 32', 'control_anywhere', True),
    (SOURCE, 'claim-splitlines', 'lines = split_receipt_lines(report_text or "")',
     'lines = (report_text or "").splitlines()', 'separator_bypass', True),
    (SOURCE, 'crlf-rejected', 'i < len(lines) - 1 and line.endswith("\\r")',
     'False', 'all_verdicts_both_endings', True),
    # Distinct from character/separator changes: erase bytes at the I/O boundaries.
    (SOURCE, 'extra-cli-newline-folding', 'Path(args.report).open(newline="")',
     'Path(args.report).open()', 'stray_cr', True),
    ('lib/routing_record.py', 'extra-history-newline-folding',
     "Path(d['report']).open(newline='')", "Path(d['report']).open()", 'stray_cr', True),
]


def main():
    originals = {path: (ROOT / path).read_bytes() for path in (SOURCE, 'lib/routing_record.py')}
    original = originals[SOURCE]
    results = []
    for source, name, old, new, selector, expect_red in [(SOURCE, *case) for case in CASES] + CONTROL_CASES:
        folder = OUT / name
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True)
        for sub in ('bin', 'lib', 'templates', 'tests'):
            shutil.copytree(ROOT / sub, folder / sub, ignore=shutil.ignore_patterns('__pycache__'))
        path = folder / source
        text = path.read_text()
        assert text.count(old) == (2 if name == 'claim-splitlines' else 1), name
        mutated = text.replace(old, new, 1)
        (folder / 'mutation.diff').write_text(''.join(difflib.unified_diff(
            text.splitlines(True), mutated.splitlines(True), fromfile=source, tofile=source)))
        path.write_text(mutated)
        command = [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                   '--basetemp=' + str(folder / 'tmp'), 'tests/test_verdict_line.py']
        if selector:
            command += ['-k', selector]
        run = subprocess.run(command, cwd=folder, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'),
                             capture_output=True, text=True)
        output = run.stdout + run.stderr
        (folder / 'pytest.log').write_text(output)
        # Syntax/import errors do not count as killed mutations.
        red = run.returncode == 1 and ' failed' in output and 'ERROR collecting' not in output
        passed = red if expect_red else run.returncode == 0
        results.append(dict(name=name, source=source, old=old, new=new, returncode=run.returncode,
                            result='red' if red else 'green' if run.returncode == 0 else 'error',
                            expected='red' if expect_red else 'green', passed=passed,
                            source_sha256=hashlib.sha256(mutated.encode()).hexdigest(),
                            pytest_summary=output.strip().splitlines()[-1]))
    assert all((ROOT / path).read_bytes() == data for path, data in originals.items())
    result = dict(baseline_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  original_sha256=hashlib.sha256(original).hexdigest(), original_unchanged=True,
                  original_sha256_by_source={path: hashlib.sha256(data).hexdigest()
                                             for path, data in originals.items()},
                  results=results)
    (ROOT / 'evidence/verdict-line-mutations.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    for row in results:
        print(row['name'], row['result'], row['pytest_summary'])
    return 0 if all(row['passed'] for row in results) else 1

if __name__ == '__main__':
    sys.exit(main())
