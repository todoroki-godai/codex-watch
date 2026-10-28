"""Sequential mutations in a disposable copy; never alter the working implementation."""
import difflib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
NOTES = ROOT / '_work/notes'
mutations = [
    ('01-delete-recovery-reset', 'bin/codex-watch', '  else\n    capacity_reported=0\n  fi', '  else\n    :\n  fi', 'rechecks_capacity', '①要素削除: 回復時の状態解除'),
    ('02-disable-body-boundary', 'bin/_codex_common.sh', '      if (body) next', '      if (0) next', 'role_section_error_quote', '④無効化: role区間を無視'),
    ('03-hook-meaning-reversal', 'bin/_codex_common.sh', 'if ($0 ~ /^hook: /) { body=0;', 'if ($0 ~ /^hook: /) { body=1;', 'terminal_capacity', '②意味破壊: CLI区間を本文と誤認'),
    ('04-always-negative-detector', 'bin/_codex_common.sh', 'END { exit !(result || pending) }', 'END { exit 1 }', 'capacity_without_tokens', '④判定を常に陰性にする'),
    ('05-remove-negation', 'bin/_codex_common.sh', 'if (text ~ /(not|no[[:space:]]+longer)[[:space:]]+(at[[:space:]]+capacity|overloaded)/) return 0', 'if (0) return 0', 'normal_or_noncapacity', '独自変異A: 否定文の意味を失う'),
    ('06-break-wrapped-block', 'bin/_codex_common.sh', 'block != "" && line ~ /^[[:space:]]+/', 'block != "" && 0', 'terminal_capacity', '独自変異B: 複数行への分散を読まない'),
    ('07-swap-summary-state', 'bin/_codex_common.sh', 'result=pending; pending=0;', 'pending=result; result=0;', 'terminal_capacity', '③入替: tokens usedで候補を消失'),
]
results = []
with tempfile.TemporaryDirectory(prefix='mutation-', dir=ROOT / '_work') as folder:
    sandbox = Path(folder)
    for name in ['bin', 'lib']:
        shutil.copytree(ROOT / name, sandbox / name, ignore=shutil.ignore_patterns('__pycache__'))
    (sandbox / 'tests').mkdir()
    shutil.copy2(ROOT / 'tests/test_codex_capacity.py', sandbox / 'tests/test_codex_capacity.py')
    originals = {file: (sandbox / file).read_text() for _, file, *_ in mutations}
    for name, file, before, after, selection, kind in mutations:
        target = sandbox / file
        original = originals[file]
        assert original.count(before) == 1, (name, original.count(before))
        modified = original.replace(before, after)
        target.write_text(modified)
        assert target.read_text() != original
        (NOTES / f'{name}.diff').write_text(''.join(difflib.unified_diff(original.splitlines(True), modified.splitlines(True), fromfile=file, tofile=file)))
        command = ['python3', '-m', 'pytest', '-q', str(sandbox / 'tests/test_codex_capacity.py'), '-k', selection]
        try:
            run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
            (NOTES / f'{name}.txt').write_text(run.stdout + run.stderr)
            results.append(dict(name=name, kind=kind, file=file, line=original[:original.index(before)].count('\n')+1,
                                command=command, returncode=run.returncode, summary=run.stdout.strip().splitlines()[-1]))
        finally:
            target.write_text(original)
            assert target.read_text() == original
    # Meaning-preserving positive control on the exact same copied entry points.
    target = sandbox / 'bin/_codex_common.sh'
    target.write_text('# semantic-preserving positive control\n' + originals['bin/_codex_common.sh'])
    command = ['python3', '-m', 'pytest', '-q', str(sandbox / 'tests/test_codex_capacity.py')]
    run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
    (NOTES / 'positive-control.txt').write_text(run.stdout + run.stderr)
    results.append(dict(name='positive-control', command=command, returncode=run.returncode, summary=run.stdout.strip().splitlines()[-1]))
(NOTES / 'mutation-results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')
for result in results:
    print(result['name'], result['returncode'], result['summary'])
assert all(r['returncode'] == 1 for r in results[:-1]), 'surviving mutation or execution error: not complete'
assert results[-1]['returncode'] == 0
