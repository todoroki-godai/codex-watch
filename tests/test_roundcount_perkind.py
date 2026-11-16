"""#37: human approval of the next, not yet dispatched, kind-specific round."""
import json
from functools import partial
from pathlib import Path

import pytest
from test_prerelease import case, rg, pre, TARGET, NOW, GOAL
from test_round_count_c import saved


@pytest.fixture
def repro(tmp_path, monkeypatch):
    data = json.loads((Path(__file__).parent / 'fixtures/roundcount-perkind.json').read_text())
    state = tmp_path / 'state'
    state.mkdir()
    for index, row in enumerate(data['states']):
        (state / f'{index}.state').write_text(''.join(f'{k}={v}\n' for k, v in row.items()))
    monkeypatch.setattr(rg, 'git_remote_repo', lambda work: ('min-sys', 'updater-index'))
    monkeypatch.setattr(rg, 'git_head_sha', lambda work: 'f' * 40)
    def gate(body=data['body'], kind='設計', record=''):
        return rg.run_gate(data['target'], str(tmp_path), state, '', '',
            fetch_body=lambda target: body, goal_cut=GOAL,
            kind_label=kind, prerelease_record=record)
    return data, state, gate


@pytest.mark.parametrize('record', ['', '2078-design-round4'])
def test_repro_design4(repro, monkeypatch, record):
    data, state, gate = repro
    def forbidden(*args, **kwargs):
        pytest.fail('Human approval must precede the prerelease exception')
    monkeypatch.setattr(pre, 'evaluate', forbidden)
    result = gate(record=record)
    assert (result['status'], result['total_round'], result['authority']) == ('pass', 4, 'human')
    assert result['record_target'] == data['target']
    assert result['prerelease_evidence'] == {}


@pytest.mark.parametrize('kind', ['設計', 'コード'])
@pytest.mark.parametrize('n', [3, 4, 5])
@pytest.mark.parametrize('approval,offset', [(False, 0), (True, -1), (True, 0), (True, 1)])
def test_pending_boundaries(repro, kind, n, approval, offset):
    data, state, gate = repro
    for path in state.iterdir(): path.unlink()
    for k, count in [(kind, n - 1), ('コード' if kind == '設計' else '設計', 2)]:
        for i in range(1, count + 1):
            saved(state, k + str(i), k, i, format(i + (k == '設計') * 5, 'x') * 40, data['target'])
    body = (f'巡{n}の人間承認\n' if approval else '') + f'総上限: {n + offset}'
    result = gate(body, kind)
    assert result['total_round'] == n
    assert result['status'] == ('pass' if approval and offset >= 0 else 'blocked')


def test_pending_kind(repro):
    _, _, gate = repro
    result = gate('巡3の人間承認\n総上限: 3', 'コード')
    assert (result['status'], result['total_round']) == ('pass', 3)


@pytest.mark.parametrize('kind', ['設計', 'コード'])
def test_sixth_round(repro, kind):
    data, state, gate = repro
    for path in state.iterdir(): path.unlink()
    for k, count in [(kind, 5), ('コード' if kind == '設計' else '設計', 2)]:
        for i in range(1, count + 1):
            saved(state, k + str(i), k, i, format(i + (k == '設計') * 5, 'x') * 40, data['target'])
    # N5 is already backed by saved evidence; cap6 cannot lift the hard ceiling.
    result = gate('巡5の人間承認\n総上限: 6', kind)
    assert (result['status'], result['total_round']) == ('blocked', 6)


def test_pending_not_reused(repro, monkeypatch):
    data, state, gate = repro
    saved(state, 'd4', '設計', 3, 'e'*40, data['target'])
    monkeypatch.setattr(rg, 'git_head_sha', lambda work: 'e' * 40)
    result = gate()
    assert (result['status'], result['total_round']) == ('blocked', 6)


def test_future_approval_not_completed(repro):
    _, _, gate = repro
    result = gate('巡5の人間承認\n総上限: 5')
    assert (result['status'], result['total_round']) == ('blocked', 6)


def test_exception_cap_increase_without_human(case, monkeypatch):
    """Real evaluate path: saved cap3 must reject a new exception's cap4."""
    monkeypatch.setattr(pre, 'evaluate', partial(pre.evaluate, registry=case['registry'], now=NOW))
    data = dict(case['data'], total_cap=4)
    for i in (1, 2, 3):
        saved(case['state'], f'prior-{i}', 'コード', i, str(i)*40)
    third = case['state'] / 'prior-3.state'
    third.write_text(third.read_text() + 'authority=project_prerelease\nprerelease_evidence=' +
                     json.dumps({'record': dict(data, total_cap=3)}) + '\n')
    row = rg.render_round_row(3, 'コード', '2026-11-12', '3'*40, 'Agent') + ' <!-- dispatch_id=prior-3 -->\n'
    # Existing fixture IDs are agent-1/2; retain them for strict history matching.
    for i in (1, 2):
        p = case['state'] / f'prior-{i}.state'
        p.write_text(p.read_text().replace(f'run_id=prior-{i}', f'run_id=agent-{i}'))
    body = case['body'](data).replace('## 公開前裁定', row + '\n## 公開前裁定')
    result = rg.run_gate(TARGET, str(case['work']), case['state'], '', '',
        fetch_body=lambda target: body, goal_cut=GOAL, kind_label='コード', prerelease_record='decision-1')
    assert result['total_round'] == 4
    assert result['status'] == 'blocked'
    assert '固定総上限の変更' in result['message']
    assert result['prerelease_evidence'] == {}
