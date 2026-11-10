"""節と項目の有無だけ・自己申告・迂回可能な受付を offline CLI で確認する。"""
from pathlib import Path
import subprocess
import sys

import pytest
import test_codex_review_cli as cli
from test_codex_review_cli import fake_bin, VALID_GOAL_CUT

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from round_gate import missing_preview_checks

TWO = '点検:\n- 突き合わせ: 確認済\n- 出所の付記: 消した\n'
THREE = TWO + '- 直し残しの検索: git grep で0件\n'
TARGET = 'issue:example-org/example-repo#1'


@pytest.mark.parametrize('body,round_no,missing', [
    (TWO, 1, []), (THREE, 2, []), (THREE, 3, []),
    (TWO.replace('点検:', '## 点検'), 1, []),
    (TWO.replace('点検:', '点検: 済'), 1, []),
    ('前置き\r\n' + TWO.replace('\n', '\r\n'), 1, []),
    (TWO.replace('確認済', 'x').replace('消した', '虚偽の自己申告'), 1, []),
    (TWO.replace('確認済', '\t\u3000'), 1, ['突き合わせ']),
    (TWO.replace('消した', '\u00a0'), 1, ['出所の付記']),
    (TWO.replace('点検:', '検査:'), 1, ['突き合わせ', '出所の付記']),
    (TWO.replace('点検:', ' 点検:'), 1, ['突き合わせ', '出所の付記']),
    (TWO.replace('点検:', '点検：'), 1, ['突き合わせ', '出所の付記']),
    (TWO.replace('突き合わせ:', '突き合わせ済:'), 1, ['突き合わせ']),
    (TWO, 2, ['直し残しの検索']),
    ('- 突き合わせ: x\n- 出所の付記: y\n点検:\n', 1, ['突き合わせ', '出所の付記']),
    ('点検:\n## 別の節\n- 突き合わせ: x\n- 出所の付記: y\n', 1, ['突き合わせ', '出所の付記']),
    ('点検:\n- 突き合わせ: x\n点検:\n- 出所の付記: y\n', 1, ['出所の付記']),
    ('点検:\n- 突き合わせ:\n' + TWO, 1, []),
])
def test_節と項目の有無だけ_自己申告_迂回可能(body, round_no, missing):
    """節と項目の有無だけ・自己申告・迂回可能（虚偽の内容でも通る）。"""
    assert missing_preview_checks(body, round_no) == missing


def dispatch(tmp_path, fake_bin, body, prior_kind=None, prior_target=TARGET, same_head=False):
    repo = tmp_path / 'repo'
    repo.mkdir()
    cli._init_git_repo(repo)
    state = tmp_path / 'state'
    state.mkdir()
    if prior_kind:
        head = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
        (state / 'prior.state').write_text(
            f'review_target={prior_target}\nhead_sha={head if same_head else "prior"}\n'
            f'kind_label={prior_kind}\nstarted_at=1\nround=1\n')
    before = {p.name: p.read_bytes() for p in state.glob('*.state')}
    body_file = tmp_path / 'fake_gh_body.txt'
    body_file.write_text('')
    result = cli._run_in_git_workdir(fake_bin, tmp_path, repo,
        review_target=TARGET, review_goal_cut=VALID_GOAL_CUT, prompt_text=body)
    return result, state, before, body_file


@pytest.mark.parametrize('body,prior_kind,prior_target,same_head', [
    (TWO, None, TARGET, False),
    (THREE, 'コード', TARGET, False),
    (TWO, '設計', TARGET, False),
    (TWO, 'コード', TARGET, True),
    (TWO, 'コード', 'issue:example-org/example-repo#2', False),
])
def test_cli_節と項目の有無だけ_自己申告_迂回可能_positive(
    tmp_path, fake_bin, body, prior_kind, prior_target, same_head
):
    result, state, before, body_file = dispatch(tmp_path, fake_bin, body, prior_kind, prior_target, same_head)
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(list(state.glob('*.state'))) == len(before) + 1
    assert '| clitest |' in body_file.read_text()
    effective = next(state.glob('*.prompt.*')).read_text()
    assert body in effective
    assert ('この巡は前の巡の [Must]' in effective) == (body == THREE)


@pytest.mark.parametrize('body,prior_kind,missing', [
    ('依頼本文だけ\n- 突き合わせ: x\n- 出所の付記: y\n', None, '突き合わせ'),
    (TWO.replace('確認済', ' \t\u3000'), None, '突き合わせ'),
    (TWO, 'コード', '直し残しの検索'),
    (TWO.replace('点検:', '確認:'), None, '出所の付記'),
    (TWO.replace('点検:', '点検:\n## 関連資料'), None, '突き合わせ'),
    (TWO.replace('突き合わせ:', '突き合わせ済:'), None, '突き合わせ'),
    (TWO.replace('消した', '\u00a0'), None, '出所の付記'),
])
def test_cli_節と項目の有無だけ_自己申告_迂回可能_negative(tmp_path, fake_bin, body, prior_kind, missing):
    result, state, before, body_file = dispatch(tmp_path, fake_bin, body, prior_kind)
    # Check side effects before returncode: catches record-on-stop independently.
    assert {p.name: p.read_bytes() for p in state.glob('*.state')} == before
    assert body_file.read_text() == ''
    assert not list(state.glob('*.prompt.*'))
    assert not (tmp_path / 'argv.txt').exists()
    assert result.returncode == 2, result.stdout + result.stderr
    assert '依頼文に『点検:』の節が無い／項目が足りない' in result.stderr
    assert f'足りない項目: ' in result.stderr and missing in result.stderr
    assert '決まりは review-gate スキルの『出す前の点検』' in result.stderr
