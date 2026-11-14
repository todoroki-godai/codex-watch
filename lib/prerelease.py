"""A: registered project policy and source-bound round-three recommendation.

Only run_gate calls this boundary. No environment value grants authority.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import subprocess
from pathlib import Path

REGISTRY = Path(__file__).resolve().parents[1] / 'config/prerelease-projects.json'
RE_ID = re.compile(r'[A-Za-z0-9_.:-]{1,160}')


def command(*args: str) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise ValueError('正本を取得できません: ' + args[0])
    return result.stdout.strip()


def git(workdir: str, *args: str) -> str:
    return command('git', '-C', workdir, *args)


def section(body: str, title: str) -> str:
    matches = list(re.finditer(r'^## ' + re.escape(title) + r'\s*$', body, re.M))
    if len(matches) != 1:
        raise ValueError(title + '節が無い、または重複しています')
    tail = body[matches[0].end():]
    return re.split(r'^## ', tail, maxsplit=1, flags=re.M)[0]


class ConflictingHistory(ValueError):
    """A dispatch identity has contradictory source rows; approval cannot waive it."""


def history(body: str, state_dir: Path, target: str, *, strict: bool,
            kind_label: str = 'コード', pending_head: str | None = None) -> int:
    """Reconcile dispatch identities before counting same-kind distinct HEADs."""
    from round_gate import read_state_file, ROUND_ROW_HEADER
    text = section(body, '巡の履歴')
    rows_by_id: dict[str, list[str]] = {}
    records: dict[str, tuple[str, str]] = {}
    for line in text.splitlines():
        line = line.strip()
        has_id = 'dispatch_id=' in line
        match = re.search(r'<!-- dispatch_id=([A-Za-z0-9_.:-]+) -->$', line)
        if not has_id and (not line or line == ROUND_ROW_HEADER or
                re.fullmatch(r'\|(?:\s*:?-{3,}:?\s*\|)+', line) or not line.startswith('|')):
            continue
        if not re.match(r'^\|\s*[0-9]+\s*\|', line) or not match:
            raise ValueError('履歴行が不正または dispatch_id の補完が必要です')
        if line.count('dispatch_id=') != 1 or not line[:match.start()].rstrip().endswith('|') or not RE_ID.fullmatch(match[1]):
            raise ValueError('履歴行の発注IDが不正です')
        cells = [cell.strip() for cell in line[:match.start()].split('|')[1:-1]]
        if len(cells) != 7 or cells[1] not in ('設計', 'コード') or not re.fullmatch(r'[0-9a-f]{7,40}', cells[3]):
            raise ValueError('履歴行の種別・HEAD・列が不正です')
        fingerprint = cells[:5]
        if match[1] in rows_by_id and rows_by_id[match[1]] != fingerprint:
            raise ConflictingHistory('同じ発注IDの履歴内容が矛盾しています')
        rows_by_id[match[1]] = fingerprint
    for path in sorted(state_dir.iterdir()):
        if path.suffix not in ('.state', '.reservation'):
            continue
        lines = path.read_text().splitlines()
        keys = [line.partition('=')[0] for line in lines]
        if any('=' not in line for line in lines) or len(keys) != len(set(keys)):
            raise ValueError('stateが破損またはキー重複です')
        data = read_state_file(path, strict=True)
        if data.get('review_target') != target:
            continue
        run_id = data.get('run_id', '')
        if not RE_ID.fullmatch(run_id):
            raise ValueError('stateに発注IDがありません')
        evidence = json.loads(data.get('prerelease_evidence') or '{}').get('record', {})
        kind = data.get('kind_label', evidence.get('kind', 'コード'))
        head = data.get('head_sha') or evidence.get('head_sha', '')
        if kind not in ('設計', 'コード') or not re.fullmatch(r'[0-9a-f]{40}', head):
            raise ValueError('stateの種別・完全HEADが不正です')
        if run_id in records and records[run_id] != (kind, head):
            raise ConflictingHistory('同じ発注IDのstateが矛盾しています')
        records[run_id] = (kind, head)
    full_heads = {head for _, head in records.values()}
    full_heads.update(row[3] for row in rows_by_id.values() if len(row[3]) == 40)
    for run_id, row in rows_by_id.items():
        kind, short = row[1], row[3]
        if run_id in records:
            saved_kind, head = records[run_id]
            if kind != saved_kind or not head.startswith(short):
                raise ConflictingHistory('履歴とstateの種別・HEADが矛盾しています')
        else:
            candidates = {head for head in full_heads if head.startswith(short)}
            if len(candidates) != 1:
                raise ValueError('履歴の短縮HEADを一意に照合できません')
            records[run_id] = (kind, next(iter(candidates)))
    heads = {head for kind, head in records.values() if kind == kind_label}
    if pending_head is not None:
        heads.add(pending_head)
    return len(heads)


def record(body: str, record_id: str) -> dict:
    text = section(body, '公開前裁定').strip()
    match = re.fullmatch(r'```json\s*\n(.*?)\n```', text, re.S)
    if not match:
        raise ValueError('公開前裁定は単一JSONブロックが必要です')
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError('裁定のキーが重複しています')
            out[key] = value
        return out
    data = json.loads(match[1], object_pairs_hook=unique)
    if not isinstance(data, dict):
        raise ValueError('裁定はJSON objectが必要です')
    if data.get('id') != record_id or not RE_ID.fullmatch(record_id):
        raise ValueError('裁定の参照IDが一致しません')
    return data


def validate_record(data: dict, target: str, total: int, now: dt.datetime) -> None:
    if data.get('authority') != 'project_prerelease' or data.get('target') != target:
        raise ValueError('裁定の権限または対象が一致しません')
    for key in ('series_id', 'kind', 'head_sha', 'content_hash', 'files_hash', 'base_sha',
                'plan', 'reason', 'rollback', 'cost', 'dispatch_reason', 'history_ref'):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError('裁定の必須欄が空です: ' + key)
    for key in ('blocking', 'invariants', 'remaining_checks', 'predecessors'):
        if not isinstance(data.get(key), list):
            raise ValueError('裁定の配列がありません: ' + key)
        if any(not isinstance(item, str) or not item.strip() for item in data[key]):
            raise ValueError('裁定の配列要素が空です: ' + key)
    if data['blocking'] or data['predecessors']:
        raise ValueError('blocking残存・前身系列はAの特例対象外です')
    if type(data.get('total_cap')) is not int or not 3 <= total <= data['total_cap'] <= 5:
        raise ValueError('公開前裁定は巡3〜5、固定総上限3〜5だけです')
    if total == 5 and data.get('round5_options') != ['縮小', '前身継承で切り出し', '撤回して再設計']:
        raise ValueError('巡5には縮小・切り出し・撤回の3択の記録が必要です')
    when = dt.datetime.fromisoformat(data.get('decided_at', ''))
    if when.tzinfo is None or when > now:
        raise ValueError('判断時刻はtimezone付きで現在以前にしてください')
    if data.get('operation') != 'local-read-only-review' or data.get('explicit_confirmation') is not False:
        raise ValueError('対象操作はローカル読取レビューだけです')
    if data['history_ref'] != '## 巡の履歴':
        raise ValueError('履歴参照が一致しません')


def evaluate(target, workdir: str, state_dir: Path, body: str, total: int,
             record_id: str, kind: str, *, registry: Path = REGISTRY,
             now: dt.datetime | None = None) -> dict:
    from round_gate import git_content_hash, parse_inherited_pr_numbers
    now = now or dt.datetime.now(dt.timezone.utc)
    rows = json.loads(registry.read_text())
    common = Path(git(workdir, 'rev-parse', '--path-format=absolute', '--git-common-dir')).resolve()
    matches = [row for row in rows if row['repo'] == target.repo_slug()
               and Path(row['common_dir']).resolve() == common]
    if len(matches) != 1:
        raise ValueError('固定登録のPJ実体と一致しません')
    project = matches[0]
    branch = command('gh', 'repo', 'view', target.repo_slug(), '--json', 'defaultBranchRef',
                     '-q', '.defaultBranchRef.name')
    if branch != project['default_branch']:
        raise ValueError('既定枝が固定登録と一致しません')
    commit = command('gh', 'api', f'repos/{target.repo_slug()}/commits/{branch}', '--jq', '.sha')
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('既定枝commitを取得できません')
    for path, expected in project['policies'].items():
        for ref in (f'origin/{branch}', commit):
            if git(workdir, 'rev-parse', f'{ref}:{path}') != expected:
                raise ValueError('公開終了・規則欠落・未知版です')
            entry = git(workdir, 'ls-tree', ref, '--', path).split()
            if not entry or entry[0] != '100644':
                raise ValueError('規則は追跡された通常ファイルだけです')
    data = record(body, record_id)
    validate_record(data, target.key(), total, now)
    if data['kind'] != kind or parse_inherited_pr_numbers(body):
        raise ValueError('種別不一致・前身系列はAの特例対象外です')
    if history(body, state_dir, target.key(), strict=True, kind_label=kind,
               pending_head=git(workdir, 'rev-parse', 'HEAD')) != total:
        raise ValueError('正本履歴と判定巡が一致しません')
    # A supports the original bundled cap, not an implicit per-round increase.
    from round_gate import read_state_file
    for path in state_dir.iterdir():
        if path.suffix not in ('.state', '.reservation'):
            continue
        saved = read_state_file(path, strict=True)
        if saved.get('review_target') != target.key() or saved.get('authority') != 'project_prerelease':
            continue
        prior = json.loads(saved['prerelease_evidence'])['record']
        if prior['series_id'] != data['series_id'] or prior['total_cap'] != data['total_cap']:
            raise ValueError('系列・固定総上限の変更はAの特例対象外です。再裁定が必要です')
    head = git(workdir, 'rev-parse', 'HEAD')
    if data['head_sha'] != head or data['content_hash'] != git_content_hash(workdir):
        raise ValueError('裁定の対象版と現在の内容が一致しません')
    base = data['base_sha']
    if not re.fullmatch('[0-9a-f]{40}', base):
        raise ValueError('系列基点はcommit SHAで指定してください')
    git(workdir, 'merge-base', '--is-ancestor', base, head)
    if git(workdir, 'ls-files', '--others', '--exclude-standard'):
        raise ValueError('未追跡ファイルを含む対象は列挙できません')
    # NUL-delimited paths preserve spaces and reject ambiguous/control names.
    changed = git(workdir, 'diff', '--name-only', '-z', base, '--').strip('\0').split('\0')
    files = data.get('files')
    if not isinstance(files, list) or not files or sorted(files) != sorted(changed) or len(set(files)) != len(files):
        raise ValueError('裁定対象一覧と系列差分が一致しません')
    root = Path(git(workdir, 'rev-parse', '--show-toplevel')).resolve()
    for name in files:
        if not isinstance(name, str) or not name or not name.splitlines() == [name]:
            raise ValueError('対象パスが不正です')
        path = root / name
        if Path(name).is_absolute() or '..' in Path(name).parts or not path.resolve().is_relative_to(root):
            raise ValueError('PJ外の対象は許可しません')
        if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents) if p != root):
            raise ValueError('symlink・削除・非通常ファイルは対象外です')
        if git(str(path.parent), 'rev-parse', '--show-toplevel') != str(root):
            raise ValueError('別repoの対象は許可しません')
    digest = hashlib.sha256(json.dumps(sorted(files), ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    if data['files_hash'] != digest:
        raise ValueError('対象一覧hashが一致しません')
    return {'authority': 'project_prerelease', 'policy_commit': commit,
            'policy_blobs': project['policies'], 'body_hash': hashlib.sha256(body.encode()).hexdigest(),
            'content_hash': data['content_hash'], 'record': data}
