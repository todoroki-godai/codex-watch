"""Exercise the actual launcher's preflight; stop at the next stage, never launch a CLI."""
import os
import json
import hashlib
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
NEXT = '# shellcheck source=SCRIPTDIR/_codex_common.sh'
REVIEW = ('直しの出所: レビュー巡1\n受領①累計: 起点abc・1件\n'
          '受領②件数: M1=10件中1件・2026-11-09\n受領③7段: ㋑\n')


@pytest.fixture
def check(tmp_path):
    # Retain the full launcher; sentinel intercepts the first subsequent stage.
    source = (ROOT / 'bin/codex-impl').read_text()
    assert source.count(NEXT) == 1
    launcher = tmp_path / 'codex-impl'
    prompt = tmp_path / 'prompt with spaces.md'
    fake = tmp_path / 'bin'
    fake.mkdir()
    home = tmp_path / 'home'
    home.mkdir()
    for name in ('codex', 'aws', 'git', 'gh', 'nohup'):
        p = fake / name
        p.write_text('#!/bin/sh\necho UNEXPECTED_CLI >&2\nexit 99\n')
        p.chmod(0o755)

    def run(body, *, mutation=None):
        text = source
        if mutation:
            old, new = mutation
            assert text.count(old) == 1, 'mutation must apply exactly once'
            text = text.replace(old, new)
        text = text.replace(NEXT, 'echo NEXT_STAGE >&2\nexit 71\n' + NEXT)
        launcher.write_text(text)
        prompt.write_bytes(body.encode() if isinstance(body, str) else body)
        result = subprocess.run(['bash', str(launcher), str(tmp_path), str(prompt)],
                                env={**os.environ, 'HOME': str(home), 'PATH': f'{fake}:{os.environ["PATH"]}'},
                                text=True, capture_output=True, timeout=5)
        assert 'UNEXPECTED_CLI' not in result.stderr
        return result
    return run


def assert_stop_snapshot(tmp_path, body, row, stderr=''):
    raw = body.encode() if isinstance(body, str) else body
    digest = hashlib.sha256(raw).hexdigest()
    snapshot = Path(row['snapshot'])
    assert snapshot.is_file(), stderr
    assert snapshot.read_bytes() == raw
    assert row['sha256'] == digest
    assert snapshot.parent == tmp_path / 'home/.codex-watch/receipt-gate-stops'
    assert snapshot.name.endswith(f'-{digest[:12]}.md')
    assert snapshot.name.startswith(row['time'][:10].replace('-', '') + 'T')
    assert snapshot.stat().st_mode & 0o777 == 0o600


# Negative cases: source and receipt contract.
@pytest.mark.parametrize('body', [
    'new implementation',
    '直しの出所: 巡3の指摘\n',
    ' 直しの出所: なし\n',
    '直しの出所：なし\n',
    '直しの出所: \t\n',
    '直しの出所: レビュー巡1\n',
    REVIEW.replace('受領②件数: M1=10件中1件・2026-11-09\n', ''),
    REVIEW.replace('受領①累計: 起点abc・1件', '受領①累計: \t'),
    REVIEW.replace('受領③7段: ㋑', '受領③7段:'),
])
def test_negative(check, body):
    r = check(body)
    assert r.returncode == 2
    assert '拒否:' in r.stderr and 'NEXT_STAGE' not in r.stderr
    for phrase in ('review-receipt.md', '①', '②', '③', '直しの出所:',
                   '受領①累計:', '受領②件数:', '受領③7段:', '自己申告', '書き忘れ'):
        assert phrase in r.stderr


@pytest.mark.parametrize('body', ['直しの出所: なし\n', REVIEW,
                                  REVIEW.replace('\n', '\r\n')])
def test_positive(check, body, tmp_path):
    r = check(body)
    assert r.returncode == 71 and r.stderr.strip() == 'NEXT_STAGE'
    assert not (tmp_path / 'home/.codex-watch').exists()


@pytest.mark.parametrize('fixture_id', [5, 7, 9])
def test_real_B_positive(check, fixture_id, tmp_path):
    body = (ROOT / f'tests/fixtures/receipt/B-{fixture_id}.md').read_text()
    r = check('直しの出所: なし\n' + body)
    assert r.returncode == 71 and r.stderr.strip() == 'NEXT_STAGE'
    assert not (tmp_path / 'home/.codex-watch').exists()


def test_accident_shape_is_rejected(check, tmp_path):
    body = ('直しの出所: なし（新規実装）\n新しい仕組みを足す\n'
            '## C. レビュー巡3の指摘を直す\n指摘を反映する。\n')
    r = check(body)
    assert r.returncode == 2 and 'NEXT_STAGE' not in r.stderr
    row = json.loads((tmp_path / 'home/.codex-watch/receipt-gate-stops.log').read_text())
    assert_stop_snapshot(tmp_path, body, row, r.stderr)


@pytest.mark.parametrize('tail,word', [
    ('## C. レビュー巡3の指摘を直す', '巡3'),
    ('指摘を反映', '指摘を反映'),
    ('\n' * 100 + '巡9', '巡9'),
])
def test_word_negative_and_private_log(check, tail, word, tmp_path):
    body = '直しの出所: なし\n本文の写しの目印\n' + tail
    r = check(body)
    assert r.returncode == 2 and 'NEXT_STAGE' not in r.stderr
    assert '出所を「レビュー…」に直し、受領の3行を書く' in r.stderr
    assert '語で見ているだけ・言い換えは通る' in r.stderr
    log = tmp_path / 'home/.codex-watch/receipt-gate-stops.log'
    rows = log.read_text().splitlines()
    assert len(rows) == 1 and '本文の写しの目印' not in rows[0]
    row = json.loads(rows[0])
    assert set(row) == {'time', 'prompt', 'match', 'snapshot', 'sha256'}
    assert row['time'] and row['match'] == word
    assert row['prompt'] == str(tmp_path / 'prompt with spaces.md')
    assert_stop_snapshot(tmp_path, body, row, r.stderr)
    # Reusing and correcting the same source path must preserve the stopped body.
    check('直しの出所: なし\n修正済み')
    assert Path(row['snapshot']).read_bytes() == body.encode()
    check('直しの出所: なし\n' + tail)
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(rows) == 2 and rows[0]['snapshot'] != rows[1]['snapshot']
    assert_stop_snapshot(tmp_path, '直しの出所: なし\n' + tail, rows[1])


def test_only_body_after_source_is_scanned(check, tmp_path):
    r = check('巡3 指摘を反映\n直しの出所: なし（巡3）\n新規実装 [Must]\n')
    assert r.returncode == 71
    assert not (tmp_path / 'home/.codex-watch/receipt-gate-stops.log').exists()


# Independent input attacks: conflicting duplicates, Unicode blank values, NUL.
@pytest.mark.parametrize('body', [
    '直しの出所: なし\n' + REVIEW,
    REVIEW + '直しの出所: なし\n',
    REVIEW + '受領②件数: \n',
    REVIEW.replace('受領②件数: M1=10件中1件・2026-11-09', '受領②件数: \u3000\u00a0'),
    '直しの出所: \u3000\n',
    REVIEW + '\x00',
    b'\xff',
])
def test_independent_input_attacks(check, body):
    r = check(body)
    assert r.returncode == 2 and 'NEXT_STAGE' not in r.stderr


# Killed mutants: a unique marker is executed inside the changed branch.
# Exit 71 proves the original exit-2 oracle would fail, rather than a syntax crash.
@pytest.mark.parametrize('body,old,new', [
    ('直しの出所: なし\n## C. レビュー巡3の指摘を直す\n',
     "reason = '出所を「レビュー…」に直し、受領の3行を書く必要があります。語で見ているだけ・言い換えは通る。'",
     "print('MUTANT_M2', file=sys.stderr); reason = ''"),
    ('直しの出所: 巡3の指摘\n',
     "reason = '直しの出所は「なし」か「レビュー」で始めてください。'",
     "print('MUTANT_M1', file=sys.stderr); reason = ''"),
    ('no header', "reason = '直しの出所: は行頭に、空でない値つきで1行だけ必要です。'",
     "print('MUTANT_SOURCE', file=sys.stderr); reason = ''"),
    ('直しの出所: レビュー巡1\n',
     "reason = 'レビューの直しには、空でない受領の3行がそれぞれ1行必要です。'",
     "print('MUTANT_RECEIPTS', file=sys.stderr); reason = ''"),
    (REVIEW.replace('受領③7段: ㋑', '受領③7段: \u3000'),
     "reason = 'レビューの直しには、空でない受領の3行がそれぞれ1行必要です。'",
     "print('MUTANT_BLANK', file=sys.stderr); reason = ''"),
])
def test_mutations_hit_and_killed(check, body, old, new):
    baseline = check(body)
    assert baseline.returncode == 2
    mutant = check(body, mutation=(old, new))
    assert mutant.returncode == 71
    assert 'MUTANT_' in mutant.stderr and 'NEXT_STAGE' in mutant.stderr
    assert mutant.returncode != baseline.returncode


@pytest.mark.parametrize('body', [
    '直しの出所: なし\r\n直しの出所: レビュー巡3\r\n',
    '直しの出所: なし\u2028## C. レビュー巡3の指摘を直す',
])
def test_independent_line_boundary_attacks(check, body):
    r = check(body)
    assert r.returncode == 2 and 'NEXT_STAGE' not in r.stderr


def test_log_failure_stops_launch(check, tmp_path):
    (tmp_path / 'home/.codex-watch').write_text('not a directory')
    r = check('直しの出所: なし\n指摘を反映')
    assert r.returncode == 2 and 'NEXT_STAGE' not in r.stderr


@pytest.mark.parametrize('program', ['#!/bin/sh\nexit 127\n',
                                    '#!/bin/sh\necho unexpected-exception >&2\nexit 1\n'])
def test_python_failure_stops_launch(check, tmp_path, program):
    python = tmp_path / 'bin/python3'
    python.write_text(program)
    python.chmod(0o755)
    r = check('直しの出所: なし\n')
    assert r.returncode != 0 and 'NEXT_STAGE' not in r.stderr


@pytest.mark.parametrize('body', ['直しの出所: なし\r\n指摘を反映\r\n',
                                  '直しの出所: なし\n指摘を反映\n'])
def test_snapshot_preserves_bytes(check, tmp_path, body):
    r = check(body)
    assert r.returncode == 2 and 'NEXT_STAGE' not in r.stderr
    row = json.loads((tmp_path / 'home/.codex-watch/receipt-gate-stops.log').read_text())
    assert_stop_snapshot(tmp_path, body, row, r.stderr)


@pytest.mark.parametrize('failure', ['directory', 'write'])
def test_snapshot_failure_stops_launch(check, tmp_path, failure):
    folder = tmp_path / 'home/.codex-watch'
    folder.mkdir()
    if failure == 'directory':
        (folder / 'receipt-gate-stops').write_text('not a directory')
        r = check('直しの出所: なし\n指摘を反映')
    else:
        # Deterministic write failure, including when tests run as root.
        r = check('直しの出所: なし\n指摘を反映', mutation=(
            'stream.write(prompt_bytes)', "raise OSError('injected snapshot write failure')"))
    assert r.returncode == 2 and 'NEXT_STAGE' not in r.stderr
    assert '写しの保存' in r.stderr
    assert not (folder / 'receipt-gate-stops.log').exists()


def test_snapshot_mutation_hit_and_killed(check, tmp_path):
    body = '直しの出所: なし\n指摘を反映'
    old = """with os.fdopen(os.open(snapshot, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
                stream.write(prompt_bytes)"""
    mutant = check(body, mutation=(old, "print('MUTANT_NO_SNAPSHOT', file=sys.stderr)"))
    assert mutant.returncode == 2 and 'MUTANT_NO_SNAPSHOT' in mutant.stderr
    row = json.loads((tmp_path / 'home/.codex-watch/receipt-gate-stops.log').read_text())
    with pytest.raises(AssertionError, match='MUTANT_NO_SNAPSHOT'):
        assert_stop_snapshot(tmp_path, body, row, mutant.stderr)
