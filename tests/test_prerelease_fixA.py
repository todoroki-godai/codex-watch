"""Review c1 exact reproductions and identity / authority boundaries."""
import json
import pytest
from test_prerelease import case, evaluate, run_cli, rg, pre, TARGET, GOAL


def gate(c, body, record='', target=TARGET):
    return rg.run_gate(target, str(c['work']), c['state'], '', '',
        fetch_body=lambda target: body, goal_cut=GOAL,
        prerelease_record=record, kind_label='コード')


def test_ordinary_empty_evidence(case):
    c = case
    (c['state'] / 'ordinary.state').write_text(
        f'review_target={TARGET}\nrun_id=agent-1\nround=1\nhead_sha={"1"*40}\nauthority=ordinary\nprerelease_evidence={{}}\n')
    assert evaluate(c)['authority'] == 'project_prerelease'


def rows():
    return [rg.render_round_row(i, 'コード', f'2026-11-{10+i}', sha, 'Agent') +
        f' <!-- dispatch_id=dispatch-{i} -->' for i, sha in ((1, 'a'*40), (2, 'b'*40))]


def body_with(lines):
    return '\n'.join([rg.ROUND_SECTION_TITLE, rg.ROUND_ROW_HEADER, rg.ROUND_ROW_SEP, *lines])


def test_identical_duplicate(case):
    row = rows()[0]
    for path in case['state'].iterdir():
        path.unlink()
    assert pre.history(body_with([row, row]), case['state'], TARGET, strict=True) == 1


@pytest.mark.parametrize('approval', ['', '\n巡3の人間承認\n総上限: 3巡\n'])
@pytest.mark.parametrize('field', ['all', 'round', 'sha', 'time', 'kind'])
def test_conflicting_id(case, field, approval):
    case['git']('remote', 'set-url', 'origin', 'https://github.com/other/repo.git')
    first, second = rows()
    if field == 'all':
        second = second.replace('dispatch-2', 'dispatch-1')
    else:
        second = first.replace({'round': '| 1 |', 'sha': 'aaaaaaa', 'time': '2026-11-11', 'kind': 'コード'}[field],
                               {'round': '| 2 |', 'sha': 'bbbbbbb', 'time': '2026-11-12', 'kind': '設計'}[field])
    with pytest.raises(pre.ConflictingHistory, match='発注ID'):
        pre.history(body_with([first, second]) + approval, case['state'], TARGET, strict=True)


@pytest.mark.parametrize('approval,allowed', [('', False), ('\n巡3の人間承認\n', False),
    ('\n総上限: 3巡\n', False), ('\n巡3の人間承認\n総上限: 3巡\n', True)])
def test_malformed_history(case, approval, allowed):
    case['git']('remote', 'set-url', 'origin', 'https://github.com/other/repo.git')
    first, second = rows()
    body = body_with([first, second.replace('| 2 |', 'unreadable')]) + approval
    result = gate(case, body, target='issue:other/repo#1')
    expected = 3 if '巡3の人間承認' in approval else 1
    assert result['total_round'] == expected
    assert result['status'] == ('blocked' if expected == 3 and not allowed else 'pass')
    # The same malformed row must still invalidate the exception.
    with pytest.raises(ValueError):
        pre.history(body, case['state'], TARGET, strict=True)


def test_normal_human(case):
    (case['state'] / 'third.state').write_text(f'run_id=third\nreview_target={TARGET}\nround=3\nhead_sha={case["data"]["head_sha"]}\n')
    result = gate(case, body_with(rows()) + '\n巡3の人間承認\n総上限: 3巡\n')
    assert result['status'] == 'pass' and result['total_round'] == 3 and result['authority'] == 'human'


def test_saved_exception_cap(case):
    c = case
    (c['state'] / 'prior.state').write_text(f'review_target={TARGET}\nrun_id=agent-1\nround=1\nhead_sha={"1"*40}\n'
        'authority=project_prerelease\nprerelease_evidence=' +
        json.dumps({'record': dict(c['data'], total_cap=4)}) + '\n')
    with pytest.raises(ValueError, match='固定総上限'):
        evaluate(c)


def test_reservation_keeps_authority(case):
    result = run_cli(case)
    assert result.returncode == 0, result.stdout + result.stderr
    saved = rg.read_state_file(next(case['state'].glob('*.reservation')))
    assert saved['authority'] == 'project_prerelease'
