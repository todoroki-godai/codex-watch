import hashlib
import os
from pathlib import Path
import subprocess
import sys

import pytest

HELPER = Path(__file__).resolve().parents[1] / 'lib/receipt_gate.py'
REVIEW = '直しの出所: レビュー\n受領①累計: 1\n受領②件数: 0\n受領③7段: ㋑\n'


def run(tmp_path, body, entry='cc'):
    raw = body.encode() if isinstance(body, str) else body
    args = [sys.executable, str(HELPER), '--entrypoint', entry]
    if entry == 'cc':
        args += ['--stdin']
    else:
        prompt = tmp_path / 'prompt'
        prompt.write_bytes(raw)
        args += ['--file', str(prompt)]
    return subprocess.run(args, input=raw, capture_output=True, env={**os.environ, 'HOME': str(tmp_path)})


@pytest.mark.parametrize('body', ['なし', '直しの出所: なし\n直しの出所: なし\n', '直しの出所: \n',
    *[REVIEW.replace(line + '\n', '') for line in REVIEW.splitlines()[1:]],
    *[REVIEW + word for word in ('Should', 'should', 'sHoUlD')], b'\xff', b'\x00'])
def test_reject(tmp_path, body):
    result = run(tmp_path, body)
    assert result.returncode == 2 and not result.stdout


@pytest.mark.parametrize('entry', ['codex', 'cc'])
def test_pass(tmp_path, entry):
    result = run(tmp_path, REVIEW, entry)
    assert result.returncode == 0
    assert result.stdout == f'receipt-gate v1 pass sha256={hashlib.sha256(REVIEW.encode()).hexdigest()}\n'.encode()


def test_shared_guidance(tmp_path):
    body = '直しの出所: なし\n指摘を反映\n'
    codex = run(tmp_path, body, 'codex')
    cc = run(tmp_path, body, 'cc')
    assert codex.stderr == cc.stderr
    assert '出所を「レビュー…」に直し、受領の3行を書く必要があります。語で見ているだけ・言い換えは通る。調査・集計'.encode() in cc.stderr
