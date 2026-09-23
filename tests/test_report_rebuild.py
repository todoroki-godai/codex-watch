"""Report reconstruction with local synthetic codex logs; no CLI/LLM calls."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
import round_gate as rg

SHA = 'a' * 40
HASH = '1' * 64


def rebuild(tmp_path, log_text, original):
    log = tmp_path / 'run.log'
    report = tmp_path / 'run.report'
    log.write_text(log_text)
    report.write_text(original)
    result = subprocess.run(
        ['bash', '-c', 'source "$1"; rebuild_report_if_needed "$2" "$3" || exit; extract_verdict_line "$3"',
         'bash', str(ROOT / 'lib/report_rebuild.sh'), str(log), str(report)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    return report.read_text(), result.stdout.strip(), report


@pytest.mark.parametrize('verdict,preamble', [
    ('マージ可', '修正要否は未判定です。対象コミットを確認してから判定を返します。'),
    ('修正要', '修正要／マージ可の判定は差分を確認してから確定します。'),
])
@pytest.mark.parametrize('original_kind', ['preamble', 'combined', 'tail'])
def test_rebuild_preamble_receipt(tmp_path, verdict, preamble, original_kind):
    body = f'{verdict}\nread_sha={SHA}\ncontent_hash={HASH}\n本文\n'
    original = {'preamble': preamble, 'combined': preamble + '\n\n\n' + body, 'tail': '後続本文'}[original_kind]
    log = f'user\n依頼\ncodex\n{preamble}\nhook: done\ncodex\n{body}hook: done\ncodex\n後続本文\n'
    text, displayed, report = rebuild(tmp_path, log, original)
    assert text.splitlines()[:3] == body.splitlines()[:3]
    assert '後続本文' in text
    assert preamble not in text
    assert displayed == verdict
    assert rg.check_receipt(SHA, HASH, text).status == 'ok'
    assert rg.check_receipt('b' * 40, HASH, text).status == 'rejected'
    assert rg.check_receipt(SHA, '2' * 64, text).status == 'rejected'
    assert Path(str(report) + '.raw').read_text() == original


def test_valid_report_is_untouched(tmp_path):
    original = f'マージ可\nread_sha={SHA}\ncontent_hash={HASH}\n'
    text, verdict, report = rebuild(tmp_path, 'codex\n別内容\n', original)
    assert text == original
    assert verdict == 'マージ可'
    assert not Path(str(report) + '.raw').exists()


@pytest.mark.parametrize('body', [
    f'マージ可\nread_sha={SHA}\ncontent_hash={HASH}',
    '判定はまだありません\n本文',
    '説明\nマージ可\n本文',  # A verdict inside a section is not a section start.
    'マージ可の予定\n本文',  # Prefix matches must not count as verdicts.
])
def test_rebuild_without_verdict_section_preserves_output(tmp_path, body):
    text, _, _ = rebuild(tmp_path, f'codex\n{body}\nhook: done\ncodex\n後続\n', '部分出力')
    assert text == body + '\n\n後続'


def test_first_verdict_section_keeps_later_verdict_sections(tmp_path):
    body = f'設計修正要\nread_sha={SHA}\ncontent_hash={HASH}'
    text, verdict, _ = rebuild(tmp_path, f'codex\n前置き\ncodex\n{body}\ncodex\n実装着手可\n後続\n', '後続')
    assert text == body + '\n実装着手可\n後続'
    assert verdict == '設計修正要'
    assert rg.check_receipt(SHA, HASH, text).status == 'ok'
