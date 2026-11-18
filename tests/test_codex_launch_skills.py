"""Both launchers with a fake Codex protocol peer, credentials and HOME."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import tomllib

import pytest

ROOT = Path(os.environ.get("CODEX_SKILLS_TEST_ROOT", Path(__file__).resolve().parents[1]))
SANDBOX = "/usr/bin/sandbox-exec"
PROMPT = """直しの出所: なし
dummy prompt
見込み: 1分
点検:
- 突き合わせ: 確認済
- 出所の付記: 確認済
- 直し残しの検索: 確認済
"""
FAKE_CODEX = r'''
import json, os, pathlib, sys, time
root = pathlib.Path(__file__).resolve().parent.parent
home = pathlib.Path(os.environ['HOME'])
source = home / '.codex'
args = sys.argv[1:]
variant = (root / 'variant').read_text()
if args == ['--version']:
    (root / 'version-called').touch()
    print('unknown' if variant == 'bad-version' else
          'codex-cli 0.169.2' if variant == 'new-version' else 'codex-cli 0.169.1')
elif 'app-server' in args:
    scan = pathlib.Path(os.environ['CODEX_HOME'])
    probe = scan / 'probe'
    probe.mkdir()
    # Use files inside the scratch area for fixture observations. Only the simulated
    # sandbox writes to the fixture root, and only when OS isolation is not under test.
    assert scan != source
    assert (scan / 'config.toml').read_bytes() == (source / 'config.toml').read_bytes()
    assert not any((scan / part).exists() for part in ('auth.json', 'sessions', 'memories'))
    assert 'OPENAI_API_KEY' not in os.environ
    assert 'GH_TOKEN' not in os.environ
    assert 'AWS_SECRET_ACCESS_KEY' not in os.environ
    assert '-C' not in args
    for line in sys.stdin:
        msg = json.loads(line)
        method = msg['method']
        if method == 'initialize':
            print(json.dumps({'id': msg['id'], 'result': {'userAgent': 'fake'}}), flush=True)
        elif method == 'initialized':
            assert 'id' not in msg
        else:
            assert method == 'skills/list'
            work = root / 'project' / 'nested'
            assert pathlib.Path.cwd() == work
            assert msg['params'] == {'cwds': [str(work)], 'forceReload': True}
            if variant == 'timeout':
                time.sleep(30)
            if variant == 'change-config':
                (source / 'config.toml').write_text('# changed during scan\n')
            rows = json.loads((root / 'inventory').read_text())
            for row in rows:
                if row['path'].startswith('@'):
                    row['path'] = str(scan / row['path'][1:])
            reply = dict(cwd=str(work), errors=[], skills=rows)
            if variant == 'partial':
                reply['errors'] = [{'message': 'private config content', 'path': '/private'}]
            if variant == 'missing':
                del reply['errors']
            print(json.dumps({'method': 'skills/changed'}), flush=True)
            print(json.dumps({'id': msg['id'], 'result': {'data': [reply]}}), flush=True)
elif args[0] == 'exec':
    payload = {'argv': args, 'prompt': sys.stdin.read()}
    (root / 'capture.tmp').write_text(json.dumps(payload))
    (root / 'capture.tmp').replace(root / 'capture')
    if variant == 'child-error':
        sys.exit('test config error')
else:
    sys.exit('unexpected Codex route')
'''


def executable(path, code):
    path.write_text(f"#!{sys.executable}\n{code}")
    path.chmod(0o755)


@pytest.fixture
def launch(tmp_path):
    root = tmp_path.resolve()
    home = root / "home"
    codex_home = home / ".codex"
    work = root / "project/nested"
    work.mkdir(parents=True)
    codex_home.mkdir(parents=True)
    temp = root / "scan-tmp"
    temp.mkdir()
    fake = root / "fake-bin"
    fake.mkdir()
    repo = root / "wrapper"
    shutil.copytree(ROOT / "bin", repo / "bin")
    shutil.copytree(ROOT / "lib", repo / "lib", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "templates", repo / "templates")
    common = repo / "bin/_codex_common.sh"
    shim = fake / "sandbox"
    common.write_text(common.read_text().replace(SANDBOX, str(shim)).replace(
        "SCAN_TIMEOUT = 15", "SCAN_TIMEOUT = 1"))
    executable(shim, """
import os, pathlib, sys
root = pathlib.Path(__file__).resolve().parent.parent
(root / 'scan-called').touch()
(root / 'scratch').write_text(os.environ['CODEX_HOME'])
assert sys.argv[1] == '-p'
os.execv(sys.argv[3], sys.argv[3:])
""")
    executable(fake / "codex", FAKE_CODEX)
    executable(fake / "aws", """
import json, sys
if sys.argv[1] == 'sts':
    print('669126230735')
else:
    print(json.dumps({'Version': 1, 'AccessKeyId': 'test', 'SecretAccessKey': 'test',
                      'SessionToken': 'test', 'Expiration': '2099-01-02T03:04:05Z'}))
""")
    executable(fake / "gh", "raise SystemExit('unexpected GitHub call')")
    prompt = root / "prompt"
    prompt.write_text(PROMPT)
    (codex_home / "config.toml").write_text("[skills]\n")
    for path in ("auth.json", "sessions/canary", "memories/canary"):
        target = codex_home / path
        target.parent.mkdir(exist_ok=True)
        target.write_text("private fixture data")
    inventory = []

    def skill(name, rel, *, scope="user", plugin=None, enabled=True, link=None):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if link:
            path.symlink_to(link)
        else:
            path.write_text(name)
        listed = "@" + str(path.relative_to(codex_home)) if path.is_relative_to(codex_home) else str(path)
        inventory.append(dict(name=name, path=listed, scope=scope, enabled=enabled, pluginId=plugin))
        return path

    env = dict(HOME=str(home), TMPDIR=str(temp), PATH=f"{fake}:{os.environ['PATH']}",
               CODEX_WATCH_DIR=str(root / "state"), CODEX_SUMMARY="#0",
               CODEX_IMPL_ALLOW_MAIN="1", CODEX_IMPL_ALLOW_MISSING_NODE_MODULES="1",
               CODEX_REVIEW_KIND_LABEL="コード", CODEX_REVIEW_NO_GATE="local test",
               OPENAI_API_KEY="fixture-key", GH_TOKEN="fixture-token", AWS_SECRET_ACCESS_KEY="fixture-secret")

    def run(kind, variant="", **settings):
        for name in ("capture", "version-called", "scan-called", "scratch"):
            (root / name).unlink(missing_ok=True)
        (root / "inventory").write_text(json.dumps(inventory))
        (root / "variant").write_text(variant)
        return subprocess.run(
            ["bash", str(repo / f"bin/codex-{kind}"), str(work), str(prompt), "test"],
            cwd=root, env={**env, **settings}, capture_output=True, text=True, timeout=12,
        )

    def child(result):
        assert result.returncode == 0, result.stderr
        deadline = time.monotonic() + 4
        while not (root / "capture").exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        return json.loads((root / "capture").read_text())

    return root, skill, inventory, run, child, env


def configs(child):
    args = child["argv"]
    return {key: value for n, arg in enumerate(args) if arg == "-c"
            for key, value in tomllib.loads(args[n + 1]).items() if key in ("skills", "memories")}


@pytest.mark.parametrize("kind", ["impl", "review"])
def test_default_filters_skills_and_memories(launch, kind):
    root, skill, _, run, child, _ = launch
    commit = skill("commit", "home/.claude/skills/commit/SKILL.md")
    skill("commit", "home/.agents/skills/commit/SKILL.md", link=commit)
    normal = skill("agent-browser", "home/.agents/skills/agent-browser/SKILL.md")
    duplicate = skill("agent-browser", "home/.agents/skills/agent-browser.backup/SKILL.md")
    extra = skill("explicit", 'project/nested/.agents/skills/空 白 " and \\ /SKILL.md', scope="repo")
    off = skill("disabled", "home/.codex/skills/disabled/SKILL.md", enabled=False)
    old = skill("pdf:pdf", "home/.codex/plugins/cache/other/pdf/1/skills/pdf/SKILL.md", plugin="pdf@other")
    skill("pdf:pdf", "home/.codex/plugins/cache/openai-primary-runtime/pdf/2/skills/pdf/SKILL.md",
          plugin="pdf@openai-primary-runtime")
    system = skill("system", "home/.codex/skills/.system/system/SKILL.md", scope="system")
    admin = skill("admin", "admin/skills/admin/SKILL.md", scope="admin")
    ancestor = skill("ancestor", "project/.agents/skills/ancestor/SKILL.md", scope="repo")
    before = {p: p.stat().st_mtime_ns for p in (commit, normal, off, root / "home/.codex/config.toml")}
    observed = child(run(kind, CODEX_SKILLS_ALLOW=" explicit,explicit "))
    values = configs(observed)
    blocked = {Path(s["path"]) for s in values["skills"]["config"] if s["enabled"] is False}
    assert blocked == {duplicate, old, system, admin, ancestor}
    assert extra not in blocked
    assert values["memories"] == {"use_memories": False}
    assert observed["argv"][1:3] == ["-C", str(root / "project/nested")]
    assert ("を読み込んではならない" in observed["prompt"]) == (kind == "review")
    assert {p: p.stat().st_mtime_ns for p in before} == before
    assert (root / "home/.agents/skills/commit/SKILL.md").readlink() == commit
    assert not Path((root / "scratch").read_text()).exists()


@pytest.mark.parametrize("kind", ["impl", "review"])
def test_off_preserves_legacy_args(launch, kind):
    root, _, _, run, child, _ = launch
    args = child(run(kind, "new-version", CODEX_SKILLS_FILTER="off"))["argv"]
    common = ["exec", "-C", str(root / "project/nested")]
    options = ["-s", "read-only"] if kind == "review" else [
        "-c", 'default_permissions="codex-impl-dev"',
        "-c", 'permissions.codex-impl-dev.extends=":workspace"',
        "-c", 'permissions.codex-impl-dev.network.enabled=true',
        "-c", 'shell_environment_policy.inherit="all"',
        "-c", 'shell_environment_policy.ignore_default_excludes=true',
        "-c", 'shell_environment_policy.set.AWS_PROFILE="codex-dev"',
        "-c", 'permissions.codex-impl-dev.filesystem={"~/.aws"="deny"}',
        "-m", "gpt-6.1-sol", "-c", 'model_reasoning_effort="medium"',
    ]
    assert args == [*common, *options, "-o", args[-2], "-"]
    assert not (root / "version-called").exists()
    assert not (root / "scan-called").exists()


def test_review_linked_extra_rejected_or_explicitly_allowed(launch):
    root, skill, _, run, child, _ = launch
    actual = skill("target", "home/.agents/skills/title/SKILL.md")
    skill("linked", "project/nested/.agents/skills/alias/SKILL.md", scope="repo", link=actual)
    result = run("review", CODEX_SKILLS_ALLOW="linked")
    assert result.returncode != 0, "review launched a forbidden linked skill"
    assert "linked" in result.stderr and "CODEX_REVIEW_ALLOW_SKILLS=1" in result.stderr
    assert not (root / "capture").exists()
    observed = child(run("review", CODEX_SKILLS_ALLOW="linked", CODEX_REVIEW_ALLOW_SKILLS="1"))
    assert configs(observed)["skills"] == {"config": []}
    assert "を読み込んではならない" not in observed["prompt"]
    assert PROMPT in observed["prompt"]


def test_review_link_from_agents_to_claude_is_allowed(launch):
    _, skill, _, run, child, _ = launch
    actual = skill("extra", "home/.claude/skills/extra/SKILL.md")
    skill("extra", "home/.agents/skills/extra/SKILL.md", link=actual)
    observed = child(run("review", CODEX_SKILLS_ALLOW="extra", CODEX_MEMORIES="keep"))
    assert configs(observed) == {"skills": {"config": []}}


@pytest.mark.parametrize("kind", ["impl", "review"])
@pytest.mark.parametrize(("variant", "message", "scanned"), [
    ("new-version", "0.169.2", False), ("bad-version", "版", False),
    ("partial", "探索エラー", True), ("missing", "応答", True),
    ("timeout", "期限", True), ("change-config", "変更", True),
])
def test_reject_before_exec(launch, kind, variant, message, scanned):
    root, skill, _, run, _, _ = launch
    skill("commit", "home/.claude/skills/commit/SKILL.md")
    result = run(kind, variant)
    assert result.returncode != 0, (variant, result.stderr)
    assert message in result.stderr, result.stderr
    assert "private config content" not in result.stderr
    assert (root / "scan-called").exists() == scanned
    assert not (root / "capture").exists()
    assert not list((root / "state").glob("*.state"))
    if scanned:
        assert not Path((root / "scratch").read_text()).exists()


@pytest.mark.parametrize(("requested", "message"), [
    ("extra", "有効"), ("ext", "未知"), ("duplicate", "複数実体"), ("*extra", "不正"),
    ("extra,", "不正"), ("extra\t", "不正"), ("ghost", "未知"),
])
def test_extra_requires_exact_enabled_unambiguous_name(launch, requested, message):
    root, skill, _, run, _, _ = launch
    skill("extra", "home/.codex/skills/extra/SKILL.md", enabled=False)
    skill("duplicate", "home/.agents/skills/duplicate/SKILL.md")
    skill("duplicate", "project/.agents/skills/duplicate/SKILL.md", scope="repo")
    result = run("impl", CODEX_SKILLS_ALLOW=requested)
    assert result.returncode != 0
    assert message in result.stderr, result.stderr
    assert not (root / "capture").exists()
