#!/usr/bin/env python3
"""Observe routing without changing dispatch authority. Never persist raw adapter output."""
import datetime
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import selectors
import time

BUDGET_SECONDS = 30
STAGES = ('A', '1', '2', '3', 'B')
MAX_OUTPUT = 65536


def classify(data, returncode):
    """Validate the route wire contract, then retain only safe reason categories."""
    if not isinstance(data, dict) or not isinstance(data.get('stages'), dict):
        raise ValueError('shape')
    stages = data['stages']
    stopped = data.get('stopped_at')
    reasons = data.get('reasons')
    if ('stopped_at' not in data or set(stages) != set(STAGES)
            or not isinstance(reasons, list) or not all(isinstance(s, str) for s in reasons)):
        raise ValueError('fields')
    if stopped is None:
        if not all(stages[s] is True for s in STAGES) or reasons:
            raise ValueError('pass')
        if returncode != 0:
            return 'error', None, ['処理失敗']
        return 'pass', None, ['全段通過']
    if stopped not in STAGES:
        raise ValueError('stage')
    i = STAGES.index(stopped)
    if (not all(stages[s] is True for s in STAGES[:i]) or stages[stopped] is not False
            or not all(stages[s] == 'not_evaluated' for s in STAGES[i + 1:]) or not reasons):
        raise ValueError('stop')
    if returncode != 1:
        return 'error', None, ['処理失敗']
    # Route reasons may contain command stderr, paths or document text. Do not copy them.
    categories = []
    for reason in reasons:
        if 'series/predecessor record missing' in reason:
            category = '系列・前身記録不足'
        elif '記録された作業場所が消失' in reason:
            category = '作業場所消失'
        elif 'cumulative threshold exceeded' in reason:
            category = '累計差分超過'
        elif 'same family in two adjacent rounds' in reason:
            category = '同族指摘の反復'
        elif 'missing check:' in reason or 'missing code evidence:' in reason:
            category = '検査記録不足'
        elif 'green' in reason:
            category = '全体試験の記録不備'
        else:
            category = 'その他の判定理由'
        if category not in categories:
            categories.append(category)
    return 'would_block', stopped, categories


def evaluate(adapter, record, workdir):
    deadline = time.monotonic() + BUDGET_SECONDS
    if not Path(adapter).is_file():
        return 'missing', None, ['部品なし']
    child = None
    try:
        child = subprocess.Popen([sys.executable, adapter, record, workdir],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, start_new_session=True,
                                 preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL))
        # Bound untrusted output in memory; never put raw output in a file.
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            raw = bytearray()
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise subprocess.TimeoutExpired('routing', BUDGET_SECONDS)
                block = os.read(child.stdout.fileno(), min(8192, MAX_OUTPUT + 1 - len(raw)))
                if not block:
                    selector.unregister(child.stdout)
                    break
                raw.extend(block)
                if len(raw) > MAX_OUTPUT:
                    return 'invalid', None, ['出力不正']
            child.wait(timeout=max(0, deadline - time.monotonic()))
            try:
                result = classify(json.loads(raw), child.returncode)
            except (ValueError, TypeError, KeyError):
                result = ('error', None, ['処理失敗']) if child.returncode else ('invalid', None, ['出力不正'])
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired('routing', BUDGET_SECONDS)
            return result
    except subprocess.TimeoutExpired:
        # The existing adapter supervises a worker in another session. Give its
        # KeyboardInterrupt handler a bounded chance to kill that worker first.
        if child is not None:
            try:
                os.killpg(child.pid, signal.SIGINT)
            except ProcessLookupError:
                pass
            try:
                child.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                pass
        return 'timeout', None, ['時間切れ']
    except (OSError, ValueError):
        return 'error', None, ['処理失敗']
    finally:
        if child is not None:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()
            if child.stdout is not None:
                child.stdout.close()


def observe(state_dir, run_id, target, kind, workdir):
    adapter = os.environ.get('CODEX_REVIEW_ADAPTER', str(Path.home() / '.claude/skills/review-gate/adapter.py'))
    try:
        verdict, stopped, reasons = evaluate(adapter, os.environ.get('REVIEW_GATE_RECORD', ''), workdir)
    except Exception:
        verdict, stopped, reasons = 'error', None, ['処理失敗']
    entry = dict(dispatch_id=run_id, target=target, kind=kind,
                 time=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 verdict=verdict, stopped_at=stopped, reasons=reasons)
    label = {'pass': '全段通過', 'would_block': '停止相当', 'error': '処理失敗',
             'invalid': '出力不正', 'timeout': '時間切れ', 'missing': '部品なし'}[verdict]
    notice = 'routing警告: ' + label + ' ' + json.dumps(entry, ensure_ascii=True, separators=(',', ':'))
    try:
        line = (json.dumps(entry, ensure_ascii=True, separators=(',', ':')) + '\n').encode()
        fd = os.open(Path(state_dir) / 'routing-warn.jsonl', os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            while line:
                written = os.write(fd, line)
                if written <= 0:
                    raise OSError('short write')
                line = line[written:]
        finally:
            os.close(fd)
    except OSError:
        notice += ' 記録失敗'
    print(notice, file=sys.stderr)


def run_bounded(args):
    """Caller-side deadline covers evaluation, recording and blocked stderr alike."""
    child = None
    try:
        child = subprocess.Popen([sys.executable, __file__, '--observe', *args],
                                 stdin=subprocess.DEVNULL, start_new_session=True)
        child.wait(timeout=BUDGET_SECONDS + 1)
    except (subprocess.TimeoutExpired, OSError):
        pass
    finally:
        if child is not None:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()


if __name__ == '__main__':
    if sys.argv[1:2] == ['--observe']:
        observe(*sys.argv[2:])
    else:
        run_bounded(sys.argv[1:])
