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
from round_gate import check_receipt, Indeterminate, gh_fetch_body, git_head_sha, parse_target, read_state_file

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


def fields(tail):
    """Find assignments only outside JSON strings and arrays/objects."""
    quoted = False
    depth = 0
    for match in re.finditer(r'"|\\|[\[\]{}]|(?:^|\s)([a-z_]+)=', tail):
        token = match[0]
        # Include intervening ordinary characters when deciding escape parity.
        if quoted:
            if token == '"':
                preceding = len(tail[:match.start()]) - len(tail[:match.start()].rstrip('\\'))
                if preceding % 2 == 0:
                    quoted = False
            continue
        if token == '"':
            quoted = True
        elif token in ('[', '{'):
            depth += 1
        elif token in (']', '}'):
            depth = max(0, depth - 1)
        elif match[1] is not None and depth == 0:
            yield match


def structured(text):
    """Unknown keys are ignored; duplicate or malformed known keys remain absent."""
    values = {}
    for line in text.splitlines():
        if not line.startswith('routing-record:'):
            continue
        tail = line[len('routing-record:'):]
        matches = list(fields(tail))
        for i, match in enumerate(matches):
            key = match[1]
            if key not in KEYS:
                continue
            raw = tail[match.end():matches[i+1].start() if i+1 < len(matches) else len(tail)].strip()
            try:
                value = json.loads(raw)
            except ValueError:
                value = raw if key in ('series_id', 'base_sha') and not raw.startswith(('\"', '[', '{')) and not any(c.isspace() for c in raw) else None
            if key in values:
                values[key] = None
            else:
                values[key] = value if valid(key, value) else None
    return {k: v for k, v in values.items() if v is not None}


def declared_keys(text):
    return {m[1] for line in text.splitlines() if line.startswith('routing-record:')
            for m in fields(line[len('routing-record:'):])}


def receipt_rows(text):
    """Strict JSON and one receipt per dispatch; duplicates cannot overwrite."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result
    def non_json(_):
        raise ValueError('non JSON constant')
    rows = {}
    malformed = False
    for line in text.splitlines():
        if not line.startswith('routing-receipt:'):
            continue
        try:
            value = json.loads(line[len('routing-receipt:'):], object_pairs_hook=unique, parse_constant=non_json)
            if not isinstance(value, dict) or not present(value.get('dispatch_id')):
                raise ValueError('receipt shape')
            rid = value['dispatch_id']
            rows[rid] = None if rid in rows else value
        except (ValueError, TypeError):
            malformed = True
    return ({} if malformed else rows), malformed


def received_fields(d, receipt, reasons):
    """Return only verified fields; discard check_receipt's untrusted reason."""
    if receipt is None or receipt.get('status') != 'received':
        return {}
    fields = {}
    tags = receipt.get('finding_family_tags')
    if valid('family_tags', tags):
        fields['finding_family_tags'] = tags
    route_hash = d.get('route_content_hash', '')
    if (re.fullmatch(r'[a-f0-9]{64}', route_hash)
            and receipt.get('route_content_hash') == route_hash):
        fields['content_hash'] = route_hash
    try:
        with Path(d['report']).open(newline='') as report_file:
            report = report_file.read()
        checked = check_receipt(d.get('head_sha', ''), d.get('content_hash', ''), report)
        ok = checked.status == 'ok'
    except (OSError, ValueError, KeyError):
        ok = False
    if not ok:
        reasons.append('受領照合失敗')
        return {}
    if len(fields) == 2:
        fields['status'] = 'received'
    return fields


def history(body, state_dir, target, run_id, reasons=None):
    """Bundle only complete, uniquely matched receipt evidence per round."""
    if reasons is None:
        reasons = []
    receipts, malformed = receipt_rows(section(body, '巡の履歴'))
    legacy_body = ''.join(line for line in body.splitlines(keepends=True)
                          if not line.startswith('routing-receipt:'))
    proposed, warnings = backfill(legacy_body, Path(state_dir), target)
    text = section(proposed, '巡の履歴')
    states = {}
    for p in sorted(Path(state_dir).glob('*.state')):
        d = read_state_file(p, strict=True)
        if d.get('review_target') == target:
            states.setdefault(d.get('run_id'), []).append(d)
    groups = {}
    unknown = bool(warnings) or malformed
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
        entry.update(received_fields(d, receipts.get(rid), reasons))
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
        hashes = {e.get('content_hash') for e in entries}
        if (all(e['status'] == 'received' and 'family_tags' in e for e in entries)
                and len(heads) == 1 and len(hashes) == 1):
            event.update(status='received', content_hash=next(iter(hashes)),
                         finding_family_tags=sorted({t for e in entries for t in e['finding_family_tags']}))
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
            record['history'] = history(body, state_dir, target, run_id, reasons)
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


class OwnedRecord(str):
    """A path plus the supervisor's still-open directory and file identity."""
    def __new__(cls, path, dir_fd, file_dev, file_ino):
        value = super().__new__(cls, path)
        value.dir_fd = int(dir_fd)
        value.file_identity = (int(file_dev), int(file_ino))
        parent = os.fstat(value.dir_fd)
        value.parent_identity = (parent.st_dev, parent.st_ino)
        return value


def check_record(path, out=None):
    parent = checked_parent(path).lstat()
    if (parent.st_dev, parent.st_ino) != path.parent_identity:
        raise ValueError('temporary directory replaced')
    if out is None:
        fd = os.open(Path(path).name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=path.dir_fd)
        try:
            check_record(path, fd)
        finally:
            os.close(fd)
        return
    info = os.fstat(out)
    if ((info.st_dev, info.st_ino) != path.file_identity
            or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
        raise ValueError('temporary file replaced')


def write_record(path, record):
    out = os.open(Path(path).name, os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=path.dir_fd)
    try:
        check_record(path, out)
        data = json.dumps(record, ensure_ascii=True).encode()
        os.ftruncate(out, 0)
        with os.fdopen(out, 'wb', closefd=False) as stream:
            stream.write(data)
    finally:
        os.close(out)


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
    out = None
    try:
        out = os.open('record.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        info = os.fstat(out)
        yield OwnedRecord(str(directory / 'record.json'), fd, info.st_dev, info.st_ino)
    finally:
        try:
            os.unlink('record.json', dir_fd=fd)
        except FileNotFoundError:
            pass
        if out is not None:
            os.close(out)
        os.close(fd)
        try:
            now = directory.lstat()
            if (now.st_dev, now.st_ino) == (owned.st_dev, owned.st_ino):
                directory.rmdir()
        except FileNotFoundError:
            pass
