"""A2 contract: ordinary counting is bdb4d62; history guards only A."""
import pytest
from test_prerelease import case, evaluate, pre, rg, TARGET
from test_prerelease_fixA import gate, body_with


def test_ordinary_parallel_round2(case):
    """D1: two reviewers, seven seconds apart, one completed round."""
    lines = []
    for index, (when, reviewer) in enumerate([
        ('2026-11-06 18:32:39', 'm1-review-spec'),
        ('2026-11-06 18:32:46', 'm1-review-perf'),
    ], 1):
        (case['state'] / f'prior-{index}.state').write_text(
            f'run_id=agent-{index}\nreview_target={TARGET}\nhead_sha={"c03820d" + "0" * 33}\n'
            f'round=1\nstarted_at={index}\nstarted_at_human={when}\nreviewer={reviewer}\n')
        lines.append(rg.render_round_row(1, 'コード', when, 'c03820d', reviewer))
    result = gate(case, body_with(lines))
    assert result['status'] == 'pass' and result['total_round'] == 2
    assert result['authority'] == 'ordinary' and result['history_round'] is None


def test_ordinary_prose_round2(case):
    """D2: prose inside the history section is ordinary valid input."""
    (case['state'] / 'prior-2.state').unlink()
    body = body_with([rg.render_round_row(1, 'コード', '2026-11-12', '1111111', 'Agent'),
                      '巡1の受領: 指摘を確認し、直し済み。'])
    result = gate(case, body)
    assert result['status'] == 'pass' and result['total_round'] == 2
    assert result['history_round'] is None


@pytest.mark.parametrize('record', ['', 'decision-1'])
@pytest.mark.parametrize('bad', ['prose', 'conflict', 'malformed'])
def test_human_approval_with_bad_history(case, monkeypatch, record, bad):
    body = case['body'](suffix='\n巡3の人間承認\n総上限: 3巡\n')
    if bad == 'prose':
        body = body.replace('## 巡の履歴', '## 巡の履歴\n受領の説明文')
    elif bad == 'conflict':
        body = body.replace('dispatch_id=agent-2', 'dispatch_id=agent-1')
    else:
        body = body.replace('| 2 |', 'unreadable')
    def forbidden(*args, **kwargs):
        pytest.fail('Valid ordinary approval must not parse exception history')
    monkeypatch.setattr(pre, 'history', forbidden)
    monkeypatch.setattr(pre, 'evaluate', forbidden)
    result = gate(case, body, record)
    assert result['status'] == 'pass' and result['total_round'] == 3
    assert result['authority'] == 'human' and result['history_round'] is None


@pytest.mark.parametrize('bad', ['prose', 'conflict', 'malformed', 'extra-dispatch'])
def test_exception_bad_history_falls_back(case, monkeypatch, bad):
    body = case['body']()
    if bad == 'prose':
        body = body.replace('## 巡の履歴', '## 巡の履歴\n説明文')
    elif bad == 'conflict':
        body = body.replace('dispatch_id=agent-2', 'dispatch_id=agent-1')
    elif bad == 'malformed':
        body = body.replace('| 2 |', 'unreadable')
    else:
        body = body.replace('## 公開前裁定', rg.render_round_row(
            3, 'コード', '2026-11-12', '3333333', 'Agent') +
            ' <!-- dispatch_id=extra -->\n\n## 公開前裁定')
    original = pre.evaluate
    monkeypatch.setattr(pre, 'evaluate', lambda *args, **kwargs:
                        original(*args, **kwargs, registry=case['registry']))
    result = gate(case, body, 'decision-1')
    assert result['status'] == 'blocked' and result['total_round'] == 3
    assert result['prerelease_evidence'] == {} and result['history_round'] is None
    assert '公開前特例不成立' in result['message']


def test_exception_extra_dispatch(case):
    body = case['body']().replace('## 公開前裁定', rg.render_round_row(
        3, 'コード', '2026-11-12', '3333333', 'Agent') +
        ' <!-- dispatch_id=extra -->\n\n## 公開前裁定')
    with pytest.raises(ValueError, match='正本履歴と判定巡'):
        evaluate(case, body=body)
