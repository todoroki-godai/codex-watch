"""Offline entry-point contracts. Input partitions: tests/progress-overdue-verification.md."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(os.environ.get('CODEX_OVERDUE_TEST_ROOT', Path(__file__).resolve().parents[1]))
@pytest.fixture(scope='session')
def baseline_source(tmp_path_factory):
    baseline = tmp_path_factory.mktemp('overdue-baseline')
    (baseline / 'bin').mkdir()
    for name in ('codex-impl', 'codex-watch', 'codex-status', '_codex_common.sh'):
        source = subprocess.run(['git', '-C', str(Path(__file__).resolve().parents[1]),
                                 'show', f'7c44521:bin/{name}'], check=True, capture_output=True).stdout
        (baseline / 'bin' / name).write_bytes(source)
    shutil.copytree(ROOT / 'lib', baseline / 'lib')
    return baseline


def executable(path, body):
    path.write_text('#!/bin/sh\n' + body)
    path.chmod(0o755)


@pytest.fixture
def sandbox(tmp_path):
    fake = tmp_path / 'fake'
    fake.mkdir()
    home = tmp_path / 'home'
    home.mkdir()
    state = tmp_path / 'state'
    state.mkdir()
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('CODEX_', 'AWS_', 'GH_', 'GITHUB_'))}
    env.update(HOME=str(home), PATH=f'{fake}:{env["PATH"]}', CODEX_WATCH_DIR=str(state))
    for name in ('aws', 'gh', 'codex', 'git'):
        executable(fake / name, 'exit 99\n')
    return tmp_path, fake, state, env


@pytest.fixture
def launch(sandbox):
    tmp, fake, state, env = sandbox
    tree = tmp / 'source'
    for folder in ('bin', 'lib'):
        shutil.copytree(ROOT / folder, tree / folder)
    # No real config, credentials, network, git mutation or LLM calls.
    (tree / 'lib/codex_impl_aws.py').write_text(
        'import sys\nif len(sys.argv)==1: print("CODEX_IMPL_AWS_STATE=none; CODEX_IMPL_AWS_EXPIRATION=; " )\n')
    executable(fake / 'codex', 'cat >/dev/null\n')
    env.update(CODEX_SUMMARY='#0', CODEX_IMPL_ALLOW_MAIN='1', CODEX_IMPL_ALLOW_MISSING_NODE_MODULES='1')

    def run(body, override=None):
        prompt = tmp / 'prompt with spaces.md'
        prompt.write_bytes(('直しの出所: なし\n' + body).encode())
        if override is not None:
            env['CODEX_IMPL_ESTIMATE_MIN'] = override
        trace_dir = os.environ.get('CODEX_OVERDUE_TRACE_DIR')
        if trace_dir:
            trace = Path(trace_dir)
            trace.mkdir(parents=True, exist_ok=True)
            trace_file = trace / f'parser-{len(list(trace.glob("parser-*")))}.log'
            script = tree / 'bin/codex-impl'
            source = script.read_text()
            # Record executed Python line numbers only, never input or environment values.
            source = source.replace("if value is None:",
                "_trace = open(" + repr(str(trace_file)) + ", 'w')\n"
                "def _parser_trace(frame, event, arg):\n"
                "    if event == 'line' and frame.f_code.co_filename == '<stdin>':\n"
                "        _trace.write(str(frame.f_lineno) + '\\n')\n"
                "    return _parser_trace\n"
                "sys.settrace(_parser_trace)\n"
                "sys._getframe().f_trace = _parser_trace\n"
                "if value is None:", 1)
            script.write_text(source)
        r = subprocess.run(['bash', str(tree / 'bin/codex-impl'), str(tmp), str(prompt)],
                           env=env, capture_output=True, text=True, errors="replace", timeout=10)
        assert r.returncode == 0, r.stderr
        rows = (state / (r.stdout.strip() + '.state')).read_text().splitlines()
        assert len([row for row in rows if row.startswith('estimate_min=')]) == 1
        return next(row.split('=', 1)[1] for row in rows if row.startswith('estimate_min=')), r
    return run


@pytest.mark.parametrize('body,override,expected', [
    ('## 見込み: 45分\n', None, '45'), ('見込み: 1分', None, '1'),
    ('## 見込み: 2分\r\n', None, '2'),
    ('見込み: 1分\n## 見込み: 9分', None, '1'),
    ('見込み: x分\n見込み: 9分', None, ''),
    ('見込み: 0分', None, '0'), ('見込み: -1分', None, '-1'),
    ('見込み: 01分', None, '01'), ('見込み: ' + '9'*40 + '分', None, '9'*40),
    ('見込み: 1.5分', None, ''), ('見込み: 分', None, ''), ('本文', None, ''),
    (' 見込み: 1分', None, '1'), ('見込み：1分', None, '1'),
    ('本文 見込み: 1分', None, '1'), ('見込み: 1分ほか', None, '1'),
    # Sanitized spelling from the 2026-11-11 run prompts (one case per form).
    ('- 終わり: 確認する。見込み: 30分。', None, '30'),
    ('- 終わり: 確認する。見込み: 40分。', None, '40'),
    ('- **見込み: 約63分**。', None, '63'),
    ('見込み: 約40分', None, '40'),
    ('## 見込み: 25分', None, '25'),
    ('**見込み: 約63分**', None, '63'),
    ('文。見込み： 約30 分（確認込み）。', None, '30'),
    ('文。見込み: 3分。\n## 見込み: 9分', None, '9'),
    ('文。見込み: 3分。見込み: 9分。', None, '3'),
    ('見込み： 約9分（確認込み）\n見込み: 3分', None, '9'),
    ('\ufeff見込み: 30分', None, '30'),
    ('見込み: x分\n文。見込み: 9分。', None, ''),
    ('見込み: 1分', '9', '9'), ('見込み: 1分', '', ''),
    ('見込み: 1分', '1.5', ''), ('見込み: 1分', '1\n2', ''),
    ('見込み: 1分', '$(touch injected)', ''), ('見込み: $((1+1))分', None, ''),
])
def test_estimate_record(launch, body, override, expected):
    value, r = launch(body, override)
    assert value == expected
    assert len(r.stderr.splitlines()) == (0 if expected else 1)
    if not expected:
        assert r.stderr.startswith('警告:')


@pytest.fixture
def watch(sandbox, baseline_source):
    tmp, fake, state, env = sandbox
    executable(fake / 'date', 'echo 1000\n')
    executable(fake / 'stat', 'echo 1000\n')
    executable(fake / 'sleep', 'echo SLEPT >&2\nexit 77\n')
    def run(estimate='1', elapsed=121, marker=False, dead=False, maximum=0,
            baseline=False, verdict=False, command='codex-watch'):
        log = state / 'run.log'
        log.write_text('tokens used\n' if verdict else '')
        (state / 'run.state').write_text(
            f'run_id=run\npid={99999999 if dead else os.getpid()}\nlog={log}\n'
            f'workdir={tmp}\nstarted_at={1000-elapsed}\n' +
            ('' if estimate is None else f'estimate_min={estimate}\n'))
        m = state / 'run.overdue'
        if marker:
            m.touch()
        source = baseline_source if baseline else ROOT
        r = subprocess.run(['bash', '-x', str(source / 'bin' / command), 'run', '99999', str(maximum)],
                           env=env, capture_output=True, text=True, errors="replace", timeout=10)
        trace_dir = os.environ.get('CODEX_OVERDUE_TRACE_DIR')
        if trace_dir:
            p = Path(trace_dir)
            p.mkdir(parents=True, exist_ok=True)
            (p / f'trace-{len(list(p.glob("trace-*")))}.log').write_text(r.stderr)
        return r, m
    return run


@pytest.mark.parametrize('elapsed,overdue', [(119, False), (120, False), (121, True), (61, False)])
def test_boundary(watch, elapsed, overdue):
    r, marker = watch(elapsed=elapsed)
    assert r.returncode == 0
    assert r.stdout == ('OVERDUE: run 見込み1分の2倍を超過（経過2分）。git log・status と出力を読んで判断する\n'
                        if overdue else 'TIMEOUT: run 監視上限0秒に到達（プロセスはまだ生存） (ログ先頭ヘッダー参考値: model=unresolved/unresolved effort=unresolved/unresolved)\n')
    assert marker.exists() == overdue


@pytest.mark.parametrize('estimate', [None, '', '0', '-1', '1.5', 'x', '9'*40, '$(touch injected)'])
def test_legacy_output_unchanged(watch, estimate):
    new, marker = watch(estimate=estimate)
    old, _ = watch(estimate=estimate, baseline=True)
    assert new.returncode == old.returncode == 0
    assert new.stdout == old.stdout
    assert not marker.exists()


def test_run_start_and_repeat(watch):
    first, marker = watch(elapsed=500, maximum=100)
    assert first.returncode == 0 and first.stdout.startswith('OVERDUE:')
    assert marker.exists()
    second, _ = watch(elapsed=500, maximum=100)
    assert second.returncode == 77 and 'SLEPT' in second.stderr
    assert second.stdout == ''


def test_marker_keeps_watching(watch):
    r, _ = watch(marker=True, maximum=100)
    assert r.returncode == 77 and 'SLEPT' in r.stderr
    assert r.stdout == ''


def test_exit_wins(watch):
    r, marker = watch(dead=True)
    assert r.returncode == 0 and r.stdout.startswith('EXIT:')
    assert 'OVERDUE:' not in r.stdout and not marker.exists()


def test_verdict_alive(watch):
    r, marker = watch(verdict=True)
    assert r.returncode == 0 and marker.exists()
    assert [row.split(':', 1)[0] for row in r.stdout.splitlines()] == ['VERDICT', 'OVERDUE']


@pytest.mark.parametrize('estimate', [None, '', '45'])
def test_status(watch, estimate):
    new, _ = watch(estimate=estimate, command='codex-status')
    old, _ = watch(estimate=estimate, command='codex-status', baseline=True)
    assert new.returncode == old.returncode == 0
    if estimate:
        assert '経過     : 2分1秒 / 見込み45分' in new.stdout
        assert new.stdout.replace(' / 見込み45分', '') == old.stdout
    else:
        assert new.stdout == old.stdout


def test_overdue_rearm_then_exit(watch):
    first, marker = watch(elapsed=500, maximum=100)
    assert first.returncode == 0 and first.stdout.startswith('OVERDUE:')
    assert marker.exists()
    final, _ = watch(marker=True, dead=True)
    assert final.returncode == 0 and final.stdout.startswith('EXIT:')
    assert 'OVERDUE:' not in final.stdout
