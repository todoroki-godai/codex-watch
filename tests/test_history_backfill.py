"""Expectations: issue #40 and history-backfill instructions, not current output."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
import history_backfill as hb
import prerelease as pre
import round_gate as rg
from test_prerelease import case

FIXTURE = ROOT / 'tests/fixtures/history-backfill'
TARGET = 'issue:min-sys/updater-index#2023'
IDS = ['review-2023-d1-20261115-064619-99965', 'review-2023-d2-20261115-065224-70781']


@pytest.fixture
def sample(tmp_path, monkeypatch):
    state = tmp_path / 'history-state'
    state.mkdir()
    for path in FIXTURE.glob('*.state'):
        shutil.copy2(path, state / path.name)
    body = tmp_path / 'body.md'
    body.write_text((FIXTURE / 'table.md').read_text())
    fake = tmp_path / 'fake'
    fake.mkdir()
    gh = fake / 'gh'
    gh.write_text('''#!/usr/bin/env python3
import os,json,sys
from pathlib import Path
Path(os.environ['CALLS']).write_text(json.dumps(sys.argv[1:]))
assert sys.argv[1:3] in (['issue','view'],['pr','view'])
print(Path(os.environ['BODY']).read_text(),end='')
''')
    gh.chmod(0o755)
    monkeypatch.setenv('PATH', str(fake) + os.pathsep + os.environ['PATH'])
    monkeypatch.setenv('BODY', str(body))
    monkeypatch.setenv('CALLS', str(tmp_path / 'calls'))
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    return dict(state=state, body=body, tmp=tmp_path)


def snapshot(state):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in state.iterdir()}


def run(s, *args, target=TARGET):
    before = snapshot(s['state'])
    result = subprocess.run([str(ROOT / 'bin/codex-history-backfill'), target,
                             '--state-dir', str(s['state']), *args],
                            text=True, capture_output=True, timeout=15)
    assert snapshot(s['state']) == before
    return result


def expected(body):
    for n, rid in enumerate(IDS, 1):
        lines = body.splitlines(keepends=True)
        body = ''.join(line.rstrip('\n') + f' <!-- dispatch_id={rid} -->\n'
                       if line.startswith(f'| {n} |') else line for line in lines)
    return body


# First test: actual two legacy rows -> CLI -> existing complete exception boundary.
def test_real_history_gate(sample, case):
    s, c = sample, case
    # case has its own fake gh; restore the sample reader for the CLI.
    policy_path = os.environ['PATH']
    os.environ['PATH'] = str(s['tmp'] / 'fake') + os.pathsep + os.environ['PATH']
    os.environ['BODY'] = str(s['body'])
    result = run(s)
    assert result.returncode == 0, result.stderr
    assert result.stdout == expected(s['body'].read_text())
    assert result.stderr == ''
    os.environ['PATH'] = policy_path
    for p in c['state'].iterdir(): p.unlink()
    for p in s['state'].iterdir(): shutil.copy2(p, c['state'] / p.name)
    c['data']['target'] = TARGET
    c['data']['kind'] = '設計'
    body = result.stdout + '\n## 公開前裁定' + c['body']().split('## 公開前裁定', 1)[1]
    # Fixed registry/git/policy fixture from existing A tests; no live API or dispatch.
    evidence = pre.evaluate(rg.parse_target(TARGET), str(c['work']), c['state'], body,
                            3, 'decision-1', '設計', registry=c['registry'])
    assert evidence['authority'] == 'project_prerelease'
    assert pre.history(result.stdout, c['state'], TARGET, strict=True) == 2


@pytest.mark.parametrize('mode', ['missing', 'duplicate-state', 'duplicate-row', 'duplicate-id',
    'used-id', 'other-target', 'wrong-time', 'missing-round', 'missing-kind_label',
    'missing-started_at_human', 'missing-head_sha', 'missing-reviewer', 'invalid-id'])
def test_ambiguous(sample, mode):
    s = sample
    p = s['state'] / (IDS[0] + '.state')
    data = p.read_text()
    body = s['body'].read_text()
    if mode == 'missing': p.unlink()
    elif mode == 'duplicate-state': (s['state'] / 'duplicate.state').write_text(data)
    elif mode == 'duplicate-row':
        body += next(line for line in body.splitlines(True) if line.startswith('| 1 |'))
    elif mode == 'duplicate-id':
        other = s['state'] / (IDS[1] + '.state')
        other.write_text(other.read_text().replace(IDS[1], IDS[0]))
    elif mode == 'used-id':
        body = body.rstrip('\n') + f' <!-- dispatch_id={IDS[0]} -->\n'
    elif mode == 'other-target': p.write_text(data.replace(TARGET, 'pr:min-sys/updater-index#2023'))
    elif mode == 'wrong-time': p.write_text(data.replace('06:46:20', '06:46:21'))
    elif mode == 'invalid-id': p.write_text(data.replace(IDS[0], 'bad id'))
    else:
        key = mode.removeprefix('missing-')
        p.write_text(''.join(line for line in data.splitlines(True) if not line.startswith(key + '=')))
    s['body'].write_text(body)
    result = run(s)
    assert result.returncode == 1, result.stderr
    assert '未補完: | 1 |' in result.stderr
    line1 = next(line for line in result.stdout.splitlines() if line.startswith('| 1 |'))
    assert '<!-- dispatch_id=' not in line1
    assert result.stdout.count('\n') == body.count('\n')


def test_existing(sample):
    body = expected(sample['body'].read_text())
    sample['body'].write_text(body)
    assert run(sample).stdout == body
    # Even a nonmatching pre-existing ID is never rewritten.
    body = body.replace(IDS[0], 'existing-independent-run')
    sample['body'].write_text(body)
    result = run(sample)
    assert result.returncode == 0
    assert result.stdout == body


def test_description(sample):
    body = (FIXTURE / 'body.md').read_text()
    sample['body'].write_text(body)
    result = run(sample)
    assert result.returncode == 1
    assert result.stdout == expected(body)
    assert '説明文または解釈できない行: - 巡2' in result.stderr
    assert '未補完' not in result.stderr


@pytest.mark.parametrize('missing', [('kind_label',), ('reviewer',), ('kind_label', 'reviewer')])
def test_missing_values_do_not_default(sample, missing):
    p = sample['state'] / (IDS[0] + '.state')
    p.write_text(''.join(line for line in p.read_text().splitlines(True)
                         if not any(line.startswith(key + '=') for key in missing)))
    body = sample['body'].read_text()
    if 'kind_label' in missing:
        body = body.replace('| 1 | 設計 |', '| 1 | コード |')
    if 'reviewer' in missing:
        body = body.replace('| review-2023-d1 |', '| codex |')
    sample['body'].write_text(body)
    result = run(sample)
    assert result.returncode == 1
    assert '未補完: | 1 |' in result.stderr
    assert IDS[0] not in result.stdout
    assert IDS[1] in result.stdout


@pytest.mark.parametrize('line', ['|--- 説明文', '| 巡 | これは説明文'])
def test_table_like_description(sample, line):
    body = sample['body'].read_text() + line + '\n'
    sample['body'].write_text(body)
    result = run(sample)
    assert result.returncode == 1
    assert result.stdout == expected(body)
    assert '説明文または解釈できない行: ' + line in result.stderr


@pytest.mark.parametrize('size,ok', [(0,False),(1,True),(160,True),(161,False)])
def test_id_boundary(sample, size, ok):
    p = sample['state'] / (IDS[0] + '.state')
    p.write_text(p.read_text().replace(IDS[0], 'a' * size))
    result = run(sample)
    assert result.returncode == (0 if ok else 1)
    assert ('<!-- dispatch_id=' + 'a' * size + ' -->' in result.stdout) == ok


@pytest.mark.parametrize('mode', ['duplicate-key', 'broken-line', 'missing-dir'])
def test_bad_state(sample, mode):
    p = sample['state'] / (IDS[0] + '.state')
    if mode == 'missing-dir':
        result = run(sample, '--state-dir', str(sample['tmp'] / 'absent'))
    else:
        p.write_text(p.read_text() + ('run_id=overwritten\n' if mode == 'duplicate-key' else 'broken\n'))
        result = run(sample)
    assert result.returncode == 2
    assert result.stdout == ''


@pytest.mark.parametrize('target', [TARGET, 'pr:min-sys/updater-index#2023'])
def test_target(sample, target):
    if target.startswith('pr:'):
        for p in sample['state'].iterdir(): p.write_text(p.read_text().replace(TARGET, target))
    result = run(sample, target=target)
    assert result.returncode == 0
    assert json.loads((sample['tmp'] / 'calls').read_text()) == [target.split(':')[0], 'view',
        '2023', '-R', 'min-sys/updater-index', '--json', 'body', '-q', '.body']


@pytest.mark.parametrize('body', ['## Other\n', '## 巡の履歴\n\n## 巡の履歴\n'])
def test_section(sample, body):
    sample['body'].write_text(body)
    result = run(sample)
    assert result.returncode == 2 and result.stdout == ''


def test_output(sample):
    p = sample['tmp'] / 'proposal.md'
    body = sample['body'].read_text()
    result = run(sample, '--output', str(p))
    assert result.returncode == 0 and result.stdout == ''
    assert p.read_text() == expected(body)
    assert sample['body'].read_text() == body


def test_output_protected(sample):
    result = run(sample, '--output', str(sample['state'] / 'proposal.md'))
    assert result.returncode == 2
    assert not (sample['state'] / 'proposal.md').exists()


def test_semantic(sample):
    body = sample['body'].read_text()
    # Whitespace within cells is insignificant, time and SHA values remain exact.
    body = body.replace('| 1 |', '|  1  |').replace('| 設計 |', '|\t設計\t|')
    sample['body'].write_text(body)
    result = run(sample)
    assert result.returncode == 0
    assert result.stdout.count('<!-- dispatch_id=') == 2
    for rid in IDS: assert f'<!-- dispatch_id={rid} -->' in result.stdout


def test_partial_and_outer_sections(sample):
    body = '## Intro\nkeep\n' + sample['body'].read_text() + '\n## After\nunchanged\n'
    sample['body'].write_text(body)
    (sample['state'] / (IDS[1] + '.state')).unlink()
    result = run(sample)
    assert result.returncode == 1
    assert result.stdout == expected(body).replace(f' <!-- dispatch_id={IDS[1]} -->', '')
    assert result.stderr.count('未補完:') == 1
