"""Receipt evidence is explicit, per dispatch, and never logged verbatim."""
import json
from pathlib import Path
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import routing_record as rr
import routing_warn as rw
from test_routing_record import case, build, PARTS
from round_gate import EMPTY_SHA256, check_receipt

TARGET = 'issue:org/repo#1'
SHA = 'a' * 40
TREE = 'b' * 64
ROUTE = 'c' * 64


def evidence(case, tags=('alpha', 'beta')):
    body = case[2]
    receipts = []
    for rid, tag in zip(('first', 'second'), tags):
        report = case[1] / (rid + '.report')
        report.write_text(f'実装着手可\nread_sha={SHA}\ncontent_hash={TREE}\n')
        (case[1] / (rid + '.state')).write_text(
            f'run_id={rid}\nreview_target={TARGET}\nround=1\nkind_label=設計\n'
            f'started_at_human=date\nhead_sha={SHA}\nreviewer={rid}\n'
            f'content_hash={TREE}\nroute_content_hash={ROUTE}\nreport={report}\n')
        body += f'| 1 | 設計 | date | {SHA[:7]} | {rid} | 1 | family | <!-- dispatch_id={rid} -->\n'
        receipts.append(dict(dispatch_id=rid, status='received', finding_family_tags=[tag], route_content_hash=ROUTE))
    return body, receipts


def body_with(body, receipts):
    return body + ''.join('routing-receipt: ' + json.dumps(r) + '\n' for r in receipts)


def get(case, body, receipts):
    return rr.history(body_with(body, receipts), case[1], TARGET, 'next')


def test_received_all_same_hashes(case):
    body, receipts = evidence(case)
    assert get(case, body, receipts) == [dict(event_id='first', status='received', target_sha=SHA,
        family_tags=['family'], finding_family_tags=['alpha', 'beta'], content_hash=ROUTE)]
    receipts[0]['finding_family_tags'] = ['none']
    assert get(case, body, receipts)[0]['finding_family_tags'] == ['beta', 'none']
    # One reviewer is also a complete round.
    (case[1]/'second.state').unlink()
    body = '\n'.join(l for l in body.splitlines() if 'dispatch_id=second' not in l)+'\n'
    assert get(case, body, receipts[:1])[0]['status'] == 'received'


@pytest.mark.parametrize('mode', ['missing', 'duplicate', 'other'])
def test_same_hash_ids_required(case, mode):
    body, receipts = evidence(case)
    if mode == 'missing': receipts.pop()
    if mode == 'duplicate': receipts[1]['dispatch_id'] = 'first'
    if mode == 'other': receipts[1]['dispatch_id'] = 'unrelated'
    assert all(e.get('status') != 'received' for e in get(case, body, receipts))


@pytest.mark.parametrize('mode', ['absent', 'empty', 'malformed', 'sha', 'tree', 'empty_hash', 'old'])
def test_report_rejected(case, mode):
    body, receipts = evidence(case)
    report = case[1]/'second.report'
    if mode == 'absent': report.unlink()
    if mode == 'empty': report.write_text('')
    if mode == 'malformed': report.write_text('可\nMARKER_TWO\nMARKER_THREE\n')
    if mode == 'sha': report.write_text(f'実装着手可\nread_sha={"d"*40}\ncontent_hash={TREE}\n')
    if mode == 'tree': report.write_text(f'実装着手可\nread_sha={SHA}\ncontent_hash={"d"*64}\n')
    if mode == 'empty_hash': report.write_text(f'実装着手可\nread_sha={SHA}\ncontent_hash={EMPTY_SHA256}\n')
    if mode == 'old':
        p=case[1]/'second.state'; p.write_text(p.read_text().replace(f'content_hash={TREE}\n',''))
    assert all(e.get('status') != 'received' for e in get(case, body, receipts))


@pytest.mark.parametrize('mode', ['tags_missing', 'tags_empty', 'tags_bad', 'hash_missing', 'hash_bad', 'hash_mismatch', 'state_missing', 'state_tree', 'different_sha', 'different_route'])
def test_incomplete_receipt(case, mode):
    body, receipts = evidence(case)
    r=receipts[1]
    if mode == 'tags_missing': r.pop('finding_family_tags')
    if mode == 'tags_empty': r['finding_family_tags']=[]
    if mode == 'tags_bad': r['finding_family_tags']=[1]
    if mode == 'hash_missing': r.pop('route_content_hash')
    if mode == 'hash_bad': r['route_content_hash']='bad'
    if mode == 'hash_mismatch': r['route_content_hash']='d'*64
    p=case[1]/'second.state'
    if mode == 'state_missing': p.write_text(p.read_text().replace(f'route_content_hash={ROUTE}\n',''))
    if mode == 'state_tree':
        p.write_text(p.read_text().replace(f'route_content_hash={ROUTE}',f'route_content_hash={TREE}'))
        r['route_content_hash']=TREE
    if mode == 'different_sha':
        p.write_text(p.read_text().replace(SHA,'d'*40)); body=body.replace(f'| {SHA[:7]} | second',f'| {"d"*7} | second')
        q=case[1]/'second.report'; q.write_text(q.read_text().replace(SHA,'d'*40))
    if mode == 'different_route':
        p.write_text(p.read_text().replace(ROUTE,'d'*64)); r['route_content_hash']='d'*64
    events=get(case, body, receipts)
    # state_tree describes a legitimate different recipe value, so matching evidence is accepted
    # only if all reviewers agree (they do not here).
    assert all(e.get('status') != 'received' for e in events)
    if mode.startswith('tags_'): assert 'finding_family_tags' not in events[-1]


@pytest.mark.parametrize('raw', ['{broken', '{"dispatch_id":"first","dispatch_id":"second"}', '[]', 'null'])
def test_invalid_receipt_json(case, raw):
    body, receipts=evidence(case)
    events=rr.history(body_with(body,receipts[:1])+'routing-receipt: '+raw+'\n',case[1],TARGET,'next')
    assert all(e.get('status') != 'received' for e in events)


def test_receipt_failure_is_fixed_and_private(case, monkeypatch, capsys):
    body, receipts=evidence(case)
    (case[1]/'second.report').write_text('可\nMARKER_TWO\nMARKER_THREE\n')
    reason=check_receipt(SHA,TREE,(case[1]/'second.report').read_text()).reason
    assert 'MARKER_TWO' in reason and 'MARKER_THREE' in reason
    monkeypatch.setattr(rr,'gh_fetch_body',lambda _: body_with(body,receipts))
    monkeypatch.setenv('CODEX_REVIEW_ADAPTER',str(PARTS/'adapter.py'))
    monkeypatch.delenv('REVIEW_GATE_RECORD',raising=False)
    before={p.name:p.read_bytes() for p in case[1].glob('*.state')}
    prompt=case[1]/'prompt'; prompt.write_text('')
    with rr.record_path(True) as record:
        rw.observe(str(case[1]),'next',TARGET,'設計',str(case[0]),str(prompt),record)
    row=json.loads((case[1]/'routing-warn.jsonl').read_text())
    assert '受領照合失敗' in row['reasons']
    output=capsys.readouterr()
    private=output.err+(case[1]/'routing-warn.jsonl').read_text()+''.join(p.read_text() for p in case[1].glob('*.state'))
    assert 'MARKER_TWO' not in private and 'MARKER_THREE' not in private
    assert before=={p.name:p.read_bytes() for p in case[1].glob('*.state')}


@pytest.mark.parametrize('mode', ['ok', 'write', 'timeout', 'external', 'invalid'])
def test_dispatch_hash_output(case, monkeypatch, capsys, mode):
    monkeypatch.delenv('REVIEW_GATE_RECORD', raising=False)
    monkeypatch.setattr(rr, 'generate', lambda *a: ({'current': {'content_hash': ROUTE if mode != 'invalid' else 'invalid'}}, []))
    monkeypatch.setattr(rw, 'evaluate', lambda *a: ('pass', None, ['全段通過']))
    prompt=case[1]/'prompt'; prompt.write_text('')
    if mode == 'external': monkeypatch.setenv('REVIEW_GATE_RECORD', '/not/read')
    if mode in ('write', 'timeout'):
        def fail(*args):
            if mode == 'timeout':
                import subprocess
                raise subprocess.TimeoutExpired('test', 0)
            raise OSError('write')
        monkeypatch.setattr(rr, 'write_record', fail)
    with rr.record_path(True) as record:
        rw.observe(str(case[1]),'next',TARGET,'設計',str(case[0]),str(prompt),record)
    assert capsys.readouterr().out == (ROUTE+'\n' if mode == 'ok' else '')


def test_non_json_constant_and_status(case):
    body, receipts = evidence(case)
    raw = json.dumps(receipts[1])[:-1] + ', "extra": NaN}'
    events = rr.history(body_with(body,receipts[:1])+'routing-receipt: '+raw+'\n',case[1],TARGET,'next')
    assert all(e.get('status') != 'received' for e in events)
    receipts[1]['status']='pending'
    assert all(e.get('status') != 'received' for e in get(case,body,receipts))


def test_third_duplicate_stays_invalid(case):
    body, receipts = evidence(case)
    assert all(e.get('status') != 'received' for e in get(case,body,[*receipts, receipts[1], receipts[1]]))


def test_tree_recipe_cannot_replace_route(case):
    body, receipts=evidence(case)
    for r in receipts: r['route_content_hash']=TREE
    assert all(e.get('status') != 'received' for e in get(case,body,receipts))


def test_duplicate_json_id_cannot_overwrite(case):
    body, receipts=evidence(case)
    raw=json.dumps(receipts[1]).replace('{', '{"dispatch_id":"first",',1)
    events=rr.history(body_with(body,receipts[:1])+'routing-receipt: '+raw+'\n',case[1],TARGET,'next')
    assert all(e.get('status') != 'received' for e in events)


def test_history_family_missing_cannot_be_received(case):
    body, receipts=evidence(case)
    body=body.replace('| family |', '| - |')
    assert all(e.get('status') != 'received' for e in get(case,body,receipts))


@pytest.mark.parametrize('raw', [
    '{"dispatch_id":"first","status":"pending","status":"received"}',
    '{broken',
    'null',
    '{"dispatch_id":"unrelated","extra":NaN}',
])
@pytest.mark.parametrize('position', ['before', 'after'])
def test_malformed_receipt_invalidates_all_receipts(case, raw, position):
    body, receipts = evidence(case)
    valid_body = body_with(body, receipts)
    assert get(case, body, receipts)[0]['status'] == 'received'
    invalid = 'routing-receipt: ' + raw + '\n'
    text = body + invalid + body_with('', receipts) if position == 'before' else valid_body + invalid
    events = rr.history(text, case[1], TARGET, 'next')
    assert any(event.get('missing') for event in events)
    assert all(event.get('status') != 'received' for event in events)
