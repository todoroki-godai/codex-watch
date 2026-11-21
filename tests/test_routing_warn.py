"""D observation: real CLI, fake sender/GitHub, temporary state only."""
import concurrent.futures
import datetime
import importlib.util
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import time

import pytest
from test_codex_review_cli import fake_bin, VALID_GOAL_CUT

ROOT = Path(os.environ.get('ROUTING_WARN_TEST_ROOT', Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / 'lib'))
spec = importlib.util.spec_from_file_location('routing_warn', ROOT / 'lib/routing_warn.py')
rw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rw)
PASS = dict(stages={s: True for s in ('A', '1', '2', '3', 'B')}, stopped_at=None, reasons=[])


def blocked(stage='A'):
    stages = list(PASS['stages'])
    return dict(stages={s: True if i < stages.index(stage) else False if s == stage else 'not_evaluated'
                        for i, s in enumerate(stages)}, stopped_at=stage,
                reasons=['series/predecessor record missing\nSYNTHETIC_SECRET'])


def adapter(tmp_path, data=PASS, code=0, body=None):
    p = tmp_path / 'adapter 空白.py'
    p.write_text(body if body is not None else f'import sys\nprint({json.dumps(data)!r})\nprint("SYNTHETIC_SECRET", file=sys.stderr)\nsys.exit({code})\n')
    return p


def dispatch(tmp_path, fake_bin, monkeypatch, adapter_path, *, kind='コード', timeout=40):
    work = tmp_path / 'work'
    work.mkdir(exist_ok=True)
    state = tmp_path / 'state'
    state.mkdir(exist_ok=True)
    prompt = tmp_path / 'prompt.txt'
    prompt.write_text('本文 SYNTHETIC_PROMPT\n点検:\n- 突き合わせ: 済\n- 出所の付記: 済\n- 直し残しの検索: 済\n')
    env = dict(os.environ, PATH=f'{fake_bin}:{os.environ["PATH"]}', CODEX_WATCH_DIR=str(state),
               CODEX_REVIEW_KIND_LABEL=kind, CODEX_SUMMARY='#0', CODEX_REVIEW_MODEL='gpt-6.2-sol', CODEX_REVIEW_ADAPTER=str(adapter_path),
               REVIEW_TARGET='issue:example-org/example-repo#1', REVIEW_GOAL_CUT=VALID_GOAL_CUT,
               FAKE_GH_BODY=str(tmp_path / 'body.txt'), ARGV_CAPTURE_FILE=str(tmp_path / 'sent.txt'))
    for name in ('CODEX_REVIEW_GATE_CHECK', 'CODEX_REVIEW_NO_GATE'):
        env.pop(name, None)
    before = datetime.datetime.now(datetime.timezone.utc)
    result = subprocess.run([str(ROOT / 'bin/codex-review'), str(work), str(prompt), 'routing-test'],
                            env=env, capture_output=True, text=True, timeout=timeout)
    return result, state, before


def check_dispatch(result, state, before, verdict, stage=None, prior=0):
    assert result.returncode == 0, result.stdout + result.stderr
    run = result.stdout.strip().splitlines()[-1]
    assert (state / f'{run}.state').is_file()
    sent = state.parent / 'sent.txt'
    deadline = time.monotonic() + 2
    while not sent.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert sent.exists(), 'fake sender was not invoked'
    lines = (state / 'routing-warn.jsonl').read_text().splitlines()
    assert len(lines) == prior + 1
    entry = json.loads(lines[-1])
    assert set(entry) == {'dispatch_id', 'target', 'kind', 'time', 'verdict', 'stopped_at', 'reasons'}
    assert entry['dispatch_id'] == run
    assert entry['target'] == 'issue:example-org/example-repo#1'
    assert entry['kind'] in ('コード', '設計')
    assert entry['verdict'] == verdict
    if verdict == 'pass':
        assert entry['reasons'][0] == '全段通過'
    elif verdict == 'error':
        assert entry['reasons'][0] == '処理失敗'
    assert entry['stopped_at'] == stage
    assert (entry['stopped_at'] is not None) == (entry['verdict'] == 'would_block')
    assert before <= datetime.datetime.fromisoformat(entry['time']) <= datetime.datetime.now(datetime.timezone.utc)
    warnings = [s for s in result.stderr.splitlines() if s.startswith('routing警告:')]
    assert len(warnings) == 1
    assert {'timeout': '時間切れ', 'missing': '部品なし'}.get(verdict, 'routing警告:') in warnings[0]
    assert 'SYNTHETIC_SECRET' not in result.stderr + '\n'.join(lines)
    assert 'SYNTHETIC_PROMPT' not in result.stderr + '\n'.join(lines)
    return entry


@pytest.mark.parametrize('mode', ['pass', 'blockA', 'block1', 'block2', 'block3', 'blockB',
                                  'error', 'error-pass', 'invalid', 'invalid-null', 'missing'])
def test_dispatch_outcomes(tmp_path, fake_bin, monkeypatch, mode):
    if mode.startswith('block'):
        p, expected, stage = adapter(tmp_path, blocked(mode[-1]), 1), 'would_block', mode[-1]
    else:
        stage = None
        expected = {'pass': 'pass', 'error': 'error', 'error-pass': 'error',
                    'invalid': 'invalid', 'invalid-null': 'invalid', 'missing': 'missing'}[mode]
        p = adapter(tmp_path, code=7 if mode.startswith('error') else 0,
                    body={'error': 'raise RuntimeError("SYNTHETIC_SECRET")',
                          'invalid': 'print("not JSON SYNTHETIC_SECRET")',
                          'invalid-null': 'print("null")'}.get(mode))
        if mode == 'missing':
            p.unlink()
    result, state, before = dispatch(tmp_path, fake_bin, monkeypatch, p)
    check_dispatch(result, state, before, expected, stage)


@pytest.mark.parametrize('record,kind', [('', '設計'), ('  ', 'コード'), ('/tmp/日本語 空白.json', '設計')])
def test_record_arguments(tmp_path, fake_bin, monkeypatch, record, kind):
    seen = tmp_path / 'seen.json'
    p = adapter(tmp_path, body=f'import sys,json\nopen({str(seen)!r},"w").write(json.dumps(sys.argv[1:]))\nprint({json.dumps(PASS)!r})\n')
    monkeypatch.setenv('REVIEW_GATE_RECORD', record)
    result, state, before = dispatch(tmp_path, fake_bin, monkeypatch, p, kind=kind)
    entry = check_dispatch(result, state, before, 'pass')
    assert entry['kind'] == kind
    assert json.loads(seen.read_text()) == [record, str(tmp_path / 'work')]


@pytest.mark.parametrize('data', [None, [], {}, dict(PASS, stages={}),
    dict(PASS, stages={s: 1 for s in PASS['stages']}),
    dict(PASS, reasons=['unexpected']), dict(PASS, stopped_at='C'),
    dict(blocked(), stages=PASS['stages']), dict(blocked(), reasons=[]),
    dict(PASS, reasons=[0]), {k:v for k,v in PASS.items() if k != 'stopped_at'}])
def test_invalid_outputs(data):
    with pytest.raises((ValueError, TypeError)):
        rw.classify(data, 0)


@pytest.mark.parametrize('delta,expected', [(29.999, 'pass'), (30, 'timeout'), (30.001, 'timeout')])
def test_deadline_boundary(tmp_path, monkeypatch, delta, expected):
    p = adapter(tmp_path)
    # select loop calls the clock once for stdout and once for EOF; use a constant
    # until classify has consumed output, then expose the exact total elapsed time.
    original = rw.classify
    finished = [False]
    def classify(*args):
        result = original(*args)
        finished[0] = True
        return result
    monkeypatch.setattr(rw, 'classify', classify)
    monkeypatch.setattr(rw.time, 'monotonic', lambda: delta if finished[0] else 0)
    assert rw.evaluate(str(p), '', str(tmp_path))[0] == expected


def test_dispatch_timeout(tmp_path, fake_bin, monkeypatch):
    fifo = tmp_path / 'alive.fifo'
    os.mkfifo(fifo)
    fd = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
    child_code = f'import os,time; fd=os.open({str(fifo)!r},os.O_WRONLY); os.write(fd,b"ready"); time.sleep(120)'
    p = adapter(tmp_path, body=f'import subprocess,sys\nsubprocess.Popen([sys.executable,"-c",{child_code!r}])\n')
    started = time.monotonic()
    try:
        result, state, before = dispatch(tmp_path, fake_bin, monkeypatch, p, timeout=38)
        elapsed = time.monotonic() - started
        entry = check_dispatch(result, state, before, 'timeout')
        assert 29 <= elapsed < 36
        assert entry['reasons'][0] == '時間切れ'
        assert set(entry['reasons'][1:]) <= {'履歴照合失敗', '対象SHA未取得', '対象同一性未取得'}
        assert os.read(fd, 16) == b'ready'
        # EOF proves the inherited writer closed. A living descendant would EAGAIN.
        assert os.read(fd, 16) == b''
    finally:
        os.close(fd)


def test_missing_adapter(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.delenv('CODEX_REVIEW_ADAPTER', raising=False)
    assert rw.evaluate(str(tmp_path), '', str(tmp_path))[0] == 'missing'
    rw.observe(str(tmp_path), 'id', 'none:test', '設計', str(tmp_path))
    assert json.loads((tmp_path / 'routing-warn.jsonl').read_text())['verdict'] == 'missing'


def test_internal_failure(tmp_path, monkeypatch, capsys):
    def fail(*args):
        raise RuntimeError('SYNTHETIC_SECRET')
    monkeypatch.setattr(rw, 'evaluate', fail)
    rw.observe(str(tmp_path), 'id', 'target', 'コード', str(tmp_path))
    entry = json.loads((tmp_path / 'routing-warn.jsonl').read_text())
    assert entry['verdict'] == 'error'
    assert 'SYNTHETIC_SECRET' not in capsys.readouterr().err


def test_append_and_write_failure(tmp_path, fake_bin, monkeypatch):
    p = adapter(tmp_path)
    for count in range(2):
        result, state, before = dispatch(tmp_path, fake_bin, monkeypatch, p)
        check_dispatch(result, state, before, 'pass', prior=count)
    log = state / 'routing-warn.jsonl'
    log.unlink()
    log.mkdir()
    result, _, _ = dispatch(tmp_path, fake_bin, monkeypatch, p)
    assert result.returncode == 0
    assert sum('routing警告:' in s for s in result.stderr.splitlines()) == 1
    assert '記録失敗' in result.stderr


def test_concurrent_append(tmp_path, monkeypatch):
    monkeypatch.setenv('CODEX_REVIEW_ADAPTER', str(tmp_path / 'missing.py'))
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: rw.observe(str(tmp_path), str(i), 'target', '設計', str(tmp_path)), range(24)))
    entries = [json.loads(s) for s in (tmp_path / 'routing-warn.jsonl').read_text().splitlines()]
    assert {e['dispatch_id'] for e in entries} == {str(i) for i in range(24)}


def gate_shim(fake_bin, state, exitcode=0):
    p = fake_bin / 'python3'
    p.write_text(f'''#!{sys.executable}
import os,sys,json
from pathlib import Path
if len(sys.argv)>2 and sys.argv[1].endswith('/round_gate.py'):
    if sys.argv[2]=='gate':
        if '--reserve-run-id' in sys.argv:
            Path({str(state / 'reserved.reservation')!r}).write_text('unchanged reservation')
        print(json.dumps(dict(authority='project_prerelease',total_round=1)))
        sys.exit({exitcode})
    if sys.argv[2]=='record': sys.exit(0)
os.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[1:]])
''')
    p.chmod(0o755)


def test_prerelease_order(tmp_path, fake_bin, monkeypatch):
    state = tmp_path / 'state'
    state.mkdir()
    gate_shim(fake_bin, state)
    marker = state / 'reserved.reservation'
    p = adapter(tmp_path, body=f'from pathlib import Path\nassert Path({str(marker)!r}).read_text()=="unchanged reservation"\nprint({json.dumps(blocked())!r})\nraise SystemExit(1)\n')
    result, state, before = dispatch(tmp_path, fake_bin, monkeypatch, p)
    check_dispatch(result, state, before, 'would_block', 'A')
    assert marker.read_text() == 'unchanged reservation'
    assert len(list(state.glob('*.reservation'))) == 1


def test_existing_gate_rejection(tmp_path, fake_bin, monkeypatch):
    gate_shim(fake_bin, tmp_path / 'state', 4)
    result, state, _ = dispatch(tmp_path, fake_bin, monkeypatch, tmp_path / 'absent')
    assert result.returncode == 4
    assert not (state / 'routing-warn.jsonl').exists()
    assert not list(state.glob('*.state'))


@pytest.mark.parametrize('size,expected', [(65535, 'pass'), (65536, 'pass'), (65537, 'invalid')])
def test_output_size_boundary(tmp_path, size, expected):
    raw = json.dumps(PASS).ljust(size)
    p = adapter(tmp_path, body=f'import sys\nsys.stdout.write({raw!r})')
    assert rw.evaluate(str(p), '', str(tmp_path))[0] == expected


@pytest.mark.parametrize('ignored', [False, True])
def test_detached_worker_cleanup(tmp_path, monkeypatch, ignored):
    fifo = tmp_path / 'detached.fifo'
    os.mkfifo(fifo)
    fd = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
    marker = tmp_path / 'worker.pid'
    code = f'import os,time; fd=os.open({str(fifo)!r},os.O_WRONLY); os.write(fd,b"ready"); time.sleep(120)'
    p = adapter(tmp_path, body=f"""import os,signal,subprocess,sys,time
child=subprocess.Popen([sys.executable,'-c',{code!r}],start_new_session=True)
open({str(marker)!r},'w').write(str(child.pid))
try:
    time.sleep(120)
except KeyboardInterrupt:
    os.killpg(child.pid,signal.SIGKILL)
    child.wait()
""")
    monkeypatch.setattr(rw, 'BUDGET_SECONDS', 0.5)
    started = time.monotonic()
    previous = signal.signal(signal.SIGINT, signal.SIG_IGN if ignored else signal.default_int_handler)
    try:
        assert rw.evaluate(str(p), '', str(tmp_path))[0] == 'timeout'
        assert time.monotonic() - started < 2
        assert os.read(fd, 16) == b'ready'
        assert os.read(fd, 16) == b''
    finally:
        signal.signal(signal.SIGINT, previous)
        os.close(fd)
        if marker.exists():
            try:
                os.killpg(int(marker.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.mark.parametrize('chunk', [None, 'first12', 12, 1, 0])
def test_short_write(tmp_path, monkeypatch, capsys, chunk):
    monkeypatch.setenv('CODEX_REVIEW_ADAPTER', str(tmp_path / 'missing'))
    original = os.write
    calls = []
    def write(fd, data):
        calls.append(len(data))
        assert len(calls) < 1000, 'write made no progress'
        size = (12 if len(calls) == 1 else len(data)) if chunk == 'first12' else chunk
        return original(fd, data if size is None else data[:size])
    with monkeypatch.context() as patch:
        patch.setattr(rw.os, 'write', write)
        rw.observe(str(tmp_path), 'first', 'target', 'コード', str(tmp_path))
    rw.observe(str(tmp_path), 'second', 'target', 'コード', str(tmp_path))
    rows = [json.loads(s) for s in (tmp_path / 'routing-warn.jsonl').read_text().splitlines()]
    assert [r['dispatch_id'] for r in rows] == (['second'] if chunk == 0 else ['first', 'second'])
    if chunk not in (None, 0):
        assert len(calls) > 1
    assert ('記録失敗' in capsys.readouterr().err) == (chunk == 0)


@pytest.mark.parametrize('broken', [False, True])
def test_readme_aggregation(tmp_path, broken):
    readme = (ROOT / 'README.md').read_text()
    command = readme.split("python3 - <<'PY'\n", 1)[1].split('\nPY\n', 1)[0]
    entry = dict(time=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 verdict='pass', stopped_at=None, reasons=['全段通過'])
    lines = [json.dumps(entry)]
    if broken:
        lines += ['{"unfinished":', '', '[]', json.dumps(dict(entry, reasons=2)),
                  json.dumps(dict(entry, time='broken'))]
    lines.append(json.dumps(entry))
    (tmp_path / 'routing-warn.jsonl').write_text('\n'.join(lines) + '\n')
    offset = readme[:readme.index(command)].count('\n')
    program = f'exec(compile({(chr(10) * offset + command)!r}, {str(ROOT / "README.md")!r}, "exec"))'
    result = subprocess.run([sys.executable, '-c', program], capture_output=True, text=True,
                            env=dict(os.environ, CODEX_WATCH_DIR=str(tmp_path)), timeout=5)
    assert result.returncode == 0, result.stderr
    assert "('pass', None, '全段通過'): 2" in result.stdout
    assert f'破損行: {5 if broken else 0}' in result.stdout


@pytest.mark.parametrize('mode', ['normal', 'fifo-open', 'fifo-full', 'stderr-full'])
def test_blocked_dispatch(tmp_path, fake_bin, monkeypatch, mode):
    state = tmp_path / 'state'
    state.mkdir()
    p = adapter(tmp_path)
    descriptors = []
    stderr_fd = None
    if mode.startswith('fifo'):
        fifo = state / 'routing-warn.jsonl'
        os.mkfifo(fifo)
        if mode == 'fifo-full':
            read_fd = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
            write_fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
            descriptors += [read_fd, write_fd]
            while True:
                try:
                    os.write(write_fd, b'x' * 4096)
                except BlockingIOError:
                    break
    elif mode == 'stderr-full':
        # Saturate only the observation stderr: earlier CLI diagnostics are outside
        # this warning's deadline and must remain readable.
        fifo = tmp_path / 'stderr.fifo'
        os.mkfifo(fifo)
        read_fd = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
        stderr_fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
        descriptors += [read_fd, stderr_fd]
        while True:
            try:
                os.write(stderr_fd, b'x' * 4096)
            except BlockingIOError:
                break
        shim = fake_bin / 'python3'
        shim.write_text(f'''#!{sys.executable}
import os,sys
if len(sys.argv)>1 and sys.argv[1].endswith('/routing_warn.py'):
    fd=os.open({str(fifo)!r},os.O_WRONLY)
    os.dup2(fd,2)
    os.close(fd)
os.execv({sys.executable!r},[{sys.executable!r},*sys.argv[1:]])
''')
        shim.chmod(0o755)
    started = time.monotonic()
    try:
        result, state, before = dispatch(tmp_path, fake_bin, monkeypatch, p, timeout=36)
        elapsed = time.monotonic() - started
        assert result.returncode == 0, result.stdout
        run_id = result.stdout.strip().splitlines()[-1]
        assert (state / f'{run_id}.state').exists()
        deadline = time.monotonic() + 2
        while not (tmp_path / 'sent.txt').exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert (tmp_path / 'sent.txt').exists()
        assert elapsed < 35
        if mode == 'normal':
            check_dispatch(result, state, before, 'pass')
        else:
            assert elapsed >= 30
        if mode == 'stderr-full':
            assert json.loads((state / 'routing-warn.jsonl').read_text())['dispatch_id'] == run_id
    finally:
        for fd in descriptors:
            os.close(fd)


def test_whole_budget(monkeypatch):
    calls = []
    class Child:
        pid = 123456789
        def wait(self, timeout=None):
            calls.append(timeout)
            if len(calls) == 1:
                assert timeout == 31
                raise subprocess.TimeoutExpired('observation', timeout)
    def launch(argv, **kwargs):
        assert argv[2] == '--observe'
        assert argv[3:] == ['state', 'id', 'target', 'kind', 'work']
        return Child()
    monkeypatch.setattr(rw.subprocess, 'Popen', launch)
    monkeypatch.setattr(rw.os, 'killpg', lambda pid, sig: calls.append((pid, sig)))
    rw.run_bounded(['state', 'id', 'target', 'kind', 'work'])
    assert calls == [31, (123456789, signal.SIGKILL), None]
