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


@pytest.mark.parametrize('failure', ['missing', 'directory'])
def test_missing_canonical_stops_before_dispatch(launcher, tmp_path, fake_bin, failure):
    canonical = launcher / 'templates/must-criteria.md'
    canonical.unlink()
    if failure == 'directory':
        canonical.mkdir()
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
