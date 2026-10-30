"""Admission decisions plus the actual launcher, with no real Codex/GitHub."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from conftest import VALID_REVIEW_PROMPT

ROOT = Path(os.environ.get('RGE_TEST_ROOT', Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / 'lib'))
import review_admission as admission
from round_gate import Indeterminate


@pytest.fixture(autouse=True)
def trace_mutation():
    lines = set()
    target = str(ROOT / 'lib/review_admission.py')
    def trace(frame, event, arg):
        if event == 'line' and frame.f_code.co_filename == target:
            lines.add(frame.f_lineno)
        return trace
    if os.environ.get('RGE_TRACE'):
        sys.settrace(trace)
    yield
    sys.settrace(None)
    if os.environ.get('RGE_TRACE'):
        with open(os.environ['RGE_TRACE'], 'a') as out:
            out.write(json.dumps(sorted(lines)) + '\n')


@pytest.fixture
def case(tmp_path):
    state = tmp_path / 'state'
    state.mkdir()
    work = tmp_path / 'project'
    work.mkdir()
    prompt = tmp_path / 'prompt'
    prompt.write_text(VALID_REVIEW_PROMPT)
    def run(text=None, target='none:test', predecessor='', body=''):
        if text is not None:
            prompt.write_text(text)
        return admission.check(prompt, str(work), state, target, predecessor, lambda _: body)
    run.state, run.work, run.prompt = state, work, prompt
    return run


def history(case, number=1, found=('A',), repairs='なし', target='none:test', **extra):
    report = case.state / f'r{number}.report'
    findings = [{'severity': 'Must', 'family': f} for f in found]
    report.write_text('修正要\nread_sha=' + 'a'*40 + '\ncontent_hash=' + 'b'*64 +
                      '\nreview_findings=' + json.dumps(findings) + '\n')
    data = dict(pid='2147483647', run_id=f'r{number}', workdir=str(case.work), started_at=str(number),
                review_target=target, report=str(report), head_sha='a'*40, content_hash='b'*64,
                repair_families=repairs, round=str(number), kind_label='設計')
    data.update(extra)
    path = case.state / f'r{number}.state'
    path.write_text(''.join(f'{k}={v}\n' for k,v in data.items()))
    return path, report


def request(repairs='なし', addition='なし'):
    return VALID_REVIEW_PROMPT.replace('## 修正した族\nなし', '## 修正した族\n'+repairs).replace('## 追加変更\nなし', '## 追加変更\n'+addition)


@pytest.mark.parametrize('field', admission.FIELDS)
def test_missing_field(case, field):
    text = VALID_REVIEW_PROMPT
    start = text.index('## '+field+'\n')
    end = text.find('\n## ', start + 3)
    text = text[:start] + (text[end+1:] if end >= 0 else '')
    with pytest.raises(Indeterminate):
        case(text)


def test_zero_without_addition(case):
    history(case, found=())
    with pytest.raises(Indeterminate):
        case()


def test_two_repairs_stop(case):
    history(case, 1, repairs='A')
    history(case, 2, repairs='A')
    with pytest.raises(Indeterminate):
        case(request('A', 'あり: 新しい変更と確認理由'))


def test_unreadable_previous(case):
    _, report = history(case)
    report.unlink()
    with pytest.raises(Indeterminate):
        case(request('A'))


@pytest.mark.parametrize('transform', ['fence', 'duplicate', 'empty', 'spelling', 'nested'])
def test_heading_transforms(case, transform):
    if transform == 'fence':
        text = '```md\n' + VALID_REVIEW_PROMPT + '```\n'
    elif transform == 'duplicate':
        text = VALID_REVIEW_PROMPT + '\n## 守る対象\n別内容\n'
    elif transform == 'empty':
        text = VALID_REVIEW_PROMPT.replace('既存の受付条件と状態記録。', '')
    elif transform == 'spelling':
        text = VALID_REVIEW_PROMPT.replace('## 信頼境界', '## 信頼 境界')
    else:
        text = VALID_REVIEW_PROMPT.replace('## 信頼境界', '### 信頼境界')
    with pytest.raises(Indeterminate):
        case(text)


@pytest.mark.parametrize('tags', ['A.1', 'A,A', 'a', 'A，B', 'A\nB', 'A,B,C,D,E'])
def test_family_subdivision(case, tags):
    with pytest.raises(Indeterminate):
        case(request(tags))


@pytest.mark.parametrize('alter', ['bad_json', 'duplicate_json', 'subtag', 'duplicate_result', 'receipt', 'old', 'unknown_repairs', 'unreadable_state', 'broken_state'])
def test_bad_history(case, alter):
    target = 'issue:org/repo#1' if alter == 'receipt' else 'none:test'
    path, report = history(case, target=target)
    if alter == 'bad_json': report.write_text(report.read_text().replace('[{"severity"', '[invalid {"severity"'))
    elif alter == 'duplicate_json': report.write_text(report.read_text().replace('"family": "A"', '"family": "B", "family": "A"'))
    elif alter == 'subtag': report.write_text(report.read_text().replace('"A"', '"A.1"'))
    elif alter == 'duplicate_result': report.write_text(report.read_text() + 'review_findings=[]\n')
    elif alter == 'receipt': report.write_text(report.read_text().replace('a'*40, 'c'*40))
    elif alter == 'old': report.write_text('指摘0件\n')
    elif alter == 'unknown_repairs': path.write_text(path.read_text().replace('repair_families=なし\n', ''))
    elif alter == 'unreadable_state': path.unlink(); path.mkdir()
    else: path.write_text(path.read_text() + 'review_target=none:other\n')
    with pytest.raises(Indeterminate):
        case(request('A'), target=target)


def test_remote_without_local(case):
    with pytest.raises(Indeterminate):
        case(target='issue:org/repo#1', body='| 2 | コード | now | abc | codex | 計測中 |\n判定: 修正要')


def test_predecessor_missing(case):
    with pytest.raises(Indeterminate):
        case(predecessor='pr:org/repo#1')


def test_renamed_target_and_kind_keeps_family(case):
    history(case, 1, repairs='A', target='none:old')
    history(case, 2, repairs='A', target='bypass', kind_label='コード')
    with pytest.raises(Indeterminate):
        case(request('A'), target='none:new')


def test_underdeclared_repairs(case):
    history(case, found=('A','B'))
    with pytest.raises(Indeterminate):
        case(request('A'))


@pytest.mark.parametrize('mode', ['initial', 'valid', 'zero_addition', 'different_family', 'one_repair', 'other_project'])
def test_positive_controls(case, mode):
    text = request()
    if mode == 'valid':
        history(case); text = request('A')
    elif mode == 'zero_addition':
        history(case, found=()); text = request(addition='あり: 対象を追加したため再検査')
    elif mode == 'different_family':
        history(case, 1, repairs='A'); history(case, 2, repairs='B'); text = request('A')
    elif mode == 'one_repair':
        history(case, repairs='A'); text = request('A')
    elif mode == 'other_project':
        history(case, workdir=str(case.work / 'other'))
    assert case(text) in ('なし', 'A')


@pytest.mark.parametrize('valid', [True, False])
def test_launcher_wiring(case, tmp_path, valid):
    fake = tmp_path / 'bin'; fake.mkdir()
    capture = tmp_path / 'capture'
    codex = fake / 'codex'
    codex.write_text('#!/bin/sh\ncat > "$RGE_CAPTURE"\n')
    codex.chmod(0o755)
    gh = fake / 'gh'; gh.write_text('#!/bin/sh\nexit 93\n'); gh.chmod(0o755)
    case.prompt.write_text(request() if valid else 'no fields')
    env = {k:v for k,v in os.environ.items() if not k.startswith(('CODEX_', 'REVIEW_', 'GH_', 'GITHUB_'))}
    env.update(PATH=str(fake)+os.pathsep+env['PATH'], CODEX_WATCH_DIR=str(case.state),
               CODEX_REVIEW_KIND_LABEL='コード', REVIEW_TARGET='none:test', RGE_CAPTURE=str(capture))
    result = subprocess.run([str(ROOT / 'bin/codex-review'), str(case.work), str(case.prompt)],
                            env=env, capture_output=True, text=True, timeout=10)
    if valid:
        assert result.returncode == 0, result.stdout + result.stderr
        import time
        for _ in range(100):
            if capture.exists() and 'review_findings=' in capture.read_text(): break
            time.sleep(.01)
        assert 'review_findings=' in capture.read_text()
        assert 'repair_families=なし' in next(case.state.glob('*.state')).read_text()
    else:
        assert result.returncode != 0
        assert len(result.stderr.splitlines()) == 1
        assert not capture.exists()
        assert not list(case.state.glob('*.state'))


def test_running_previous(case):
    history(case, pid=str(os.getpid()))
    with pytest.raises(Indeterminate):
        case(request('A'))


@pytest.mark.parametrize('addition', ['', 'あり:', 'あり: ', 'あり：理由', 'あり: 理由\n複数行'])
def test_addition_shape(case, addition):
    history(case, found=())
    with pytest.raises(Indeterminate):
        case(request(addition=addition))


def test_inherited_target_across_workdirs(case):
    history(case, target='pr:org/repo#1', workdir=str(case.work / 'old'))
    with pytest.raises(Indeterminate):
        case(target='issue:org/repo#2', predecessor='pr:org/repo#1')
    assert case(request('A'), target='issue:org/repo#2', predecessor='pr:org/repo#1') == 'A'


def test_remote_history_ahead_of_local(case):
    history(case, target='issue:org/repo#1')
    with pytest.raises(Indeterminate):
        case(request('A'), target='issue:org/repo#1', body='| 2 | コード | now | abc | codex | 計測中 |')


def test_inherited_cycle(case):
    with pytest.raises(Indeterminate):
        case(target='pr:org/repo#1', body='前身 PR #1')


def test_ambiguous_timestamp(case):
    history(case, 1, started_at='1')
    history(case, 2, started_at='1')
    with pytest.raises(Indeterminate):
        case(request('A'))


@pytest.mark.parametrize('two_repairs', [False, True])
def test_missing_review_target_rejected(case, two_repairs):
    if two_repairs:
        history(case, 1, repairs='A')
    path, _ = history(case, 2, found=('A',) if two_repairs else (), repairs='A')
    path.write_text(path.read_text().replace('review_target=none:test\n', ''))
    with pytest.raises(Indeterminate, match='レビュー記録'):
        case(request('A' if two_repairs else 'なし'))


def test_impl_disguise_rejected(case):
    path, _ = history(case, found=(), mode='workspace-write')
    path.write_text(path.read_text().replace('review_target=none:test\n', ''))
    with pytest.raises(Indeterminate, match='レビュー記録'):
        case()


def test_real_impl_record_skipped(case):
    # codex-impl always writes mode=workspace-write; no review fields are emitted.
    (case.state / 'impl.state').write_text(
        f'run_id=impl\npid={os.getpid()}\nworkdir={case.work}\nstarted_at=1\n'
        'mode=workspace-write\nwritable_git_common=\naws=none\naws_expiration=\n')
    assert case() == 'なし'


@pytest.mark.parametrize('missing', ['pid', 'report', 'round', 'repair_families', 'head_sha', 'content_hash'])
def test_review_required_keys(case, missing):
    path, _ = history(case)
    path.write_text(''.join(line+'\n' for line in path.read_text().splitlines()
                            if not line.startswith(missing+'=')))
    with pytest.raises(Indeterminate, match='レビュー記録'):
        case(request('A'))


@pytest.mark.parametrize('target', ['none:test', 'bypass'])
def test_unhashed_next_round_with_addition(case, target):
    history(case, found=(), target=target, head_sha='', content_hash='')
    assert case(request(addition='あり: 新規入力を追加したため再検査'), target=target) == 'なし'


def test_independent_issue_same_workdir(case):
    history(case, found=(), target='issue:org/repo#1')
    assert case(target='issue:org/repo#2') == 'なし'


@pytest.mark.parametrize('target', ['none:new', 'bypass'])
def test_omitted_predecessor_untracked_target_keeps_history(case, target):
    history(case, found=(), target='issue:org/repo#1')
    with pytest.raises(Indeterminate, match='前巡0件'):
        case(target=target)


def test_tracked_receipt_still_required(case):
    history(case, found=(), target='issue:org/repo#1', head_sha='', content_hash='')
    with pytest.raises(Indeterminate, match='受領照合'):
        case(request(addition='あり: 新規入力を追加したため再検査'), target='issue:org/repo#1')


@pytest.mark.parametrize('bypass', [False, True])
def test_launcher_unhashed_next_round(case, tmp_path, monkeypatch, bypass):
    fake = tmp_path / 'bin'; fake.mkdir()
    done = tmp_path / 'done'
    codex = fake / 'codex'
    codex.write_text('''#!/bin/sh
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-o" ]; then shift; report="$1"; fi
  shift
done
cat >/dev/null
printf 'review_findings=[]\\n' > "$report"
printf 'done' > "$RGE_DONE"
''')
    codex.chmod(0o755)
    gh = fake / 'gh'; gh.write_text('#!/bin/sh\nexit 93\n'); gh.chmod(0o755)
    env = {k:v for k,v in os.environ.items() if not k.startswith(('CODEX_', 'REVIEW_', 'GH_', 'GITHUB_'))}
    env.update(PATH=str(fake)+os.pathsep+env['PATH'], CODEX_WATCH_DIR=str(case.state),
               CODEX_REVIEW_KIND_LABEL='コード', REVIEW_TARGET='none:test', RGE_DONE=str(done))
    if bypass:
        env['CODEX_REVIEW_NO_GATE'] = 'test'
    result = subprocess.run([str(ROOT / 'bin/codex-review'), str(case.work), str(case.prompt)],
                            env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    import time
    for _ in range(100):
        if done.exists(): break
        time.sleep(.01)
    assert done.exists()
    data = admission.strict_state(next(case.state.glob('*.state')))
    target = 'bypass' if bypass else 'none:test'
    assert data['review_target'] == target
    assert data['head_sha'] == data['content_hash'] == ''
    # The stub has produced its final report; isolate OS process reaping from admission.
    def exited(pid, signal):
        assert pid == int(data['pid']) and signal == 0
        raise ProcessLookupError
    monkeypatch.setattr(admission.os, 'kill', exited)
    assert case(request(addition='あり: 新規入力を追加したため再検査'), target=target) == 'なし'
