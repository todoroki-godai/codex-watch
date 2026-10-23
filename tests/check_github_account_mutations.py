#!/usr/bin/env python3
"""Mutation checks in isolated source copies; fake HOME prevents real shared writes.

python3 tests/check_github_account_mutations.py
No git or real Codex is invoked. Never enable CODEX_TEST_REAL_GH here.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.test-round1-mutations'
OUT.mkdir(exist_ok=True)
common = (ROOT/'bin/_codex_common.sh').read_text()
set_line = next(line for line in common.splitlines() if line.startswith('  CODEX_GITHUB_ARGS=(-c '))
cases = [
    ('a-per-run-directory', 'test_review_records_after_codex_exit',
     [('  CODEX_GITHUB_CONFIG_DIR="$STATE_DIR/gh-account/$CODEX_GITHUB_ACCOUNT"',
       '  CODEX_GITHUB_CONFIG_DIR="$(mktemp -d "$STATE_DIR/gh-account.XXXXXX")"')]),
    ('b-empty-state', 'test_undeclared_preserves_launch',
     [('[[ -n "$CODEX_GITHUB_ACCOUNT" ]] && printf', 'printf')]),
    ('c-undeclared-gh', 'test_undeclared_never_calls_gh',
     [('[[ -e "$declaration" || -L "$declaration" ]] || return 0',
       '[[ -e "$declaration" || -L "$declaration" ]] || { gh api --hostname github.com user --jq .login >/dev/null 2>&1 || :; return 0; }')]),
    ('d-stale-config', 'test_repeated_account_replaces_files',
     [('    fd, temporary = tempfile.mkstemp',
       '    if name == "config.yml" and (pathlib.Path(folder) / name).exists():\n        continue\n    fd, temporary = tempfile.mkstemp')]),
    ('e-nonatomic-overwrite', 'test_repeated_account_replaces_files',
     [('        os.replace(temporary, pathlib.Path(folder) / name)',
       '        (pathlib.Path(folder) / name).write_bytes(data)')]),
    ('old-a-child-env', 'test_pinned_child_and_persistence',
     [('export GH_CONFIG_DIR="$CODEX_GITHUB_CONFIG_DIR"', 'GH_CONFIG_DIR="$CODEX_GITHUB_CONFIG_DIR"')]),
    ('old-b-no-match', 'test_invalid_or_missing_account_stops or test_failed_preflight_stops_and_redacts',
     [('if [[ "$actual" != "$CODEX_GITHUB_ACCOUNT" ]]; then', 'if false; then')]),
    ('old-c-require-declaration', 'test_undeclared_preserves_launch',
     [('[[ -e "$declaration" || -L "$declaration" ]] || return 0', '[[ -e "$declaration" || -L "$declaration" ]] || return 5')]),
    ('old-d-write-shared-hosts', 'test_pinned_child_and_persistence',
     [('os.replace(temporary, pathlib.Path(folder) / name)',
       'os.replace(temporary, pathlib.Path(os.environ["HOME"]) / ".config/gh/hosts.yml" if name == "hosts.yml" else pathlib.Path(folder) / name)')]),
    ('old-e-first-line-only', 'test_invalid_or_missing_account_stops',
     [('read_text().strip()', 'read_text().splitlines()[0].strip()')]),
    ('old-f-drop-shell-policy', 'test_pinned_child_and_persistence',
     [(set_line, '  CODEX_GITHUB_ARGS=()')]),
    ('positive-equivalent-comparison', 'test_pinned_child_and_persistence or test_invalid_or_missing_account_stops',
     [('if [[ "$actual" != "$CODEX_GITHUB_ACCOUNT" ]]; then', 'if ! [[ "$actual" == "$CODEX_GITHUB_ACCOUNT" ]]; then')]),
]
results = []
for name, select, replacements in cases:
    folder = OUT / name
    if folder.exists(): shutil.rmtree(folder)
    folder.mkdir()
    for d in ('bin','lib'):
        shutil.copytree(ROOT/d,folder/d,ignore=shutil.ignore_patterns('__pycache__'))
    changed = common
    for old,new in replacements:
        assert changed.count(old) == 1, (name, old, changed.count(old))
        changed = changed.replace(old,new)
    (folder/'bin/_codex_common.sh').write_text(changed)
    env=dict(os.environ, CODEX_ACCOUNT_TEST_ROOT=str(folder), PYTHONDONTWRITEBYTECODE='1')
    env.pop('CODEX_TEST_REAL_GH', None)
    command=[sys.executable,'-m','pytest',str(ROOT/'tests/test_codex_github_account.py'),'-q','--tb=short',
             '-k', select, '--basetemp', str(folder/'tmp')]
    r=subprocess.run(command,env=env,capture_output=True,text=True,timeout=180)
    (folder/'pytest.log').write_text(r.stdout+r.stderr)
    (folder/'bin/_codex_common.sh').write_text(common)
    assert (folder/'bin/_codex_common.sh').read_text() == common
    expected_green = name.startswith('positive-')
    ok = (r.returncode == 0) if expected_green else (r.returncode == 1)
    evidence=[line for line in r.stdout.splitlines() if line.startswith(('FAILED ','ERROR '))]
    summary=next((line for line in reversed(r.stdout.splitlines()) if 'passed' in line or 'failed' in line or 'error' in line),'no summary')
    result=dict(mutation=name,exit=r.returncode,expected='green' if expected_green else 'red',ok=ok,summary=summary,evidence=evidence,
                replacements=replacements, restored=True, restored_sha256=hashlib.sha256(common.encode()).hexdigest())
    results.append(result)
    print(json.dumps(result,ensure_ascii=False),flush=True)
    (OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    if not ok: sys.exit(1)
