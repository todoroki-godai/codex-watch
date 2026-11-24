"""#37 mutations; reuse the existing diff, trace and test-ID evidence runner."""
import check_round_count_c_mutations as runner

runner.OUT = runner.ROOT / '.tmp/roundcount-perkind/mutations'
runner.TEST_FILES.extend(['tests/test_roundcount_perkind.py', 'tests/test_round_gate.py'])
runner.CASES += [
    ('N14-next-approval-disabled', 'lib/round_gate.py',
     'if (not kinds and pending_new_head is not None',
     'if (False and pending_new_head is not None',
     'repro_design4', 'if (False and', '① remove next approval attribution'),
    ('N15-no-human-approval', 'lib/round_gate.py',
     'if not approvals:', 'if False:',
     'pending_boundaries', 'if False:', '④ disable human approval guard'),
    ('N16-no-cap-comparison', 'lib/round_gate.py',
     'if cap is None or total_for_decision > cap:', 'if cap is None:',
     'pending_boundaries', 'if cap is None:', '① remove cap comparison'),
    ('N17-exception-cap-increase', 'lib/prerelease.py',
     "if prior['series_id'] != data['series_id'] or prior['total_cap'] != data['total_cap']:",
     "if prior['series_id'] != data['series_id']:",
     'exception_cap_increase_without_human', "if prior['series_id']", '① remove saved exception cap guard'),
    ('N18-reused-head', 'lib/round_gate.py',
     'and pending_new_head not in distinct', 'and True',
     'pending_not_reused', 'and True', 'extra5 reuse a completed HEAD as next approval'),
    ('N19-future-round', 'lib/round_gate.py',
     'and 3 <= n <= 5 and ledger_total == n', 'and 3 <= n <= 5 and ledger_total <= n',
     'future_approval_not_completed', 'and 3 <= n <= 5', 'extra6 authorize an uncompleted future round'),
    ('N20-hard-ceiling', 'lib/round_gate.py',
     'if total_for_decision <= MAX_REVIEW_ROUNDS:', 'if total_for_decision <= MAX_REVIEW_ROUNDS + 1:',
     '4_plus_needs_verdict', 'if total_for_decision <= MAX_REVIEW_ROUNDS + 1:', '④ lift per-kind hard ceiling'),
    ('P3-equivalent-next-approval', 'lib/round_gate.py',
     'and 3 <= n <= 5 and ledger_total == n', 'and n in (3, 4, 5) and n == ledger_total',
     'repro_design4 or pending_boundaries', 'and n in (3, 4, 5)', 'positive'),
]

if __name__ == '__main__':
    runner.main()
