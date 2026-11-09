"""Exercise the actual launcher's preflight; stop at the next stage, never launch a CLI."""
import os
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
                                env={**os.environ, 'PATH': f'{fake}:{os.environ["PATH"]}'},
                                text=True, capture_output=True, timeout=5)
        assert 'UNEXPECTED_CLI' not in result.stderr
        return result
    return run


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
def test_positive(check, body):
    r = check(body)
    assert r.returncode == 71 and r.stderr.strip() == 'NEXT_STAGE'


@pytest.mark.parametrize('fixture_id', [5, 7, 9])
def test_real_B_positive(check, fixture_id):
    body = (ROOT / f'tests/fixtures/receipt/B-{fixture_id}.md').read_text()
    r = check('直しの出所: なし\n' + body)
    assert r.returncode == 71 and r.stderr.strip() == 'NEXT_STAGE'


def test_accident_shape_is_known_limit_without_rule_2(check):
    r = check('直しの出所: なし（新規実装）\n新しい仕組みを足す\n'
              '## C. レビュー巡3の指摘を直す\n指摘を反映する。\n')
    assert r.returncode == 71  # Deliberate scope decision, not a negative-case success.


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
