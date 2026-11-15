"""Reuse the existing diff + executed-line mutation harness on committed sources."""
import subprocess
import check_routing_record_mutations as runner

runner.OUT = runner.ROOT / '.tmp/received-history-impl2/mutations'
runner.TEST_FILE = 'tests/test_received_history.py'
runner.CASES = [
    ('N1-ignore-receipt', 'receipts.get(rid), reasons)', "(receipts.get(rid) or dict(status='received', finding_family_tags=['none'], route_content_hash=d.get('route_content_hash'))), reasons)", 'same_hash_ids_required', 'entry.update(received_fields', '①受領行の要求削除'),
    ('N2-tree-recipe', "route_hash = d.get('route_content_hash', '')", "route_hash = d.get('content_hash', '')", 'tree_recipe', "route_hash = d.get('content_hash'", '②別レシピ流用'),
    ('N3-id-reassignment', 'receipts.get(rid), reasons)', "next((r for r in receipts.values() if r is not None), None), reasons)", 'same_hash_ids_required', 'entry.update(received_fields', '③同値hash別IDへの付替'),
    ('N4-always-ok', "ok = checked.status == 'ok'", 'ok = True', 'report_rejected', 'ok = True', '④照合無効化'),
    ('N5-partial-round', "        event = dict(event_id=entries[0]['event_id'], status='pending')", "        entries = [e for e in entries if e['status'] == 'received'] or entries\n        event = dict(event_id=entries[0]['event_id'], status='pending')", 'report_rejected or same_hash_ids_required', "entries = [e for e", '別種 一部受領を全員扱い'),
    ('N6-default-none', "tags = receipt.get('finding_family_tags')", "tags = receipt.get('finding_family_tags') or ['none']", 'incomplete_receipt', "tags = receipt.get('finding_family_tags') or", '別種 欠落族を補完'),
    ('N7-json-overwrite', '            if key in result:', '            if False:', 'duplicate_json_id', 'if False:', '別種 JSONキーの後勝ち'),
    ('N8-raw-reason', "reasons.append('受領照合失敗')", 'reasons.append(checked.reason)', 'receipt_failure_is_fixed', 'reasons.append(checked.reason)', '別種 本文ログ漏洩'),
    ('P1-equivalent', 'len(heads) == 1 and len(hashes) == 1', 'len(heads) in (1,) and len(hashes) == 1', '', 'and len(heads) in (1,)', 'positive'),
]

if __name__ == '__main__':
    # Mutations must start from a committed tree, including the tests that kill them.
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=runner.ROOT).strip()
    runner.main()
