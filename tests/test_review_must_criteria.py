"""Must prefaces through the real launcher; all external CLIs are offline fakes."""
from pathlib import Path
import shutil

import pytest
import test_codex_review_cli as cli
from test_codex_review_cli import fake_bin, VALID_GOAL_CUT

ROOT = Path(__file__).resolve().parents[1]
SCOPE = 'この巡は前の巡の [Must] が直ったかを確かめるだけ。新しい論点は [Should] として別課題の候補に返す。新しい [Must] は今回の直しが新たに壊したものだけ。'


@pytest.fixture
def launcher(tmp_path, monkeypatch):
    # Missing-file probes must not rename or edit the checked-out canonical file.
    folder = tmp_path / 'launcher with spaces'
    for name in ('bin', 'lib', 'templates'):
        shutil.copytree(ROOT / name, folder / name,
                        ignore=shutil.ignore_patterns('__pycache__'))
    monkeypatch.setattr(cli, 'CODEX_REVIEW', folder / 'bin/codex-review')
    return folder


@pytest.mark.parametrize('failure', ['missing', 'directory', 'empty'])
def test_missing_canonical_stops_before_dispatch(launcher, tmp_path, fake_bin, failure):
    canonical = launcher / 'templates/must-criteria.md'
    canonical.unlink()
    if failure == 'directory':
        canonical.mkdir()
    elif failure == 'empty':
        canonical.touch()
    result = cli._run(fake_bin, tmp_path,
                      review_target='issue:example-org/example-repo#1',
                      review_goal_cut=VALID_GOAL_CUT, gate_check=False)
    assert result.returncode == 2, result.stdout + result.stderr
    assert not (tmp_path / 'argv.txt').exists()
    assert not list((tmp_path / 'state').glob('*.state'))


def test_reads_current_canonical_before_user_prompt(launcher, tmp_path, fake_bin):
    canonical = launcher / 'templates/must-criteria.md'
    # A distinct current revision catches a cached/hardcoded copy of the template.
    conditions = canonical.read_text() + '\n正本更新の試験: 空白・日本語 😀\n'
    canonical.write_text(conditions)
    result = cli._run(fake_bin, tmp_path,
                      review_target='issue:example-org/example-repo#1',
                      review_goal_cut=VALID_GOAL_CUT, gate_check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    prompts = list((tmp_path / 'state').glob('*.prompt.*'))
    assert len(prompts) == 1
    text = prompts[0].read_text()
    assert text.count(conditions) == 1
    assert text.index(conditions) < text.index('dummy prompt')


@pytest.mark.parametrize('round_no', [1, 2, 3])
def test_cli_followup_scope_from_ledger(tmp_path, fake_bin, round_no):
    repo = tmp_path / 'repo'
    repo.mkdir()
    cli._init_git_repo(repo)
    state = tmp_path / 'state'
    state.mkdir()
    for i in range(round_no - 1):
        (state / f'prior{i}.state').write_text(
            f'review_target=issue:example-org/example-repo#1\nhead_sha=prior{i}\nstarted_at={i}\nround={i+1}\n')
    (tmp_path / 'fake_gh_body.txt').write_text(
        '巡3の人間承認 総上限:5' if round_no >= 3 else '')
    result = cli._run_in_git_workdir(fake_bin, tmp_path, repo,
        review_target='issue:example-org/example-repo#1', review_goal_cut=VALID_GOAL_CUT)
    assert result.returncode == 0, result.stdout + result.stderr
    prompts = list(state.glob('*.prompt.*'))
    assert len(prompts) == 1
    text = prompts[0].read_text()
    assert text.count(SCOPE) == (1 if round_no >= 2 else 0)
    if round_no >= 2:
        conditions = (ROOT / 'templates/must-criteria.md').read_text().strip()
        assert text.index(conditions) < text.index(SCOPE) < text.index('dummy prompt')
    run_id = result.stdout.strip().splitlines()[-1]
    assert f'round={round_no}\n' in (state / f'{run_id}.state').read_text()


@pytest.mark.parametrize('prior_kinds,current_kind,expected', [
    (['設計'], 'コード', False),
    (['コード'], 'コード', True),
    (['設計'], '設計', True),
    ([None], 'コード', True),
    ([None], '設計', False),
    (['コード'], '設計', False),
])
def test_scope_separates_kinds(tmp_path, fake_bin, prior_kinds, current_kind, expected):
    repo = tmp_path / 'repo'
    repo.mkdir()
    cli._init_git_repo(repo)
    state = tmp_path / 'state'
    state.mkdir()
    for i, kind in enumerate(prior_kinds):
        (state / f'prior{i}.state').write_text(
            f'review_target=issue:example-org/example-repo#1\nhead_sha=prior{i}\nstarted_at={i}\n'
            + (f'kind_label={kind}\n' if kind is not None else ''))
    result = cli._run_in_git_workdir(fake_bin, tmp_path, repo,
        review_target='issue:example-org/example-repo#1', review_goal_cut=VALID_GOAL_CUT,
        kind_label=current_kind)
    assert result.returncode == 0, result.stdout + result.stderr
    text = next(state.glob('*.prompt.*')).read_text()
    assert text.count(SCOPE) == int(expected)
    run_id = result.stdout.strip().splitlines()[-1]
    # 総上限の巡数は種別を問わず2のまま。
    assert 'round=2\n' in (state / f'{run_id}.state').read_text()


@pytest.mark.parametrize('failure', ['unreadable', 'invalid-kind'])
def test_uncountable_ledger_stops(launcher, tmp_path, fake_bin, failure):
    state = tmp_path / 'state'
    state.mkdir()
    prior = state / 'prior.state'
    if failure == 'unreadable':
        prior.mkdir()  # OSError を権限・実行ユーザーに依存せず再現する。
    else:
        prior.write_text('review_target=issue:example-org/example-repo#1\n'
                         'head_sha=prior\nkind_label=不明\n')
    result = cli._run(fake_bin, tmp_path,
        review_target='issue:example-org/example-repo#1',
        review_goal_cut=VALID_GOAL_CUT, gate_check=False)
    assert result.returncode == 2, result.stdout + result.stderr
    assert not (tmp_path / 'argv.txt').exists()
    assert list(state.glob('*.state')) == [prior]


@pytest.mark.parametrize('scenario,expected', [
    ('same-head', False), ('duplicate-head', True), ('other-target', False),
])
def test_scope_counts_rounds_not_dispatches(tmp_path, fake_bin, scenario, expected):
    repo = tmp_path / 'repo'
    repo.mkdir()
    cli._init_git_repo(repo)
    state = tmp_path / 'state'
    state.mkdir()
    import subprocess
    head = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    target = 'issue:example-org/example-repo#1'
    old_target = target if scenario != 'other-target' else 'issue:example-org/example-repo#2'
    old_head = head if scenario == 'same-head' else 'prior'
    for i in range(2 if scenario == 'duplicate-head' else 1):
        (state / f'prior{i}.state').write_text(
            f'review_target={old_target}\nhead_sha={old_head}\nstarted_at={i}\nkind_label=コード\n')
    result = cli._run_in_git_workdir(fake_bin, tmp_path, repo,
        review_target=target, review_goal_cut=VALID_GOAL_CUT)
    assert result.returncode == 0, result.stdout + result.stderr
    text = next(state.glob('*.prompt.*')).read_text()
    assert text.count(SCOPE) == int(expected)
    # 再発注を新しい巡として数えない。前置きが同じでも数値の重複を検知する。
    import sys
    sys.path.insert(0, str(ROOT / 'lib'))
    from round_gate import ledger_own_round
    assert ledger_own_round(state, target, head, kind_label='コード') == (2 if scenario == 'duplicate-head' else 1)


def test_cause_precedes_final_evidence_for_each_must():
    lines = (ROOT / 'templates/must-criteria.md').read_text().splitlines()
    evidence = next(line for line in lines if line.startswith('各 [Must] の末尾に「根拠:'))
    causes = [line for line in lines if '「原因:' in line]
    assert len(causes) == 1
    assert causes[0].startswith('各 [Must] の「根拠:」行の直前に「原因:')
    assert '次に' not in causes[0]
    assert 'のどれかの1行を書く。' in evidence
    words = ('読まない', '環境差', '波及', '段取り', '本物')
    assert '・'.join(words) + 'のどれか1語>' in causes[0]
    for word in words:
        assert word + '＝' in causes[0]
        definition = causes[0].split(word + '＝', 1)[1].split('／', 1)[0].split('）。', 1)[0]
        assert definition.strip('（） 。')
    receiver = next(line for line in lines if line.startswith('受け手は各 [Must] 末尾の「根拠:'))
    assert lines.index(evidence) < lines.index(receiver) < lines.index(causes[0])
