#!/usr/bin/env python3
"""Apply fault mutations only on a committed clean tree; restore after every run."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.tmp/docs-ro-fix2-mutations'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT).decode().strip()


def main():
    assert os.geteuid() != 0, 'permission tests require non-root'
    assert not git('status', '--porcelain'), 'commit first'
    base = git('rev-parse', 'HEAD')
    OUT.mkdir(parents=True, exist_ok=True)
    common = 'bin/_codex_common.sh'
    config = 'templates/codex-dev.aws-config'
    old = '  if ! CODEX_AWS_ACCOUNT="$(python3 - "$declaration"'
    # The marker executes only when the old guard takes its unsafe early return.
    guard = ('  [[ -e "$declaration" || -L "$declaration" ]] || { '
             'printf "legacy-return\\n" >> "$CODEX_MUTATION_TRACE/hit"; return 0; }\n')
    process = next(line for line in git('show', '7c18da15:templates/codex-dev.aws-config').splitlines()
                   if line.startswith('credential_process'))
    process = process.replace("-c '", "-c 'printf \"template-process\\n\" >> \"$CODEX_MUTATION_TRACE/hit\"; ", 1)
    suffix = '\nexcept (OSError, UnicodeError):\n    sys.exit(1)\nif account'
    cases = [
        ('old-guard-permissions', common, old, guard + old, 'unsearchable_declaration_parent_rejected', 'legacy-return'),
        ('old-guard-nondirectory', common, old, guard + old, 'nondirectory_declaration_parent_rejected', 'legacy-return'),
        ('old-guard-symlink-cycle', common, old, guard + old, 'symlink_cycle_declaration_rejected', 'legacy-return'),
        ('normalize-nul', common, '    account = pathlib.Path(sys.argv[1]).read_text().strip()' + suffix,
         "    account = pathlib.Path(sys.argv[1]).read_text().replace('\\x00', '').strip(); pathlib.Path(os.environ['CODEX_MUTATION_TRACE'], 'hit').write_text('nul-normalization')" + suffix,
         'nul_declaration_rejected', 'nul-normalization'),
        ('restore-dev-process', config, '[profile codex-dev]\nregion = ap-northeast-1\n',
         '[profile codex-dev]\nregion = ap-northeast-1\n' + process + '\n',
         'dev_template_matches_baseline or (real_export_credentials and flag and False)', 'template-process'),
    ]
    results = []
    for name, filename, old, new, select, marker in cases:
        assert not git('status', '--porcelain'), 'dirty before mutation'
        target = ROOT / filename
        original = target.read_bytes()
        source = original.decode()
        assert source.count(old) == 1, name
        mutated = source.replace(old, new)
        diff = ''.join(difflib.unified_diff(source.splitlines(True), mutated.splitlines(True),
                                            fromfile=filename, tofile=filename))
        assert diff and source != mutated
        folder = OUT / name
        folder.mkdir(exist_ok=True)
        hit = folder / 'hit'
        hit.unlink(missing_ok=True)
        (folder / 'mutation.diff').write_text(diff)
        command = [sys.executable, '-m', 'pytest', 'tests/test_codex_impl_aws.py',
                   '-q', '--tb=short', '-k', select]
        try:
            target.write_text(mutated)
            assert git('diff', '--', filename), 'fault diff not applied'
            env = dict(os.environ, CODEX_MUTATION_TRACE=str(folder))
            run = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                 text=True, timeout=60)
            log = run.stdout + run.stderr
            (folder / 'pytest.log').write_text(log)
            reached = hit.exists() and marker in hit.read_text()
            record = dict(name=name, baseline=base, file=filename,
                          diff_sha256=hashlib.sha256(diff.encode()).hexdigest(),
                          command=command, exit=run.returncode,
                          summary=run.stdout.strip().splitlines()[-1],
                          fault_diff_applied=True, branch_reached=reached)
            record['killed'] = (run.returncode == 1 and reached and
                                ('AssertionError' in log or 'E   assert' in log) and
                                'ERROR ' not in log)
        finally:
            target.write_bytes(original)
            assert target.read_bytes() == original
            assert not git('status', '--porcelain'), 'dirty after restoration'
        record['restored_clean'] = True
        results.append(record)
        (OUT / 'results.json').write_text(json.dumps(results, indent=2))
        print(json.dumps(record), flush=True)
    assert git('rev-parse', 'HEAD') == base
    assert all(r['killed'] for r in results), 'surviving or unobserved mutation'
    print(f'{len(results)}/{len(results)} mutations killed; branches reached; worktree clean')


if __name__ == '__main__':
    main()
