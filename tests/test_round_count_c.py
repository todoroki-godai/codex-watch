"""C contract, from round-count-c design §2–5 (normal path first)."""
from pathlib import Path
import subprocess
import sys

import pytest
from test_prerelease import case, run_cli, rg, pre, TARGET, GOAL


def saved(folder, name, kind, n, head=None, target=TARGET):
    (folder / (name + '.state')).write_text(
        f'run_id={name}\nreview_target={target}\nkind_label={kind}\nround={n}\n'
        f'head_sha={head or name[0] * 40}\nstarted_at=1\n')


def design3(c):
    for p in c['state'].iterdir(): p.unlink()
    for i in (1, 2, 3): saved(c['state'], f'd{i}', '設計', i, str(i) * 40)
    return '巡3の人間承認\n総上限: 3\n'


def test_design3_code1(case, monkeypatch):
    body = design3(case)
    case['body_file'].write_text(body)
    monkeypatch.delenv('REVIEW_PRERELEASE_RECORD')
    result = run_cli(case)
    assert result.returncode == 0, result.stdout + result.stderr
    state = rg.read_state_file(next(case['state'].glob('0-fixture-*.state')))
    assert state['round'] == '1'
    assert '今回のレビュー: 巡1（種別: コード）' in open(state['effective_prompt']).read()
    assert '| 1 | コード |' in case['body_file'].read_text()


def gate(c, body, kind='コード', record=''):
    return rg.run_gate(TARGET, str(c['work']), c['state'], '', '',
        fetch_body=lambda t: body, goal_cut=GOAL, kind_label=kind, prerelease_record=record)


def test_boundary(case):
    assert gate(case, '')['status'] == 'blocked'  # two saved + pending = 3
    (case['state'] / 'prior-2.state').unlink()
    assert gate(case, '')['total_round'] == 2
    body = design3(case)
    assert gate(case, body, '設計')['status'] == 'blocked'
    assert gate(case, body)['total_round'] == 1


@pytest.mark.parametrize('candidate', ['コード', '設計', 'none', 'both'])
def test_attribution_deficit(case, candidate):
    for p in case['state'].iterdir(): p.unlink()
    for kind, count in [('コード', 2), ('設計', 3)]:
        for i in range(count): saved(case['state'], f'{kind}{i}', kind, i+1, str(i+1+(kind=='設計')*3)*40)
    for k in (['コード', '設計'] if candidate == 'both' else [candidate]):
        if k != 'none': saved(case['state'], k+'5', k, 5, ('1' if k=='コード' else '4')*40)
    result = gate(case, '巡5の人間承認\n総上限: 5')
    assert (result['status'], result['total_round']) == ('blocked', 6)


@pytest.mark.parametrize('invalid', ['none', 'both', '0', '３', '', '-1', 'head', 'other'])
def test_invalid(case, invalid):
    body = design3(case)
    p = case['state'] / 'd3.state'
    if invalid == 'none': p.unlink()
    elif invalid == 'both': saved(case['state'], 'c3', 'コード', 3, 'a'*40)
    elif invalid == 'head': p.write_text(p.read_text().replace('head_sha='+ '3'*40, 'head_sha='))
    elif invalid == 'other': p.write_text(p.read_text().replace(TARGET, 'issue:o/r#99'))
    else: p.write_text(p.read_text().replace('round=3', 'round='+invalid))
    result = gate(case, body, record='decision-1')
    expected = 5 if invalid == 'both' else (3 if invalid in ('none', 'head', 'other') else 4)
    assert result['total_round'] == expected
    assert result['status'] == ('blocked' if expected > 3 else 'pass')


def test_predecessor_and_past_head(case):
    for p in case['state'].iterdir(): p.unlink()
    pred = 'pr:min-sys/updater-index#2'
    saved(case['state'], 'a', 'コード', 1, 'a'*40, pred)
    saved(case['state'], 'b', 'コード', 2, 'b'*40, pred)
    saved(case['state'], 'd', '設計', 1, 'd'*40, pred)
    t = rg.parse_target(TARGET)
    fetch = lambda t: ''
    assert rg.target_total_rounds(t, case['state'], fetch, [rg.parse_target(pred)], 'c'*40, kind_label='コード') == 3
    saved(case['state'], 'c', 'コード', 3, 'c'*40)
    saved(case['state'], 'e', 'コード', 4, 'e'*40)
    assert rg.target_total_rounds(t, case['state'], fetch, [], 'c'*40, kind_label='コード') == 2


def test_history_heads(case):
    body = case['body']().replace('## 巡の履歴', '## 巡の履歴\n説明文\n')
    assert pre.history(body, case['state'], TARGET, strict=True, kind_label='コード') == 2
    saved(case['state'], 'duplicate', 'コード', 2, '2'*40)
    saved(case['state'], 'design', '設計', 1, 'a'*40)
    assert pre.history(body, case['state'], TARGET, strict=True, kind_label='コード', pending_head='2'*40) == 2
    assert pre.history(body, case['state'], TARGET, strict=True, kind_label='コード', pending_head='f'*40) == 3


@pytest.mark.parametrize('line', ['|---| <!-- dispatch_id=forged -->', 'text <!-- dispatch_id=forged -->', '| bad |', '| 1 | コード | bad |', '| 1 | コード | date | aaaaaaa | Agent | 計測中 | - | <!-- dispatch_id=x --> <!-- dispatch_id=y -->'])
def test_history_invalid(case, line):
    body = case['body']().replace('## 巡の履歴', '## 巡の履歴\n'+line)
    with pytest.raises(ValueError): pre.history(body, case['state'], TARGET, strict=True, kind_label='コード')


def test_cli_predecessor(case, monkeypatch):
    for p in case['state'].iterdir(): p.unlink()
    pred = 'pr:min-sys/updater-index#2'
    for i in (1, 2): saved(case['state'], str(i), 'コード', i, str(i)*40, pred)
    # N2 belongs to the predecessor and is backed by its completed HEADs.
    case['body_file'].write_text('巡2の人間承認\n総上限: 5\n')
    monkeypatch.setenv('REVIEW_PREDECESSOR', pred)
    monkeypatch.delenv('REVIEW_PRERELEASE_RECORD')
    # Fake gh shares one body for both targets; keep root free of approval and
    # use a code HEAD already dispatched at root as N3 with same-kind support.
    saved(case['state'], 'root', 'コード', 3, case['data']['head_sha'])
    case['body_file'].write_text('巡3の人間承認\n総上限: 5\n')
    # Return different bodies at the read boundary.
    gh = case['tmp'] / 'fakebin/gh'
    text = gh.read_text().replace("else:\n    print(Path(os.environ['BODY']).read_text())", "else:\n    print('' if len(a)>2 and a[2]=='2' else Path(os.environ['BODY']).read_text())")
    gh.write_text(text)
    result = run_cli(case)
    assert result.returncode == 0, result.stdout + result.stderr
    state_file = next(case['state'].glob('0-fixture-*.state'))
    state = rg.read_state_file(state_file)
    assert state['round'] == '3'
    prompt = Path(state['effective_prompt']).read_text()
    assert '今回のレビュー: 巡3（種別: コード）' in prompt
    assert '`## 過剰の点検`' in prompt
    assert 'この巡の直しで足した分' in prompt

    report = Path(state['report'])
    header = f"実装着手可\nread_sha={state['head_sha']}\ncontent_hash={state['content_hash']}\n"
    for body, expected in (
        ('## 過剰の点検\nなし\n', 0),
        ('本文\n', 4),
        ('## 過剰の点検\n \t\n', 4),
        ('## 過剰の点検\n\n', 4),
    ):
        report.write_text(header + body + '=== REVIEW DONE ===\n')
        receipt = subprocess.run(
            [sys.executable, str(case['package'] / 'lib/round_gate.py'),
             'receipt', '--state-file', str(state_file), '--report', str(report)],
            capture_output=True, text=True, timeout=15,
        )
        assert receipt.returncode == expected, (body, receipt.stdout, receipt.stderr)
        assert ('受領可' if expected == 0 else '## 過剰の点検') in receipt.stdout


@pytest.mark.parametrize('mode', ['full', 'short', 'ambiguous', 'conflict', 'reservation'])
def test_history_resolution(case, mode):
    body = case['body']()
    row = rg.render_round_row(3, 'コード', '2026-11-12', 'a'*40 if mode=='full' else '1'*7, 'Agent') + ' <!-- dispatch_id=body-only -->\n'
    if mode == 'ambiguous': saved(case['state'], 'ambiguous', 'コード', 1, '1'*7+'a'*33)
    if mode == 'conflict':
        row = rg.render_round_row(1, '設計', '2026-11-12', '1'*7, 'Agent') + ' <!-- dispatch_id=agent-1 -->\n'
    if mode == 'reservation':
        import json
        (case['state'] / 'agent-1.reservation').write_text(f'run_id=agent-1\nreview_target={TARGET}\nprerelease_evidence='+json.dumps({'record':dict(kind='コード', head_sha='1'*40)})+'\n')
    body = body.replace('## 公開前裁定', row+'\n## 公開前裁定')
    if mode in ('ambiguous', 'conflict'):
        with pytest.raises(ValueError): pre.history(body, case['state'], TARGET, strict=True, kind_label='コード')
    else:
        assert pre.history(body, case['state'], TARGET, strict=True, kind_label='コード') == (3 if mode=='full' else 2)


def test_predecessor_approval_cannot_borrow_descendants(case):
    for p in case['state'].iterdir(): p.unlink()
    pred = rg.parse_target('pr:min-sys/updater-index#2')
    saved(case['state'], 'pred', 'コード', 3, 'a'*40, pred.key())
    for i in (1, 2, 3): saved(case['state'], str(i), 'コード', i, str(i)*40)
    assert rg.target_total_rounds(rg.parse_target(TARGET), case['state'],
            lambda t: '巡3の人間承認' if t == pred else '', [pred], 'f'*40, kind_label='コード') == 7


def test_all_approvals_validated(case):
    body = design3(case)
    # N3 is supported but N2 has no attribution: restart with mixed count.
    p = case['state'] / 'd2.state'
    p.write_text(p.read_text().replace('round=2', 'round=1'))
    result = gate(case, body+'\n巡2の人間承認')
    assert (result['status'], result['total_round']) == ('blocked', 4)


def test_design_predecessor_filter(case):
    for p in case['state'].iterdir(): p.unlink()
    pred = rg.parse_target('pr:min-sys/updater-index#2')
    saved(case['state'], 'd', '設計', 1, 'a'*40, pred.key())
    for i in (1, 2): saved(case['state'], str(i), 'コード', i, str(i)*40, pred.key())
    assert rg.target_total_rounds(rg.parse_target(TARGET), case['state'], lambda t:'', [pred], 'f'*40, kind_label='設計') == 2


@pytest.mark.parametrize('n,count,candidate,extra', [
    (3, 2, False, 0), (4, 3, True, 0), (3, 2, True, 0),
    (4, 3, True, 1), (4, 3, True, 0), (5, 4, True, 0)])
def test_fallback_cases(case, n, count, candidate, extra):
    # The six previously blocked shapes: missing attribution or N-1 support.
    for p in case['state'].iterdir(): p.unlink()
    for i in range(count):
        saved(case['state'], 'd'+str(i), '設計', n if candidate and i == 0 else 1, str(i+1)*40)
    if extra: saved(case['state'], 'c', 'コード', 1, 'a'*40)
    body = f'巡{n}の人間承認\n総上限: 5'
    result = gate(case, body)
    total = max(count+extra+1, n)
    assert (result['status'], result['total_round']) == ('pass' if total <= 3 else 'blocked', total)


def test_fallback_cli(case, monkeypatch):
    body = design3(case)
    p = case['state'] / 'd3.state'
    p.write_text(p.read_text().replace('round=3', 'round=1'))
    case['body_file'].write_text(body.replace('総上限: 3', '総上限: 5'))
    monkeypatch.delenv('REVIEW_PRERELEASE_RECORD')
    result = run_cli(case)
    assert result.returncode == 4, result.stdout + result.stderr
    assert not list(case['state'].glob('0-fixture-*.state'))
    case['body_file'].write_text(case['body_file'].read_text() + '\n裁定: 縮小')
    result = run_cli(case)
    assert result.returncode == 0, result.stdout + result.stderr
    state = rg.read_state_file(next(case['state'].glob('0-fixture-*.state')))
    assert state['round'] == '4'
    assert '今回のレビュー: 巡4（種別: コード）' in open(state['effective_prompt']).read()
    assert '| 4 | コード |' in case['body_file'].read_text()


@pytest.mark.parametrize('mode', ['kind', 'read'])
def test_trust_boundary(case, monkeypatch, mode):
    body = design3(case)
    (case['state'] / 'd1.state').write_text((case['state'] / 'd1.state').read_text().replace('round=1', 'round='))
    if mode == 'kind':
        saved(case['state'], 'z', 'invalid', 1, 'e'*40)
        with pytest.raises((ValueError, rg.Indeterminate)): gate(case, body)
    else:
        original = rg.read_state_file
        def read(path, *, strict=False):
            if path.name == 'd3.state': raise OSError('fixture unreadable')
            return original(path, strict=strict)
        monkeypatch.setattr(rg, 'read_state_file', read)
        with pytest.raises(OSError): gate(case, body)


@pytest.mark.parametrize('prose', [False, True])
def test_legacy_prerelease(case, monkeypatch, prose):
    # N2 is unsupported; old history counts dispatches and rejects prose.
    from functools import partial
    from test_prerelease import NOW
    monkeypatch.setattr(pre, 'evaluate', partial(pre.evaluate, registry=case['registry'], now=NOW))
    p = case['state'] / 'prior-2.state'
    p.write_text(p.read_text().replace('round=2', 'round=1'))
    body = '巡2の人間承認\n' + case['body']()
    if prose: body = body.replace('## 巡の履歴', '## 巡の履歴\n説明文')
    result = gate(case, body, record='decision-1')
    assert result['total_round'] == 3
    assert result['status'] == ('blocked' if prose else 'pass'), result


def test_pending_cannot_support_approval(case):
    for p in case['state'].iterdir(): p.unlink()
    for i in (1, 2): saved(case['state'], 'c'+str(i), 'コード', i, str(i)*40)
    saved(case['state'], 'candidate', 'コード', 3, '1'*40)
    saved(case['state'], 'd', '設計', 1, 'a'*40)
    result = gate(case, '巡3の人間承認\n総上限: 3')
    assert (result['status'], result['total_round']) == ('blocked', 4)
