"""Issue names: unmodified launchers, offline children, real IDs/files/PIDs."""
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

import pytest

from test_codex_model_effort import fake_bin, VALID_GOAL_CUT
from test_codex_summary import read_state_file

ROOT = Path(__file__).resolve().parents[1]
INVALID = os.fsdecode(b'\xe4\xbc#5 description')


def clean_env():
    return {k: v for k, v in os.environ.items()
            if not k.startswith(('CODEX_', 'REVIEW_', 'GH_', 'GITHUB_', 'AWS_'))}


def shell_run(command, args, env):
    # Mutation runs alone opt into shell execution traces (no real credentials).
    flags = ['-x'] if 'RUN_NAME_TRACE' in env else []
    result = subprocess.run(['bash', *flags, '-c', command, 'run-name-test', *args],
                            env=env, capture_output=True, text=True, errors="backslashreplace", timeout=30)
    if 'RUN_NAME_TRACE' in env:
        with open(env['RUN_NAME_TRACE'], 'a') as output:
            output.write(result.stderr)
    return result


@pytest.mark.parametrize('summary,label,expected', [
    ('#1987 修正', 'tally', '1987-tally'),
    ('#1987', '1987-tally', '1987-tally'),
    ('#1987', 'x-1987-y', 'x-1987-y'),
    ('#1987', 'x1987y', 'x1987y'),
    ('#1987', '11987-tally', '1987-11987-tally'),
    ('#1987', '19870-tally', '1987-19870-tally'),
    ('#1987', '調査.再確認_版', '1987-調査.再確認_版'),
    ('#0', 'work', '0-work'),
    ('#0', '0-work', '0-work'),
    ('#0', '10-work', '0-10-work'),
    ('#1987', ' a*[x]$;引用 ', '1987- a*[x]$;引用 '),
    ('#1987', '', '1987-'),
    ('説明\n#1987 続き', 'work', '1987-work'),
    ('\u3000  #1987  ', 'work', '1987-work'),
    ('あ' * 58 + '#7', 'work', '7-work'),
    ('あ' * 59 + '#7', 'work', '0-work'),
    ('あ' * 56 + '#1234', 'work', '0-work'),
    ('#7 ' + 'あ' * 53 + '#1234', 'work', '7-work'),
    ('#1987 #53', 'work', '1987-work'),
    ('#1987 #53', '53-work', '1987-53-work'),
    ('#0012', 'work', '0012-work'),
    (None, 'work', '0-work'),
    ('#abc', 'work', '0-work'),
    (INVALID, 'work', '0-work'),
])
def test_label_issue(summary, label, expected):
    env = clean_env()
    if summary is not None:
        env['CODEX_SUMMARY'] = summary
    result = shell_run('source "$1"; codex_label_with_issue "$2"',
                       [str(ROOT / 'bin/_codex_common.sh'), label], env)
    assert result.returncode == 0, result.stderr
    assert result.stdout == expected + '\n'


@pytest.fixture(params=['codex-impl', 'codex-review'])
def real_launch(request, tmp_path, fake_bin):
    # Byte-for-byte copies, including the original RUN_ID calculation.
    for directory in ('bin', 'lib', 'templates'):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    workdir = tmp_path / 'workdir'
    workdir.mkdir()
    home = tmp_path / 'home'
    home.mkdir()
    prompt = tmp_path / 'prompt'
    prompt.write_text('直しの出所: なし\n点検:\n- 突き合わせ: 確認済\n'
                      '- 出所の付記: 確認済\n- 直し残しの検索: 確認済\n')
    (tmp_path / 'gh-body').write_text('')
    # Stub -o as a real report and optionally keep the child alive until teardown.
    codex = fake_bin / 'codex'
    codex.write_text('''#!/bin/sh
if [ "$1" = --version ]; then echo 'codex-cli 0.171.0'; exit 0; fi
while [ "$#" -gt 0 ]; do
  if [ "$1" = -o ]; then shift; report="$1"; fi
  shift
done
cat >/dev/null
if [ -n "${RUN_NAME_TRACE:-}" ]; then
  printf 'STUB_REPORT:%s\\n' "$report" >> "$RUN_NAME_TRACE"
fi
printf 'offline report\\n' > "$report"
printf 'offline log\\n'
if [ -n "${FAKE_HOLD_FILE:-}" ]; then
  while [ ! -e "$FAKE_HOLD_FILE" ]; do sleep 0.05; done
fi
''')
    codex.chmod(0o755)
    env = clean_env()
    # Keep nested temporary workdirs from inheriting this checkout's declarations.
    subprocess.run(['git', 'init', '-q', str(workdir)], check=True, capture_output=True)
    env.update(PATH=f'{fake_bin}:{os.environ["PATH"]}', HOME=str(home),
               CODEX_SKILLS_FILTER='off', CODEX_WATCH_DIR=str(tmp_path / 'state'), CODEX_IMPL_ALLOW_MAIN='1',
               CODEX_IMPL_ALLOW_MISSING_NODE_MODULES='1', CODEX_IMPL_MODEL='gpt-6.2-sol', CODEX_REVIEW_KIND_LABEL='コード', CODEX_REVIEW_MODEL='gpt-6.2-sol',
               CODEX_REVIEW_ADAPTER=str(tmp_path / 'missing-adapter'),
               REVIEW_TARGET='issue:example-org/example-repo#1', REVIEW_GOAL_CUT=VALID_GOAL_CUT,
               FAKE_GH_BODY=str(tmp_path / 'gh-body'))
    children = []

    def launch(summary, label, hold=False):
        run_env = dict(env, CODEX_SUMMARY=summary)
        if hold:
            run_env['FAKE_HOLD_FILE'] = str(tmp_path / 'release')
        result = shell_run('exec bash ' + ('-x ' if 'RUN_NAME_TRACE' in env else '')
                           + '"$1" "$2" "$3" "$4"',
                           [str(tmp_path / 'bin' / request.param), str(workdir), str(prompt), label], run_env)
        assert result.returncode == 0, result.stdout + result.stderr
        run_id = result.stdout.strip()
        state_path = tmp_path / 'state' / (run_id + '.state')
        state = read_state_file(state_path)
        children.append(int(state['pid']))
        assert state['run_id'] == run_id
        for key, suffix in [('log', '.log'), ('report', '.report')]:
            path = Path(state[key])
            assert path == state_path.with_name(run_id + suffix)
            deadline = time.monotonic() + 3
            while (not path.exists() or not path.stat().st_size) and time.monotonic() < deadline:
                time.sleep(.02)
            assert path.is_file() and path.stat().st_size, str(path)
        return run_id, state, state_path

    yield launch
    (tmp_path / 'release').touch()
    for pid in children:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


@pytest.mark.parametrize('summary,label,prefix', [
    ('#1987 実装', 'tally', '1987-tally'),
    ('#1987', '1987-tally', '1987-tally'),
    ('#1987', '11987-tally', '1987-11987-tally'),
    ('#1987', '調査.再確認_版', '1987-調査.再確認_版'),
    ('#0', 'work', '0-work'),
    (INVALID, 'work', '0-work'),
])
def test_real_run_identity(real_launch, summary, label, prefix):
    run_id, _, _ = real_launch(summary, label)
    assert re.fullmatch(re.escape(prefix) + r'-[0-9]{8}-[0-9]{6}-[0-9]+', run_id), run_id


def test_existing_live_run_preserved(real_launch):
    old_id, old_state, old_path = real_launch('#53', 'existing', hold=True)
    pid = int(old_state['pid'])
    os.kill(pid, 0)
    paths = [old_path, Path(old_state['log']), Path(old_state['report'])]
    before = {path: (path.stat().st_ino, path.read_bytes()) for path in paths}
    new_id, _, _ = real_launch('#1987', 'new')
    assert old_id != new_id
    os.kill(pid, 0)
    for path, snapshot in before.items():
        assert path.exists(), str(path)
        assert (path.stat().st_ino, path.read_bytes()) == snapshot
