"""Build advisory route input from explicit claims; missing evidence stays missing."""
from contextlib import contextmanager
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import tempfile
import time

from history_backfill import backfill
from prerelease import section
from round_gate import Indeterminate, gh_fetch_body, git_head_sha, parse_target, read_state_file

KEYS = ('series_id', 'predecessor_ids', 'base_sha', 'family_tags')
SHA = re.compile(r'(?:[a-f0-9]{40}|[a-f0-9]{64})')
def present(value):
    return (isinstance(value, str) and bool(value.strip())
            and value.strip() not in ('未確認', '未取得', '-')
            and not any(c in value for c in ('\x00', '\r', '\n')))



def valid(key, value):
    if key == 'base_sha':
        return isinstance(value, str) and SHA.fullmatch(value) is not None
    if key in ('predecessor_ids', 'family_tags'):
        return (isinstance(value, list) and (key == 'predecessor_ids' or bool(value))
                and all(present(x) for x in value))
    return present(value)


def structured(text):
    """Unknown keys are ignored; duplicate or malformed known keys remain absent."""
    values = {}
    for line in text.splitlines():
        if not line.startswith('routing-record:'):
            continue
        tail = line[len('routing-record:'):]
        matches = list(re.finditer(r'(?:^|\s)([a-z_]+)=', tail))
        for i, match in enumerate(matches):
            key = match[1]
            if key not in KEYS:
                continue
            raw = tail[match.end():matches[i+1].start() if i+1 < len(matches) else len(tail)].strip()
            try:
                value = json.loads(raw)
            except ValueError:
                value = raw if key in ('series_id', 'base_sha') and not any(c.isspace() for c in raw) else None
            if key in values:
                values[key] = None
            else:
                values[key] = value if valid(key, value) else None
    return {k: v for k, v in values.items() if v is not None}


def declared_keys(text):
    return {m[1] for line in text.splitlines() if line.startswith('routing-record:')
            for m in re.finditer(r'(?:^|\s)([a-z_]+)=', line[len('routing-record:'):])}


def history(body, state_dir, target, run_id):
    """Reuse legacy one-to-one ID matching, then bundle canonical round/kind rows.

    Legacy states contain neither accepted results nor route target identities.
    Do not reinterpret their whole-worktree hashes or report-file existence.
    """
    proposed, warnings = backfill(body, Path(state_dir), target)
    text = section(proposed, '巡の履歴')
    states = {}
    for p in sorted(Path(state_dir).glob('*.state')):
        d = read_state_file(p, strict=True)
        if d.get('review_target') == target:
            states.setdefault(d.get('run_id'), []).append(d)
    groups = {}
    unknown = bool(warnings)
    used = set()
    for line in text.splitlines():
        if not re.match(r'^\|\s*\d+\s*\|', line):
            continue
        cells = [s.strip() for s in line.split('|')[1:8]]
        if len(cells) != 7 or cells[1] not in ('設計', 'コード'):
            unknown = True
            continue
        key = (int(cells[0]), cells[1])
        entries = groups.setdefault(key, [])
        match = re.search(r'<!-- dispatch_id=([A-Za-z0-9_.:-]+) -->$', line)
        rid = match[1] if match and line.count('dispatch_id=') == 1 else None
        candidates = states.get(rid, [])
        if rid in used or rid == run_id or len(candidates) != 1:
            entries.append(None)
            continue
        used.add(rid)
        d = candidates[0]
        fingerprint = [d.get('round'), d.get('kind_label'), d.get('started_at_human'),
                       d.get('head_sha', '')[:7], d.get('reviewer')]
        if fingerprint != cells[:5] or not SHA.fullmatch(d.get('head_sha', '')):
            entries.append(None)
            continue
        tags = [s.strip() for s in cells[6].split(',')]
        entry = dict(event_id=rid, status='pending', target_sha=d['head_sha'])
        if valid('family_tags', tags):
            entry['family_tags'] = tags
        entries.append(entry)
    if any(rid not in used for rid in states):
        unknown = True
    result = []
    if unknown:
        result.append({'missing': True})
    previous = {}
    for (n, kind), entries in groups.items():
        last = previous.get(kind, 0)
        if n <= last or n - last > 10000:
            result.append({'missing': True})
        else:
            for gap in range(last + 1, n):
                result.append(dict(missing=True, round=gap, kind=kind))
        previous[kind] = n
        if not entries or any(e is None for e in entries):
            result.append(dict(missing=True, round=n, kind=kind))
            continue
        event = dict(event_id=entries[0]['event_id'], status='pending')
        heads = {e['target_sha'] for e in entries}
        if len(heads) == 1:
            event['target_sha'] = next(iter(heads))
        if all('family_tags' in e for e in entries):
            event['family_tags'] = sorted({t for e in entries for t in e['family_tags']})
        result.append(event)
    return result


def identity(workdir, base, route, deadline):
    code = ('import {collectChanges,contentIdentity} from ' + json.dumps(Path(route).resolve().as_uri())
            + '; const p=collectChanges(process.argv[1],process.argv[2]).paths;'
              'console.log(JSON.stringify({target_paths:p,...contentIdentity(process.argv[1],process.argv[2],p),'
              'target_sha:(await import("node:child_process")).execFileSync("git",["rev-parse","HEAD"],{cwd:process.argv[1],encoding:"utf8"}).trim()}));')
    child = None
    try:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired('identity', 0)
        child = subprocess.Popen(['node', '--input-type=module', '-e', code, workdir, base],
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
        output, _ = child.communicate(timeout=remaining)
        if child.returncode:
            raise ValueError('identity unavailable')
        return json.loads(output)
    finally:
        if child is not None:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()
            child.stdout.close()


def generate(workdir, target, kind, run_id, state_dir, prompt, route, deadline):
    record = dict(kind={'設計': 'design', 'コード': 'code'}.get(kind),
                  current={'event_id': run_id, 'input_tokens': {'reason': '実入力未測定'}},
                  history_source={'available': False}, history=[{'missing': True}], greens=[])
    reasons = []
    canonical = {}
    declared = set()
    try:
        parsed = parse_target(target)
        body = gh_fetch_body(parsed)
        record['history_source'] = dict(available=True, url=f'https://github.com/{parsed.repo_slug()}/{"issues" if parsed.kind == "issue" else "pull"}/{parsed.number}',
            fetched_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            body_hash=hashlib.sha256(body.encode()).hexdigest())
        canonical = structured(body)
        declared = declared_keys(body)
        try:
            record['history'] = history(body, state_dir, target, run_id)
        except (OSError, ValueError, RuntimeError, Indeterminate):
            reasons.append('履歴照合失敗')
    except (OSError, ValueError, RuntimeError, Indeterminate):
        reasons.append('正本取得失敗')
    supplied = structured(prompt)
    for key in KEYS:
        if key in declared:
            if key in supplied and supplied[key] != canonical.get(key):
                reasons.append('正本と依頼文の項目不一致')
            value = canonical.get(key)
        else:
            value = supplied.get(key)
        if value is not None:
            if key == 'family_tags':
                record['current'][key] = value
            else:
                record[key] = value
    if (record['history_source']['available'] and record['history'] == []
            and record.get('predecessor_ids') == []):
        record['current'].setdefault('family_tags', ['initial'])
    try:
        head = git_head_sha(workdir)
        if SHA.fullmatch(head):
            record['current']['target_sha'] = head
    except (OSError, ValueError, RuntimeError, Indeterminate):
        reasons.append('対象SHA未取得')
    try:
        if 'base_sha' not in record:
            raise ValueError('base missing')
        data = identity(workdir, record['base_sha'], route, deadline)
        record['target_paths'] = data.pop('target_paths')
        record['current'].update({k: data[k] for k in ('content_hash', 'target_list_hash', 'target_sha')})
    except (OSError, ValueError, KeyError):
        reasons.append('対象同一性未取得')
    return record, list(dict.fromkeys(reasons))


def checked_parent(path):
    parent = Path(path).parent
    info = parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError('temporary directory ownership')
    return parent


def write_record(path, record):
    parent = checked_parent(path)
    fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        out = os.open(Path(path).name, os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            info = os.fstat(out)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1:
                raise ValueError('temporary file ownership')
            data = json.dumps(record, ensure_ascii=True).encode()
            os.ftruncate(out, 0)
            with os.fdopen(out, 'wb', closefd=False) as stream:
                stream.write(data)
        finally:
            os.close(out)
    finally:
        os.close(fd)


@contextmanager
def record_path(enabled):
    """The supervising parent owns cleanup, even when its worker is killed."""
    if 'REVIEW_GATE_RECORD' in os.environ or not enabled:
        yield os.environ.get('REVIEW_GATE_RECORD', '')
        return
    directory = Path(tempfile.mkdtemp(prefix='routing-record-'))
    checked_parent(directory / 'record.json')
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    owned = os.fstat(fd)
    try:
        out = os.open('record.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        os.close(out)
        yield str(directory / 'record.json')
    finally:
        try:
            os.unlink('record.json', dir_fd=fd)
        except FileNotFoundError:
            pass
        os.close(fd)
        try:
            now = directory.lstat()
            if (now.st_dev, now.st_ino) == (owned.st_dev, owned.st_ino):
                directory.rmdir()
        except FileNotFoundError:
            pass
