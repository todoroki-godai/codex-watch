"""Exercise codex-impl with fake Chromium, CDP, AWS, and Codex commands."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import subprocess
import time

import pytest

from test_codex_impl_aws import executable

ROOT = Path(os.environ.get('CODEX_BROWSER_TEST_ROOT', Path(__file__).resolve().parents[1]))
TEMPLATE = Path(__file__).resolve().parents[1] / 'templates/browser-cdp.md'
SOURCE = '直しの出所: なし\n'
BROWSER = r'''
import json, os, sys, time
from pathlib import Path

argv = sys.argv[1:]
profile = Path(next(arg.partition('=')[2] for arg in argv if arg.startswith('--user-data-dir=')))
port = os.environ['TEST_PORT']
root = Path(os.environ['TEST_ROOT'])
(root / f'browser-{port}').write_text(json.dumps([sys.argv[0], *argv]))
mode = os.environ['TEST_BROWSER_MODE']
if mode == 'exit':
    sys.exit(9)
if mode == 'no-marker':
    time.sleep(12)
    sys.exit(0)
path = f'/devtools/browser/{port}'
url = f'ws://127.0.0.1:{port}{path}'
if mode == 'mismatch':
    url += '-foreign'
(root / f'cdp-{port}').write_text(json.dumps({'webSocketDebuggerUrl': url}))
marker = profile / 'DevToolsActivePort'
if mode == 'partial':
    marker.write_text(port + '\n')
    time.sleep(0.25)
    with marker.open('a') as stream:
        stream.write(path + '\n')
else:
    marker.write_text(f'{port}\n{path}\n')
if mode == 'live':
    time.sleep(3)
'''


@pytest.fixture
def launch(tmp_path):
    fake, work, home, state = (tmp_path / name for name in ('bin', 'work tree', 'home', 'state'))
    for folder in (fake, work, home, state):
        folder.mkdir()
    chromium = tmp_path / 'chrome headless shell'
    executable(chromium, BROWSER)
    executable(fake / 'git', """import sys
if '--absolute-git-dir' in sys.argv: print('/repo/.git/worktrees/test')
elif '--git-common-dir' in sys.argv: print('/repo/.git')
else: sys.exit(1)
""")
    executable(fake / 'aws', 'raise SystemExit(1)\n')
    executable(fake / 'gh', 'raise SystemExit(99)\n')
    executable(fake / 'timeout', r'''
import json, os, sys
from pathlib import Path
Path(os.environ['TEST_ROOT'], 'timeout-' + os.environ['TEST_PORT']).write_text(json.dumps(sys.argv[1:]))
os.execv(sys.argv[4], sys.argv[4:])
''')
    executable(fake / 'curl', r'''
import os, sys
from pathlib import Path
import urllib.parse
argv = sys.argv[1:]
url = urllib.parse.urlsplit(argv[-1])
assert url.scheme == 'http' and url.hostname == '127.0.0.1' and url.path == '/json/version'
assert argv[argv.index('--noproxy') + 1] == '*'
assert 0 < float(argv[argv.index('--max-time') + 1]) <= 10
root = Path(os.environ['TEST_ROOT'])
with (root / ('queries-' + os.environ['TEST_PORT'])).open('a') as stream:
    stream.write(str(url.port) + '\n')
answer = root / f'cdp-{url.port}'
if not answer.exists(): sys.exit(7)
print(answer.read_text())
''')
    executable(fake / 'codex', r'''
import os, sys
from pathlib import Path
root = Path(os.environ['TEST_ROOT'])
port = os.environ['TEST_PORT']
(root / f'launch-{port}').touch()
(root / f'prompt-{port}.tmp').write_bytes(sys.stdin.buffer.read())
(root / f'prompt-{port}.tmp').rename(root / f'prompt-{port}')
''')

    def run(tail, *, port=41321, mode='ok', override=chromium, opt_out='0'):
        prompt = tmp_path / f'input {port}.md'
        original = (SOURCE + tail).encode('utf-8')
        prompt.write_bytes(original)
        env = {k: v for k, v in os.environ.items() if not k.startswith(('AWS_', 'CODEX_', 'GH_', 'GITHUB_'))}
        if 'CODEX_BROWSER_TRACE' in os.environ:
            env['CODEX_BROWSER_TRACE'] = os.environ['CODEX_BROWSER_TRACE']
        env.update(PATH=f'{fake}:{os.environ["PATH"]}', HOME=str(home),
                   CODEX_WATCH_DIR=str(state), CODEX_SUMMARY='#0', CODEX_SKILLS_FILTER='off',
                   CODEX_IMPL_ALLOW_MISSING_NODE_MODULES='1', CODEX_IMPL_MODEL='gpt-6.2-sol', CODEX_IMPL_NO_BROWSER=opt_out,
                   TEST_ROOT=str(tmp_path), TEST_PORT=str(port), TEST_BROWSER_MODE=mode)
        if override is not None:
            env['CODEX_IMPL_CHROMIUM'] = str(override)
        result = subprocess.run([str(ROOT / 'bin/codex-impl'), str(work), str(prompt), 'browser test'],
                                env=env, capture_output=True, text=True, timeout=15)
        assert prompt.read_bytes() == original
        return result, original

    return run, work, home, state


def launched_prompt(tmp_path, port):
    capture = tmp_path / f'prompt-{port}'
    deadline = time.monotonic() + 5
    while not capture.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert capture.exists(), 'Codex stub did not receive the prompt'
    note, _, body = capture.read_bytes().partition(b'\n')
    assert note.decode().startswith('手元で回す試験は')
    return body


def assert_browser_launch(launch, tmp_path, result, original, port):
    _, work, _, state = launch
    assert result.returncode == 0, result.stderr
    run_id = result.stdout.strip()
    profile = work / '_work/codex-browser' / run_id
    fields = dict(line.split('=', 1) for line in (state / f'{run_id}.state').read_text().splitlines())
    assert fields['browser_port'] == str(port)
    assert fields['prompt'] == str(tmp_path / f'input {port}.md')
    argv = json.loads((tmp_path / f'browser-{port}').read_text())
    assert argv[1:] == [
        '--remote-debugging-port=0', '--remote-debugging-address=127.0.0.1',
        f'--user-data-dir={profile}', '--no-first-run', 'about:blank',
    ]
    timeout_args = tmp_path / f'timeout-{port}'
    assert timeout_args.exists(), 'Chromium did not run under timeout'
    assert json.loads(timeout_args.read_text()) == ['-k', '10', '5400', *argv]
    assert (profile / 'DevToolsActivePort').read_text().splitlines() == [
        str(port), f'/devtools/browser/{port}',
    ]
    assert set((tmp_path / f'queries-{port}').read_text().splitlines()) == {str(port)}
    block = TEMPLATE.read_text().split('## 依頼文に貼る定型\n\n```\n', 1)[1].split('\n- （ログイン', 1)[0]
    expected = block.replace('<ポート>', str(port)).replace('<許す URL の一覧>', 'この依頼文に書かれた URL だけ')
    assert launched_prompt(tmp_path, port) == original + b'\n\n' + expected.encode() + b'\n'
    return argv[0]


@pytest.mark.parametrize('word', [
    'PlAyWrIgHt', 'CHROMIUM', 'connectOverCDP', 'STYLE-DIFF', 'RUN.SH DEV', 'run.sh stg',
    'HTTPS://DEV.example.com', 'https://stg.example.com', '見本照合', '撮影', 'スクリーンショット', 'Screenshot',
])
def test_trigger(launch, tmp_path, word):
    run, *_ = launch
    result, original = run(f'指示\r\n\r\n{word}')
    assert_browser_launch(launch, tmp_path, result, original, 41321)


@pytest.mark.parametrize('body,opt_out', [
    pytest.param('テストを確認', '0', id='no-word'),
    ('127.0.0.1:41000 の説明', '0'),
    ('CONNECTOVERCDP http://127.0.0.1:41000\n撮影', '0'),
    ('connectOverCDP\n実行ファイルも不要', '1'),
    ('https://example.com/runXsh dev と https://devXexample.com', '0'),
])
def test_skip(launch, tmp_path, body, opt_out):
    run, work, _, state = launch
    result, original = run(body, opt_out=opt_out, override=tmp_path / 'absent')
    assert result.returncode == 0, result.stderr
    assert launched_prompt(tmp_path, 41321) == original
    assert 'browser_port=' not in (state / f'{result.stdout.strip()}.state').read_text()
    assert not (work / '_work').exists()
    assert not list(tmp_path.glob('browser-*'))


def test_manual_requires_numeric_port(launch, tmp_path):
    run, *_ = launch
    result, original = run('connectOverCDP http://127.0.0.1:<ポート>', mode='partial')
    assert_browser_launch(launch, tmp_path, result, original, 41321)


def test_highest_numeric_revision(launch, tmp_path):
    run, _, home, _ = launch
    cache = home / 'Library/Caches/ms-playwright'
    for revision in ('999', '1000', '1001x'):
        binary = cache / f'chromium_headless_shell-{revision}/chrome-headless-shell-mac-arm64/chrome-headless-shell'
        binary.parent.mkdir(parents=True)
        executable(binary, BROWSER)
    result, original = run('撮影', override=None)
    actual = assert_browser_launch(launch, tmp_path, result, original, 41321)
    assert 'chromium_headless_shell-1000/' in actual


@pytest.mark.parametrize('mode', ['missing', 'exit', 'mismatch'])
def test_browser_failure(launch, tmp_path, mode):
    run, _, _, state = launch
    if mode == 'missing':
        result, _ = run('screenshot', override=tmp_path / 'absent')
    else:
        result, _ = run('screenshot', mode=mode)
    assert result.returncode != 0, result.stderr
    assert 'Chromium' in result.stderr
    assert not list(state.glob('*.state'))
    assert not (tmp_path / 'launch-41321').exists()


def test_ready_deadline(launch, tmp_path):
    run, _, _, state = launch
    result, _ = run('screenshot', mode='no-marker')
    assert result.returncode != 0
    assert 'Chromium の準備が10秒以内に完了しませんでした' in result.stderr
    assert (tmp_path / 'browser-41321').exists()
    assert not (tmp_path / 'launch-41321').exists()
    assert not list(state.glob('*.state'))


@pytest.mark.parametrize('second_mode', ['ok', 'exit'])
def test_concurrent(launch, tmp_path, second_mode):
    run, _, _, state = launch
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run, '撮影する', port=41321, mode='live')
        second = pool.submit(run, '撮影する', port=41322, mode=second_mode)
        result1, original1 = first.result()
        result2, original2 = second.result()
    assert_browser_launch(launch, tmp_path, result1, original1, 41321)
    if second_mode == 'ok':
        assert_browser_launch(launch, tmp_path, result2, original2, 41322)
    else:
        assert result2.returncode != 0, result2.stderr
        assert not (tmp_path / 'launch-41322').exists()
        assert len(list(state.glob('*.state'))) == 1
    assert result1.stdout != result2.stdout


def test_launcher_has_no_kill_command():
    source = (ROOT / 'bin/codex-impl').read_text()
    assert not re.search(r'\b(?:kill|pkill|killall)\b', source)
