"""Read the Codex exec header and stream rollout records."""
from contextlib import closing
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


SESSION_ID = re.compile(r"^session id: ([0-9a-zA-Z-]+)[ \t]*$", re.MULTILINE)
LOG_VERSION = re.compile(r"OpenAI Codex v(\S+)")


def codex_sessions():
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "sessions"


def session_from(text):
    match = SESSION_ID.search(text)
    return match[1] if match else None


def log_header(path):
    try:
        with path.open(encoding="utf-8", errors="replace") as stream:
            first = LOG_VERSION.fullmatch(stream.readline().rstrip())
            if first is None or stream.readline().rstrip() != "--------":
                return None, None, None
            fields = {}
            for _ in range(198):
                line = stream.readline().rstrip()
                if line == "--------":
                    return first[1], fields.get("model"), session_from(
                        "session id: " + fields.get("session id", "")
                    )
                if not line:
                    break
                key, sep, value = line.partition(": ")
                if sep:
                    fields.setdefault(key, value)
    except OSError:
        pass
    return None, None, None


def find_rollout(sessions, session_id):
    return find_rollouts(sessions, {session_id}).get(session_id) if session_id else None


def find_rollouts(sessions, session_ids):
    """Match rollout filenames in one traversal per suffix; prefer the plain file."""
    remaining = set(session_ids)
    result = {}
    lengths = {len(session_id) for session_id in remaining}
    for suffix in (".jsonl", ".jsonl.zst"):
        if not remaining:
            break
        for path in sessions.rglob(f"rollout-*{suffix}"):
            stem = path.name[len("rollout-"):-len(suffix)]
            for length in lengths:
                session_id = stem[-length:]
                if session_id in remaining:
                    result[session_id] = path
                    remaining.remove(session_id)
            if not remaining:
                break
    return result


def records(path):
    """Yield payloads without loading the full session or creating an expanded file."""
    if path is None:
        return
    if path.suffix != ".zst":
        with path.open(encoding="utf-8", errors="replace") as stream:
            yield from json_payloads(stream)
        return
    zstd = shutil.which("zstd")
    if zstd is None:
        return
    with subprocess.Popen([zstd, "-dc", "--", str(path)], stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, encoding="utf-8", errors="replace") as process:
        with closing(process.stdout) as stream:
            yield from json_payloads(stream)
        if process.wait():
            raise OSError(f"zstd: cannot read {path}")


def json_payloads(stream):
    for line in stream:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and isinstance(record.get("payload"), dict):
            yield record["payload"]
