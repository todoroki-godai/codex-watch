"""Both launchers with a fake Codex, credentials and HOME."""
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
PROMPT = """直しの出所: なし
dummy prompt
見込み: 1分
点検:
- 突き合わせ: 確認済
- 出所の付記: 確認済
- 直し残しの検索: 確認済
"""
FAKE_CODEX = r'''
import json, pathlib, sys
root = pathlib.Path(__file__).resolve().parent.parent
args = sys.argv[1:]
variant = (root / 'variant').read_text()
if args == ['--version']:
    (root / 'version-called').touch()
    print('unknown' if variant == 'bad-version' else
          'codex-cli 0.169.2' if variant == 'new-version' else 'codex-cli 0.169.1')
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
    fake = root / "fake-bin"
    fake.mkdir()
    repo = root / "wrapper"
    shutil.copytree(ROOT / "bin", repo / "bin")
    shutil.copytree(ROOT / "lib", repo / "lib", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "templates", repo / "templates")
    helper = repo / "lib/codex_launch_skills.py"
    if helper.exists():
        helper.write_text(helper.read_text().replace('"/etc/codex"', repr(str(root / "admin"))))
    (root / "project/.git").write_text("gitdir: /nonexistent\n")
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
    def skill(name, rel, *, link=None):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if link is not None:
            path.symlink_to(link)
        else:
            path.write_text(f"---\nname: {name}\ndescription: fixture\n---\n")
        return path

    env = dict(HOME=str(home), PATH=f"{fake}:{os.environ['PATH']}",
               CODEX_WATCH_DIR=str(root / "state"), CODEX_SUMMARY="#0",
               CODEX_IMPL_ALLOW_MAIN="1", CODEX_IMPL_ALLOW_MISSING_NODE_MODULES="1",
               CODEX_REVIEW_KIND_LABEL="コード", CODEX_REVIEW_NO_GATE="local test",
               GIT_CEILING_DIRECTORIES=str(root))

    def run(kind, variant="", **settings):
        for name in ("capture", "version-called"):
            (root / name).unlink(missing_ok=True)
        (root / "variant").write_text(variant)
        return subprocess.run(
            ["bash", str(repo / f"bin/codex-{kind}"), str(work), str(prompt), "test"],
            cwd=root, env={**env, **settings}, capture_output=True, text=True, timeout=24,
        )

    def child(result):
        assert result.returncode == 0, result.stderr
        deadline = time.monotonic() + 4
        while not (root / "capture").exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        return json.loads((root / "capture").read_text())

    return root, skill, run, child


def configs(child):
    args = child["argv"]
    return {key: value for n, arg in enumerate(args) if arg == "-c"
            for key, value in tomllib.loads(args[n + 1]).items() if key in ("skills", "memories")}


@pytest.mark.parametrize("kind", ["impl", "review"])
def test_default_filters_skills_and_memories(launch, kind):
    root, skill, run, child = launch
    commit = skill("commit", "home/.claude/skills/commit/SKILL.md")
    skill("commit", "home/.agents/skills/commit/SKILL.md", link=commit)
    normal = skill("agent-browser", "home/.agents/skills/agent-browser/SKILL.md")
    duplicate = skill("agent-browser", "home/.agents/skills/agent-browser.backup/SKILL.md")
    extra = skill("explicit", 'project/nested/.agents/skills/空 白 " and \\ /SKILL.md')
    disabled = skill("disabled", "home/.codex/skills/disabled/SKILL.md")
    plugin = "home/.codex/plugins/cache"
    other = skill("pdf", f"{plugin}/other/pdf/1/skills/pdf/SKILL.md")
    old = skill("pdf", f"{plugin}/openai-primary-runtime/pdf/1.9.0/skills/pdf/SKILL.md")
    current = skill("pdf", f"{plugin}/openai-primary-runtime/pdf/1.10.0/skills/pdf/SKILL.md")
    for path in (other, old, current):
        manifest = path.parents[2] / ".codex-plugin/plugin.json"
        manifest.parent.mkdir()
        manifest.write_text('{"name": "pdf"}')
    system = skill("system", "home/.codex/skills/.system/system/SKILL.md")
    admin = skill("admin", "admin/skills/admin/SKILL.md")
    ancestor = skill("ancestor", "project/.agents/skills/ancestor/SKILL.md")
    project = skill("project", "project/.codex/skills/project/SKILL.md")
    config = root / "home/.codex/config.toml"
    config.write_text(f"""
[plugins]
"pdf@other".enabled = true
"pdf@openai-primary-runtime".enabled = true
[[skills.config]]
path = {json.dumps(str(disabled))}
enabled = false
""")
    def snapshot():
        return {p.relative_to(root): (p.lstat().st_mtime_ns, p.readlink() if p.is_symlink()
                else p.read_bytes() if p.is_file() else None)
                for p in (root / "home").rglob("*")}
    before = snapshot()
    observed = child(run(kind, CODEX_SKILLS_ALLOW=" explicit,explicit "))
    values = configs(observed)
    blocked = {Path(s["path"]) for s in values["skills"]["config"] if s["enabled"] is False}
    assert blocked == {duplicate, other, system, admin, ancestor, project}
    assert blocked.isdisjoint({commit, normal, extra, disabled, old, current})
    assert values["memories"] == {"use_memories": False}
    assert observed["argv"][1:3] == ["-C", str(root / "project/nested")]
    assert ("を読み込んではならない" in observed["prompt"]) == (kind == "review")
    assert snapshot() == before

@pytest.mark.parametrize("kind", ["impl", "review"])
def test_off_preserves_legacy_args(launch, kind):
    root, _, run, child = launch
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


@pytest.mark.parametrize("direction", ["into-agents", "out-of-agents"])
def test_review_linked_extra_rejected_or_explicitly_allowed(launch, direction):
    root, skill, run, child = launch
    target, alias = (
        ("home/.agents/private/SKILL.md", "project/nested/.agents/skills/alias/SKILL.md")
        if direction == "into-agents" else
        ("home/.claude/skills/linked/SKILL.md", "home/.agents/skills/alias/SKILL.md")
    )
    actual = skill("linked", target)
    skill("linked", alias, link=actual)
    result = run("review", CODEX_SKILLS_ALLOW="linked")
    assert result.returncode != 0, "review launched a forbidden linked skill"
    assert "linked" in result.stderr and "CODEX_REVIEW_ALLOW_SKILLS=1" in result.stderr
    assert not (root / "capture").exists()
    observed = child(run("review", CODEX_SKILLS_ALLOW="linked",
                         CODEX_REVIEW_ALLOW_SKILLS="1", CODEX_MEMORIES="keep"))
    assert configs(observed) == {"skills": {"config": []}}
    assert "を読み込んではならない" not in observed["prompt"]
    assert PROMPT in observed["prompt"]


@pytest.mark.parametrize("kind", ["impl", "review"])
@pytest.mark.parametrize(("variant", "message"), [
    ("new-version", "0.169.2"), ("bad-version", "版"), ("", "読み取り"),
])
def test_reject_before_exec(launch, kind, variant, message):
    root, _, run, _ = launch
    (root / "home/.codex/skills").write_text("private fixture content")
    result = run(kind, variant)
    assert result.returncode != 0, (variant, result.stderr)
    assert message in result.stderr, result.stderr
    if variant:
        assert "読み取り" not in result.stderr
    assert "private fixture content" not in result.stderr
    assert not (root / "capture").exists()
    assert not list((root / "state").glob("*.state"))


@pytest.mark.parametrize(("requested", "message"), [
    ("extra", "有効"), ("part", "未知"), ("duplicate", "複数実体"), ("*extra", "不正"),
    ("extra,", "不正"), ("extra\t", "不正"), ("ghost", "未知"),
])
def test_extra_requires_exact_enabled_unambiguous_name(launch, requested, message):
    root, skill, run, _ = launch
    extra = skill("extra", "home/.codex/skills/extra/SKILL.md")
    (root / "home/.codex/config.toml").write_text(
        f"[[skills.config]]\npath = {json.dumps(str(extra))}\nenabled = false\n")
    skill("partial", "home/.agents/skills/partial/SKILL.md")
    skill("duplicate", "home/.agents/skills/duplicate/SKILL.md")
    skill("duplicate", "project/.agents/skills/duplicate/SKILL.md")
    result = run("impl", CODEX_SKILLS_ALLOW=requested)
    assert result.returncode != 0
    assert message in result.stderr, result.stderr
    assert not (root / "capture").exists()
