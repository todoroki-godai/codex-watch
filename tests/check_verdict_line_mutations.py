"""Mutate isolated checkout copies; require every defective variant to turn red."""
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

def main():
    original = (ROOT / SOURCE).read_bytes()
    results = []
    for name, old, new, selector, expect_red in CASES:
        folder = OUT / name
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True)
        for sub in ('bin', 'lib', 'templates', 'tests'):
            shutil.copytree(ROOT / sub, folder / sub, ignore=shutil.ignore_patterns('__pycache__'))
        path = folder / SOURCE
        text = path.read_text()
        assert text.count(old) == 1, name
        mutated = text.replace(old, new)
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
        results.append(dict(name=name, old=old, new=new, returncode=run.returncode,
                            result='red' if red else 'green' if run.returncode == 0 else 'error',
                            expected='red' if expect_red else 'green', passed=passed,
                            source_sha256=hashlib.sha256(mutated.encode()).hexdigest(),
                            pytest_summary=output.strip().splitlines()[-1]))
    assert (ROOT / SOURCE).read_bytes() == original
    result = dict(original_sha256=hashlib.sha256(original).hexdigest(), original_unchanged=True,
                  results=results)
    (ROOT / 'evidence/verdict-line-mutations.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    for row in results:
        print(row['name'], row['result'], row['pytest_summary'])
    return 0 if all(row['passed'] for row in results) else 1

if __name__ == '__main__':
    sys.exit(main())
