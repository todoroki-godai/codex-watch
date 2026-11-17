"""First-line contract, through receipt CLI, status display and history consumers."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import round_gate as rg
from test_codex_status_receipt import _write_finished_run, _run_status, SHA, HASH
from test_received_history import evidence, get, TREE
from test_routing_record import case

ROOT = Path(__file__).resolve().parents[1]
NEGATIVE = [
    ('value', '判定保留'),
    ('condition', 'マージ可'),
    ('branch-blank', ''),
    ('branch-empty-report', None),
    ('order', '対象差分を確認中\n実装着手可'),
    ('extra-decoration', '**実装着手可**'),
    ('extra-suffix', '実装着手可（Must 0件）'),
    ('extra-space-reason', '判定保留: \t\u3000\u00a0'),
    ('extra-cross-line-reason', '判定保留: \n前の回と照合できない'),
    ('extra-control-prefix', '\x1b[32m実装着手可\x1b[0m'),
    ('extra-bom-prefix', '\ufeff実装着手可'),
]
POSITIVE = ['実装着手可', '設計修正要', '判定保留: 前の回の内容と照合できないため']


def report(first):
    return '' if first is None else f'{first}\nread_sha={SHA}\ncontent_hash={HASH}\n本文\n'


@pytest.mark.parametrize('name,first', NEGATIVE, ids=[n for n, _ in NEGATIVE])
def test_negative_receipt_cli(tmp_path, name, first):
    _write_finished_run(tmp_path, 'probe', head_sha=SHA, content_hash=HASH, report_body=report(first))
    run = subprocess.run([sys.executable, str(ROOT / 'lib/round_gate.py'), 'receipt',
                          '--state-file', str(tmp_path / 'probe.state'),
                          '--report', str(tmp_path / 'probe.report'), '--json'],
                         capture_output=True, text=True)
    assert run.returncode == 4, run.stdout + run.stderr
    assert json.loads(run.stdout)['status'] == 'rejected'
    # Also test the new check alone: shifted hash lines must not hide its failure.
    checked = rg.check_verdict_line('' if first is None else first)
    assert checked.status == 'rejected'
    assert '出し直してください' in checked.reason


@pytest.mark.parametrize('first', POSITIVE)
def test_positive_receipt_and_status(tmp_path, first):
    assert rg.check_receipt(SHA, HASH, report(first)).status == 'ok'
    _write_finished_run(tmp_path, 'probe', head_sha=SHA, content_hash=HASH, report_body=report(first))
    run = _run_status(tmp_path, 'probe')
    assert run.returncode == 0, run.stderr
    assert '受領可:' in run.stdout
    assert f'--- 判定: {first} /' in run.stdout


def test_negative_status_and_history(case):
    body, receipts = evidence(case)
    (case[1] / 'second.report').write_text(report('判定保留').replace(HASH, TREE))
    assert all(row['status'] != 'received' for row in get(case, body, receipts))
    _write_finished_run(case[1], 'probe', head_sha=SHA, content_hash=HASH, report_body=report('判定保留'))
    run = _run_status(case[1], 'probe')
    assert '受領不可:' in run.stdout and '出し直してください' in run.stdout


def test_fail_open_does_not_disable_existing_hash_check():
    # Force an exception inside only the new validator, not the SHA/hash parser.
    class BrokenPrefix(str):
        def startswith(self, *args):
            raise RuntimeError('injected validator failure')
    class Text(str):
        def split(self, sep):
            assert sep == '\n'
            return [BrokenPrefix('途中経過'), f'read_sha={SHA}', f'content_hash={HASH}']
    text = Text('report')
    assert rg.check_receipt(SHA, HASH, text).status == 'ok'
    assert rg.check_receipt('b' * 40, HASH, text).status == 'rejected'


@pytest.mark.parametrize('newline', ['\n', '\r\n'])
def test_positive_line_endings(newline):
    assert rg.check_receipt(SHA, HASH, report(POSITIVE[2]).replace('\n', newline)).status == 'ok'


# Exact Must reproduction: the opposite verdict remains on the second LF line.
SEPARATORS = [('\v', 'VT'), ('\f', 'FF'), ('\x85', 'NEL'), ('\r', 'CR')]
FORBIDDEN = [chr(n) for n in range(32) if n not in (9, 10, 13)] + [
    chr(n) for n in range(0x7f, 0xa0)
] + ['\u2028', '\u2029']


@pytest.mark.parametrize('sep,name', SEPARATORS, ids=[n for _, n in SEPARATORS])
def test_separator_bypass_rejected(tmp_path, sep, name):
    text = f'実装着手可{sep}read_sha={SHA}{sep}content_hash={HASH}\n設計修正要'
    assert rg.check_verdict_line(text).status == 'rejected'
    assert rg.parse_receipt_claim(text) == (None, None)
    assert rg.check_receipt(SHA, HASH, text).status == 'rejected'
    _write_finished_run(tmp_path, 'probe', head_sha=SHA, content_hash=HASH, report_body=text)
    run = _run_status(tmp_path, 'probe')
    assert run.returncode == 0, run.stderr
    assert '受領不可:' in run.stdout


@pytest.mark.parametrize('control', FORBIDDEN, ids=lambda c: f'U+{ord(c):04X}')
@pytest.mark.parametrize('place', ['reason', 'claim', 'body'])
def test_control_anywhere_rejected(control, place):
    text = report('判定保留: 理由' + control) if place == 'reason' else report(POSITIVE[0])
    if place == 'claim':
        text = text.replace(f'read_sha={SHA}', f'read_sha={SHA}{control}')
    elif place == 'body':
        text += '本文' + control
    # The SHA/hash reader alone must not conceal a broken verdict validator.
    assert rg.check_verdict_line(text).status == 'rejected'
    assert rg.check_receipt(SHA, HASH, text).status == 'rejected'


@pytest.mark.parametrize('newline', ['\n', '\r\n'], ids=['LF', 'CRLF'])
@pytest.mark.parametrize('first', POSITIVE)
def test_all_verdicts_both_endings(tmp_path, case, newline, first):
    text = report(first).replace('\n', newline)
    assert rg.check_receipt(SHA, HASH, text).status == 'ok'
    assert rg.parse_receipt_claim(text) == (SHA, HASH)
    _write_finished_run(tmp_path, 'probe', head_sha=SHA, content_hash=HASH, report_body=text)
    run = _run_status(tmp_path, 'probe')
    assert '受領可:' in run.stdout, run.stdout + run.stderr
    body, receipts = evidence(case)
    (case[1] / 'second.report').write_bytes(text.replace(HASH, TREE).encode())
    assert all(row['status'] == 'received' for row in get(case, body, receipts))


@pytest.mark.parametrize('text', [
    report(POSITIVE[0]).replace('\n', '\r'),
    report(POSITIVE[0]).replace('\n', '\r\r\n'),
    report(POSITIVE[0]) + '\r',
    report('判定保留: 理由\r\r'),
], ids=['CR-only', 'CRCRLF', 'final-CR', 'reason-CRCRLF'])
def test_stray_cr_rejected_through_consumers(tmp_path, case, text):
    assert rg.check_verdict_line(text).status == 'rejected'
    assert rg.check_receipt(SHA, HASH, text).status == 'rejected'
    _write_finished_run(tmp_path, 'probe', head_sha=SHA, content_hash=HASH, report_body=text)
    run = _run_status(tmp_path, 'probe')
    assert '受領不可:' in run.stdout, run.stdout + run.stderr
    body, receipts = evidence(case)
    assert all(row['status'] == 'received' for row in get(case, body, receipts))
    (case[1] / 'second.report').write_bytes(text.replace(HASH, TREE).encode())
    assert all(row['status'] != 'received' for row in get(case, body, receipts))


def test_positive_tabs_and_mixed_endings():
    text = f'判定保留: 理由\t補足\r\nread_sha={SHA}\t\ncontent_hash={HASH}\t\r\n本文\t補足'
    assert rg.check_receipt(SHA, HASH, text).status == 'ok'


def test_line_split_preserves_non_delimiters():
    assert rg.split_receipt_lines('a\r\nb\nc\rd\v\f\x85\u2028\u2029\r') == [
        'a', 'b', 'c\rd\v\f\x85\u2028\u2029\r']
    assert rg.split_receipt_lines('a\r\r\n') == ['a\r', '']
