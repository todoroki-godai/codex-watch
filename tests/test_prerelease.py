"""A contract: expected outcomes come from design §2 / implA2 instructions.
All GitHub and Codex calls use executables owned by this fixture.
"""
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
import round_gate as rg
import prerelease as pre

TARGET = 'issue:min-sys/updater-index#1'
NOW = dt.datetime(2026, 11, 13, tzinfo=dt.timezone.utc)
GOAL = '1件 | 根拠: 固定試験 | 取得日: 2026-11-13'


def exe(path, text):
    path.write_text(text)
    path.chmod(0o755)


@pytest.fixture
def case(tmp_path, monkeypatch):
    package = tmp_path / 'package'
    package.mkdir()
    for folder in ('lib', 'bin', 'templates', 'config'):
        shutil.copytree(ROOT / folder, package / folder, ignore=shutil.ignore_patterns('__pycache__'))
    work = tmp_path / 'project'
    work.mkdir()
    def git(*args):
        return pre.git(str(work), *args)
    git('init', '-q')
    git('config', 'user.name', 'Fixture')
    git('config', 'user.email', 'fixture@example.invalid')
    git('remote', 'add', 'origin', 'https://github.com/min-sys/updater-index.git')
    (work / 'policy.md').write_text('pre-release policy fixture\n')
    (work / 'release.md').write_text('unreleased\n')
    (work / 'code.py').write_text('original\n')
    git('add', '.')
    git('commit', '-qm', 'fixture baseline')
    head = git('rev-parse', 'HEAD')
    # A fixture remote ref, without checking out or creating a working branch.
    git('update-ref', 'refs/remotes/origin/main', head)
    registry = package / 'config/prerelease-projects.json'
    registry.write_text(json.dumps([dict(repo='min-sys/updater-index', common_dir=str(work / '.git'),
        default_branch='main', policies={name: git('rev-parse', 'HEAD:' + name)
        for name in ('policy.md', 'release.md')})]))
    (work / 'code.py').write_text('changed\n')
    state = tmp_path / 'state ledger'
    state.mkdir()
    # Normal counting uses the ledger. Two completed, distinct HEADs precede
    # this dispatch; body history alone cannot manufacture the third round.
    for index in (1, 2):
        (state / f'prior-{index}.state').write_text(
            f'run_id=agent-{index}\nreview_target={TARGET}\n'
            f'head_sha={str(index) * 40}\nround={index}\nstarted_at={index}\n')
    data = dict(id='decision-1', authority='project_prerelease', target=TARGET,
        series_id='series-1', kind='コード', head_sha=head, base_sha=head,
        content_hash=rg.git_content_hash(str(work)), files=['code.py'],
        files_hash=hashlib.sha256(b'["code.py"]').hexdigest(), plan='check integration',
        reason='two independent findings need confirmation', rollback='revert source',
        cost='local only', dispatch_reason='verify corrections', history_ref='## 巡の履歴',
        blocking=[], invariants=['keep cap'], remaining_checks=['integration'], predecessors=[],
        round5_options=['縮小', '前身継承で切り出し', '撤回して再設計'],
        total_cap=3, decided_at='2026-11-12T00:00:00+00:00',
        operation='local-read-only-review', explicit_confirmation=False)
    body_file = tmp_path / 'body'
    history = rg.ROUND_SECTION_TITLE + '\n' + rg.ROUND_ROW_HEADER + '\n' + rg.ROUND_ROW_SEP + '\n'
    for index in (1, 2):
        history += rg.render_round_row(index, 'コード', '2026-11-12', str(index) * 7, 'Agent') + f' <!-- dispatch_id=agent-{index} -->\n'
    def body(record=data, suffix=''):
        result = history + '\n## 公開前裁定\n```json\n' + json.dumps(record, ensure_ascii=False) + '\n```\n' + suffix
        body_file.write_text(result)
        return result
    body()
    fake = tmp_path / 'fakebin'
    fake.mkdir()
    exe(fake / 'gh', '''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
a=sys.argv[1:]
if a[0]=='repo':
    if os.environ.get('POLICY_FAIL'): sys.exit(1)
    print('main')
elif a[0]=='api' and '-X' not in a:
    if os.environ.get('POLICY_FAIL'): sys.exit(1)
    print(os.environ['POLICY_COMMIT'])
elif a[0]=='api':
    Path(os.environ['BODY']).write_text(json.load(sys.stdin)['body'])
elif a[:3]==['pr', 'view', '2']:
    print('')
else:
    print(Path(os.environ['BODY']).read_text())
''')
    exe(fake / 'codex', '''#!/usr/bin/env python3
import os,sys
from pathlib import Path
Path(os.environ['SENT']).write_text(sys.stdin.read())
''')
    monkeypatch.setenv('PATH', str(fake) + os.pathsep + os.environ['PATH'])
    for key, value in dict(BODY=str(body_file), SENT=str(tmp_path / 'sent'), POLICY_COMMIT=head,
        CODEX_SUMMARY='#0', CODEX_REVIEW_KIND_LABEL='コード', REVIEW_TARGET=TARGET,
        REVIEW_GOAL_CUT=GOAL, REVIEW_PRERELEASE_RECORD='decision-1', CODEX_WATCH_DIR=str(state)).items():
        monkeypatch.setenv(key, value)
    for key in ('CODEX_REVIEW_NO_GATE', 'CODEX_REVIEW_GATE_CHECK', 'REVIEW_PREDECESSOR', 'REVIEW_MANDATORY_GATE'):
        monkeypatch.delenv(key, raising=False)
    prompt = tmp_path / 'prompt'
    prompt.write_text('点検:\n- 突き合わせ: 済\n- 出所の付記: 済\n- 直し残しの検索: 済\n')
    return dict(package=package, work=work, git=git, data=data, body=body,
                body_file=body_file, state=state, registry=registry, tmp=tmp_path, prompt=prompt)


def run_cli(c, *args):
    return subprocess.run([str(c['package'] / 'bin/codex-review'), str(c['work']), str(c['prompt']), 'fixture'],
                          capture_output=True, text=True, timeout=30)


def evaluate(c, body=None, total=3, data=None):
    return pre.evaluate(rg.parse_target(TARGET), str(c['work']), c['state'],
        body if body is not None else c['body'](data or c['data']), total,
        'decision-1', 'コード', registry=c['registry'], now=NOW)


# First test is the complete successful path, including source completion.
def test_completed_history_round3_dispatch(case):
    c = case
    result = run_cli(c)
    assert result.returncode == 0, result.stdout + result.stderr
    states = list(c['state'].glob('0-fixture-*.state'))
    assert len(states) == 1
    saved = rg.read_state_file(states[0])
    assert saved['round'] == '3'
    assert saved['authority'] == 'project_prerelease'
    reservation = c['state'] / (saved['run_id'] + '.reservation')
    assert rg.read_state_file(reservation)['round'] == '3'
    assert '<!-- dispatch_id=' + saved['run_id'] + ' -->' in c['body_file'].read_text()
    assert pre.history(c['body_file'].read_text(), c['state'], TARGET, strict=True) == 3
    evidence = json.loads(saved['prerelease_evidence'])
    assert evidence['record']['total_cap'] == 3
    assert '3巡目' in Path(saved['effective_prompt']).read_text() or '巡3' in Path(saved['effective_prompt']).read_text() or '第3巡' in Path(saved['effective_prompt']).read_text()


def assert_prerelease_refusal(case, reason, total=3):
    result = run_cli(case)
    assert result.returncode == 4, result.stdout + result.stderr
    assert result.stdout == ''
    lines = result.stderr.splitlines()
    assert len(lines) == 1, result.stderr
    prefix = '巡数ゲートで拒否されました: '
    assert lines[0].startswith(prefix)
    gate = json.loads(lines[0].removeprefix(prefix))
    assert gate['total_round'] == total
    _, actual_reason = gate['message'].split('。公開前特例不成立: ')
    if reason is not None:
        assert actual_reason == reason
    assert not list(case['state'].glob('*.reservation'))
    assert not list(case['state'].glob('0-fixture-*.state'))
    assert not (case['tmp'] / 'sent').exists()
    return actual_reason


@pytest.mark.parametrize('legacy', [False, True], ids=['per-kind', 'legacy'])
def test_startup_reports_missing_dispatch_id(case, legacy):
    suffix = ''
    if legacy:
        # No saved round 4 to attribute and the ledger is at round 3.
        # The legacy count reads the approval, but it has no accompanying cap.
        case['data']['total_cap'] = 4
        suffix = '\n## 承認\n巡4の人間承認\n'
    body = case['body'](suffix=suffix).replace(' <!-- dispatch_id=agent-1 -->', '')
    case['body_file'].write_text(body)
    reason = assert_prerelease_refusal(case, None, total=4 if legacy else 3)
    notice, example = reason.split('実行例: ', 1)
    assert notice == '巡の履歴に発注IDがありません。補完案を確認してください。'
    command, *args = shlex.split(example)
    assert command == str(case['package'] / 'bin/codex-history-backfill')
    assert args[:1] == [TARGET]
    assert args[1:] == ['--state-dir', str(case['state'])]


@pytest.mark.parametrize('source', ['record', 'body'])
def test_startup_reports_inherited_predecessor(case, source):
    if source == 'record':
        case['data']['predecessors'] = ['pr:min-sys/updater-index#2']
        case['body']()
    else:
        case['body'](suffix='\n## 継承\n前身 PR #2 で 設計0巡・コード0巡 消化済み（継承）。\n')
    assert_prerelease_refusal(case, '前身の巡を継承する系列は公開前特例の対象外です')


@pytest.mark.parametrize('malformation', ['broken-row', 'invalid-id'])
def test_startup_does_not_offer_backfill_for_malformed_history(case, malformation):
    body = case['body']()
    first_row = next(line for line in body.splitlines() if line.startswith('| 1 |'))
    replacement = '| 1 |' if malformation == 'broken-row' else first_row.replace('agent-1', 'bad id')
    case['body_file'].write_text(body.replace(first_row, replacement))
    assert_prerelease_refusal(case, '履歴行が不正です')


@pytest.mark.parametrize(('field', 'value', 'reason'), [
    ('blocking', ['unresolved'], 'blockingが残っているため公開前特例の対象外です'),
    ('kind', '設計', '裁定と発注の種別が一致しません'),
], ids=['blocking', 'kind'])
def test_startup_reports_other_prerelease_rejections(case, field, value, reason):
    case['data'][field] = value
    case['body']()
    assert_prerelease_refusal(case, reason)


def test_invalid_review_skill_addition_releases_unused_reservation(case, monkeypatch):
    monkeypatch.setenv('CODEX_SKILLS_FILTER', 'on')
    monkeypatch.setenv('CODEX_SKILLS_ALLOW', 'extra,')
    monkeypatch.delenv('CODEX_REVIEW_ALLOW_SKILLS', raising=False)
    result = run_cli(case)
    assert result.returncode == 2, result.stderr
    assert 'CODEX_SKILLS_ALLOW' in result.stderr
    assert not (case['tmp'] / 'sent').exists()
    assert not list(case['state'].glob('0-fixture-*.state'))
    assert not list(case['state'].glob('0-fixture-*.reservation'))
    assert not list(case['state'].glob('0-fixture-*.prompt.*'))


def test_human_approval_ignores_policy_failure(case, monkeypatch):
    c = case
    (c['state'] / 'third.state').write_text(f'run_id=third\nreview_target={TARGET}\nround=3\nhead_sha={c["data"]["head_sha"]}\n')
    c['body'](suffix='\n巡3の人間承認\n総上限: 3巡\n')
    monkeypatch.setenv('POLICY_FAIL', '1')
    result = run_cli(c)
    assert result.returncode == 0, result.stdout + result.stderr
    saved = rg.read_state_file(next(c['state'].glob('0-fixture-*.state')))
    assert saved['round'] == '3' and saved['authority'] == 'human'
    assert not list(c['state'].glob('*.reservation'))


@pytest.mark.parametrize('mode', ['other-project', 'released', 'missing-policy', 'claim-only', 'wrong-remote'])
def test_authority_boundaries(case, mode, monkeypatch):
    c = case
    if mode == 'other-project':
        rows = json.loads(c['registry'].read_text()); rows[0]['common_dir'] += '-other'
        c['registry'].write_text(json.dumps(rows))
    elif mode in ('released', 'missing-policy'):
        if mode == 'released': (c['work'] / 'release.md').write_text('released\n')
        else: (c['work'] / 'policy.md').unlink()
        c['git']('add', '.')
        c['git']('commit', '-qm', 'fixture publication')
        commit = c['git']('rev-parse', 'HEAD')
        monkeypatch.setenv('POLICY_COMMIT', commit)
    elif mode == 'claim-only':
        c['body_file'].write_text(c['body']().split('## 公開前裁定')[0] + '\nproject_prerelease=true\n')
    else:
        c['git']('remote', 'set-url', 'origin', 'https://github.com/other/repo.git')
    result = run_cli(c)
    assert result.returncode != 0, result.stdout + result.stderr
    assert not list(c['state'].glob('0-fixture-*.state'))
    assert not (c['tmp'] / 'sent').exists()


@pytest.mark.parametrize('total,cap,ok', [(2,3,False),(3,2,False),(3,3,True),(3,5,True),(4,3,False),(4,4,True),(5,5,True),(6,5,False),(3,6,False),(3,True,False),(3,'3',False)])
def test_round_cap_boundaries(case, total, cap, ok):
    data = copy.deepcopy(case['data']); data['total_cap'] = cap
    if ok: pre.validate_record(data, TARGET, total, NOW)
    else:
        with pytest.raises(ValueError): pre.validate_record(data, TARGET, total, NOW)


@pytest.mark.parametrize('key', ['series_id','kind','head_sha','content_hash','files_hash','base_sha','plan','reason','rollback','cost','dispatch_reason','history_ref','blocking','invariants','remaining_checks','predecessors','decided_at','total_cap','operation','explicit_confirmation'])
def test_each_missing_material(case, key):
    data = copy.deepcopy(case['data']); data.pop(key)
    with pytest.raises((ValueError, TypeError)): pre.validate_record(data, TARGET, 3, NOW)


@pytest.mark.parametrize('value', [' ', '\u3000', '\t', '\n'])
def test_whitespace_material(case, value):
    data = copy.deepcopy(case['data']); data['reason'] = value
    with pytest.raises(ValueError): pre.validate_record(data, TARGET, 3, NOW)


@pytest.mark.parametrize('when,ok', [('2026-11-12T00:00:00',False),('2026-11-14T00:00:00+00:00',False),('invalid',False),('2026-11-13T00:00:00+00:00',True),('2026-11-13T09:00:00+09:00',True)])
def test_decision_time(case, when, ok):
    data = copy.deepcopy(case['data']); data['decided_at'] = when
    if ok: pre.validate_record(data, TARGET, 3, NOW)
    else:
        with pytest.raises(ValueError): pre.validate_record(data, TARGET, 3, NOW)


@pytest.mark.parametrize('mode', ['symlink','untracked','files-swap','content-change','blocking','predecessor','duplicate-key','missing-section','malformed-history','missing-id','kind-swap'])
def test_scope_and_history(case, mode):
    c = case; data = copy.deepcopy(c['data']); body = None
    if mode == 'symlink':
        (c['work'] / 'code.py').unlink(); (c['work'] / 'code.py').symlink_to(c['tmp'] / 'prompt')
        data['content_hash'] = rg.git_content_hash(str(c['work']))
    elif mode == 'untracked': (c['work'] / 'new').write_text('unknown')
    elif mode == 'files-swap': data['files'] = ['policy.md']
    elif mode == 'content-change': (c['work'] / 'code.py').write_text('later\n')
    elif mode == 'blocking': data['blocking'] = ['unresolved']
    elif mode == 'predecessor': data['predecessors'] = ['pr:min-sys/updater-index#2']
    elif mode == 'kind-swap': data['kind'] = '設計'
    elif mode == 'duplicate-key': body = c['body']().replace('"plan":', '"plan":"duplicate", "plan":')
    elif mode == 'missing-section': body = c['body']().replace('## 巡の履歴', '## 別節')
    elif mode == 'malformed-history': body = c['body']().replace('| 1 |', 'unreadable')
    else: body = c['body']().replace('<!-- dispatch_id=agent-1 -->', '')
    with pytest.raises((ValueError, rg.Indeterminate)):
        evaluate(c, body=body, data=data)


def test_union_body_only_and_state_only(case):
    c = case
    (c['state'] / 'one.state').write_text(f'run_id=agent-1\nreview_target={TARGET}\nhead_sha={"1"*40}\n')
    (c['state'] / 'three.state').write_text(f'run_id=cli-3\nreview_target={TARGET}\nhead_sha={"3"*40}\n')
    assert pre.history(c['body'](), c['state'], TARGET, strict=True) == 3


def test_bypass_conflict(case):
    with pytest.raises(rg.Indeterminate):
        rg.run_gate(TARGET, str(case['work']), case['state'], '', 'bypass', prerelease_record='decision-1')


def test_recheck_and_reservation(case):
    c = case
    command = [sys.executable, str(c['package'] / 'lib/round_gate.py'), 'gate', '--workdir', str(c['work']), '--json']
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    snapshot = result.stdout
    # Body changes after the first gate, despite semantically identical JSON.
    c['body_file'].write_text(c['body_file'].read_text() + '\n')
    result = subprocess.run(command + ['--snapshot', snapshot, '--reserve-run-id', 'pending-3'], capture_output=True, text=True, timeout=30)
    assert result.returncode == 5
    assert not list(c['state'].glob('*.reservation'))
    # Fresh snapshot reserves once. Reservation stays when no sender follows.
    snapshot = subprocess.run(command, capture_output=True, text=True, timeout=30).stdout
    result = subprocess.run(command + ['--snapshot', snapshot, '--reserve-run-id', 'pending-3'], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run(command + ['--snapshot', snapshot, '--reserve-run-id', 'pending-4'], capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert len(list(c['state'].glob('*.reservation'))) == 1


@pytest.mark.parametrize('mode', ['missing-rule', 'published-rule', 'local-ref-advanced', 'duplicate-state', 'read-failure'])
def test_policy_and_history_fail_closed(case, mode, monkeypatch):
    c = case
    if mode in ('missing-rule', 'published-rule'):
        rows = json.loads(c['registry'].read_text())
        if mode == 'missing-rule': rows[0]['policies']['absent.md'] = 'f' * 40
        else: rows[0]['policies']['release.md'] = 'f' * 40
        c['registry'].write_text(json.dumps(rows))
        with pytest.raises(ValueError): evaluate(c)
    elif mode == 'local-ref-advanced':
        (c['work'] / 'policy.md').write_text('changed policy')
        c['git']('add', 'policy.md'); c['git']('commit', '-qm', 'fixture changed policy')
        c['git']('update-ref', 'refs/remotes/origin/main', c['git']('rev-parse', 'HEAD'))
        with pytest.raises(ValueError, match='未知版'): evaluate(c)
    elif mode == 'duplicate-state':
        (c['state'] / 'corrupt.state').write_text('run_id=old\nrun_id=agent-1\nreview_target=' + TARGET + '\n')
        with pytest.raises(ValueError): evaluate(c)
    else:
        monkeypatch.setenv('POLICY_FAIL', '1')
        result = run_cli(c)
        assert result.returncode != 0
        assert not list(c['state'].glob('*.reservation'))


def test_semantic_positive_control(case):
    c = case
    data = copy.deepcopy(c['data'])
    data['decided_at'] = '2026-11-12T09:00:00+09:00'
    body = c['body'](data).replace('  ', '    ')
    assert evaluate(c, body=body)['authority'] == 'project_prerelease'


def test_simultaneous_reservations(case):
    c = case
    command = [sys.executable, str(c['package'] / 'lib/round_gate.py'), 'gate', '--workdir', str(c['work']), '--json']
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0
    procs = [subprocess.Popen(command + ['--snapshot', result.stdout, '--reserve-run-id', 'race-' + str(n)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for n in (1, 2)]
    outputs = [proc.communicate(timeout=30) for proc in procs]
    assert sorted(proc.returncode for proc in procs) == [0, 5], outputs
    assert len(list(c['state'].glob('*.reservation'))) == 1


@pytest.mark.parametrize('change', ['head', 'policy', 'content', 'api'])
def test_recheck_rejects_changed_sources(case, change, monkeypatch):
    c = case
    command = [sys.executable, str(c['package'] / 'lib/round_gate.py'), 'gate', '--workdir', str(c['work']), '--json']
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0
    if change == 'head':
        c['git']('commit', '--allow-empty', '-qm', 'fixture next version')
    elif change == 'policy':
        (c['work'] / 'release.md').write_text('published')
        c['git']('add', 'release.md'); c['git']('commit', '-qm', 'fixture release')
        monkeypatch.setenv('POLICY_COMMIT', c['git']('rev-parse', 'HEAD'))
    elif change == 'content': (c['work'] / 'code.py').write_text('next')
    else: monkeypatch.setenv('POLICY_FAIL', '1')
    result = subprocess.run(command + ['--snapshot', result.stdout, '--reserve-run-id', 'stale'], capture_output=True, text=True, timeout=30)
    assert result.returncode == 5
    assert not list(c['state'].glob('*.reservation'))


def test_round5_requires_options(case):
    data = copy.deepcopy(case['data']); data['total_cap'] = 5; data.pop('round5_options')
    with pytest.raises(ValueError): pre.validate_record(data, TARGET, 5, NOW)


@pytest.mark.parametrize('field,value', [('series_id','another-series'), ('total_cap',5)])
def test_saved_bundled_cap_cannot_be_raised(case, field, value):
    c = case
    original = copy.deepcopy(c['data'])
    saved = {'record': original}
    (c['state'] / 'agent-1.state').write_text(f'run_id=agent-1\nreview_target={TARGET}\nhead_sha={"1"*40}\nauthority=project_prerelease\nprerelease_evidence=' + json.dumps(saved) + '\n')
    changed = copy.deepcopy(original); changed[field] = value
    with pytest.raises(ValueError, match='固定総上限'): evaluate(c, data=changed)
