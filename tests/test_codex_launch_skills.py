"""Both launchers with a fake Codex, credentials and HOME."""
import fcntl
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
import json, os, pathlib, shutil, subprocess, sys, time
root = pathlib.Path(__file__).resolve().parent.parent
args = sys.argv[1:]
variant = (root / 'variant').read_text()
if args == ['--version']:
    (root / 'version-called').touch()
    if variant == 'version-exit-error':
        sys.exit(7)
    print('unknown' if variant == 'bad-version' else
          'codex-cli 0.171.1' if variant == 'new-version' else 'codex-cli 0.171.0')
elif args[0] == 'exec':
    payload = {'argv': args, 'prompt': sys.stdin.read(),
               'cwd': os.getcwd(), 'codex_home': os.environ['CODEX_HOME'], 'executable': sys.argv[0]}
    if '-o' not in args:
        with (root / 'probe-calls').open('a') as stream:
            stream.write(json.dumps(payload) + '\n')
        plan = json.loads((root / 'probe-plan').read_text())
        if plan.get('reinstall_system'):
            system = pathlib.Path(os.environ['CODEX_HOME']) / 'skills/.system'
            backup = root / 'system-backup'
            shutil.copytree(system, backup)
            shutil.rmtree(system)
            shutil.copytree(backup, system)
            shutil.rmtree(backup)
        if plan.get('change_config'):
            (pathlib.Path(os.environ['CODEX_HOME']) / 'config.toml').write_text('[skills]\n# changed\n')
        if plan.get('add_skill'):
            path = pathlib.Path(os.environ['CODEX_HOME']) / 'skills/added/SKILL.md'
            path.parent.mkdir()
            path.write_text('---\nname: added\n---\n')
        if plan.get('replace_system_link'):
            system = pathlib.Path(os.environ['CODEX_HOME']) / 'skills/.system'
            system.unlink()
            system.symlink_to(root / 'other-system', target_is_directory=True)
        if plan.get('replace_real_system_link'):
            system = pathlib.Path(os.environ['CODEX_HOME']) / 'skills/.system'
            shutil.copytree(system, root / 'other-system', dirs_exist_ok=True)
            shutil.rmtree(system)
            system.symlink_to(root / 'other-system', target_is_directory=True)
        if plan.get('replace_system_parent'):
            parent = pathlib.Path(os.environ['CODEX_HOME']) / 'skills'
            parent.rename(root / 'old-skills')
            parent.mkdir()
            for child in (root / 'old-skills').iterdir():
                child.rename(parent / child.name)
        if plan.get('change_system_content'):
            path = pathlib.Path(os.environ['CODEX_HOME']) / 'skills/.system/bundled/SKILL.md'
            path.write_text(path.read_text() + '\nchanged\n')
        if plan.get('replace_system_content'):
            system = pathlib.Path(os.environ['CODEX_HOME']) / 'skills/.system'
            shutil.rmtree(system)
            (system / 'different').mkdir(parents=True)
            (system / 'different/SKILL.md').write_text('different')
        if plan.get('hook_warning'):
            print('fixture warning: a startup hook failed', file=sys.stderr)
        if plan.get('timeout'):
            subprocess.Popen([sys.executable, '-c',
                              'import time; time.sleep(1.5); open("probe-orphan", "w").close()'],
                             cwd=root)
            time.sleep(5)
        session = '019a0000-0000-7000-8000-000000000001'
        print(f'session id: {session}')
        if plan.get('messages') is not None:
            path = pathlib.Path(os.environ['CODEX_HOME']) / f'sessions/2026/11/23/rollout-2026-11-23T00-00-00-{session}.jsonl'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(''.join(json.dumps({
                'type': 'response_item', 'payload': {
                    'type': 'message', 'role': role,
                    'content': [{'type': 'input_text', 'text': message}],
                },
            }) + '\n' for role, message in plan['messages']))
        sys.exit(plan.get('exit', 0))
    with (root / 'launch-calls').open('a') as stream:
        stream.write(json.dumps(payload) + '\n')
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
    def skill(name, rel):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"---\nname: {name}\ndescription: fixture\n---\n")
        return path

    def link(rel, target):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(target, target_is_directory=True)
        return path

    env = dict(HOME=str(home), CODEX_HOME=str(codex_home), PATH=f"{fake}:{os.environ['PATH']}",
               CODEX_WATCH_DIR=str(root / "state"), CODEX_SUMMARY="#0",
               CODEX_IMPL_ALLOW_MAIN="1", CODEX_IMPL_ALLOW_MISSING_NODE_MODULES="1", CODEX_IMPL_MODEL="gpt-6.2-sol",
               CODEX_REVIEW_KIND_LABEL="コード", CODEX_REVIEW_NO_GATE="local test", CODEX_REVIEW_MODEL='gpt-6.2-sol',
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

    return root, skill, link, run, child


def configs(child):
    args = child["argv"]
    return {key: value for n, arg in enumerate(args) if arg == "-c"
            for key, value in tomllib.loads(args[n + 1]).items() if key in ("skills", "memories")}


@pytest.mark.parametrize("kind", ["impl", "review"])
def test_default_filters_skills_and_memories(launch, kind):
    root, skill, link, run, child = launch
    commit = skill("commit", "home/.claude/skills/commit/SKILL.md")
    link("home/.agents/skills/commit", commit.parent)
    normal = skill("agent-browser", "home/.agents/skills/agent-browser/SKILL.md")
    duplicate = skill("agent-browser", "home/.agents/skills/agent-browser.backup/SKILL.md")
    extra = skill("explicit", 'project/nested/.agents/skills/空 白 " and \\ /SKILL.md')
    escaped = skill("unlisted", """project/nested/.agents/skills/日本 語 "' \\t/SKILL.md""")
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
    external = skill("external", "home/.claude/skills/external/SKILL.md")
    link("project/nested/.agents/skills/external", external.parent)
    link("home/.agents/skills/external", external.parent)
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
    assert blocked == {duplicate, other, system, admin, ancestor, project, external, escaped}
    assert blocked.isdisjoint({commit, normal, extra, disabled, old, current})
    assert len(values["skills"]["config"]) == len(blocked)
    assert values.get("memories") == {"use_memories": False}
    assert observed["argv"][1:3] == ["-C", str(root / "project/nested")]
    assert ("を読み込んではならない" in observed["prompt"]) == (kind == "review")
    assert snapshot() == before

@pytest.mark.parametrize("kind", ["impl", "review"])
def test_off_adds_no_skill_args(launch, kind):
    root, _, _, run, child = launch
    args = child(run(kind, "new-version", CODEX_SKILLS_FILTER="off"))["argv"]
    common = ["exec", "-C", str(root / "project/nested")]
    options = ["-s", "read-only", "-m", "gpt-6.2-sol"] if kind == "review" else [
        "-c", 'default_permissions="codex-impl-dev"',
        "-c", 'permissions.codex-impl-dev.extends=":workspace"',
        "-c", 'permissions.codex-impl-dev.network.enabled=true',
        "-c", 'shell_environment_policy.inherit="all"',
        "-c", 'shell_environment_policy.ignore_default_excludes=true',
        "-c", 'shell_environment_policy.set.AWS_PROFILE="codex-dev"',
        "-c", 'permissions.codex-impl-dev.filesystem={"~/.aws"="deny"}',
        "-m", "gpt-6.2-sol", "-c", 'model_reasoning_effort="medium"',
    ]
    assert args == [*common, *options, "-o", args[-2], "-"]
    assert (root / "version-called").exists()
    assert not (root / "probe-calls").exists()


@pytest.mark.parametrize("direction", ["into-agents", "out-of-agents"])
@pytest.mark.parametrize("variant", ["verified", "new-version", "bad-version"])
def test_review_linked_extra_rejected_or_explicitly_allowed(launch, direction, variant):
    root, skill, link, run, child = launch
    target, alias = (
        ("home/.agents/private/SKILL.md", "project/nested/.agents/skills/alias/SKILL.md")
        if direction == "into-agents" else
        ("home/.claude/skills/linked/SKILL.md", "home/.agents/skills/alias/SKILL.md")
    )
    actual = skill("linked", target)
    link(str(Path(alias).parent), actual.parent)
    result = run("review", variant, CODEX_SKILLS_ALLOW="linked")
    assert result.returncode != 0, "review launched a forbidden linked skill"
    assert "linked" in result.stderr and "CODEX_REVIEW_ALLOW_SKILLS=1" in result.stderr
    assert not (root / "capture").exists()
    observed = child(run("review", variant, CODEX_SKILLS_ALLOW="linked",
                         CODEX_REVIEW_ALLOW_SKILLS="1", CODEX_MEMORIES="keep"))
    assert configs(observed) == ({"skills": {"config": []}} if variant == "verified" else {})
    assert "を読み込んではならない" not in observed["prompt"]
    assert PROMPT in observed["prompt"]


@pytest.mark.parametrize(("variant", "target", "reason"), [
    ("verified", "home/.agents/private", "CODEX_REVIEW_ALLOW_SKILLS=1"),
    ("new-version", "home/.agents/private", "CODEX_REVIEW_ALLOW_SKILLS=1"),
    ("verified", "outside/other", "列挙後に実体が変更されました"),
], ids=["verified", "new-version", "different-public-target"])
def test_review_rechecks_nested_alias_after_keep_paths(launch, variant, target, reason):
    root, skill, link, run, _ = launch
    allowed = skill("extra", "home/.codex/skills/extra/SKILL.md")
    replacement = skill("extra", f"{target}/SKILL.md")
    alias = link("project/nested/.agents/skills/group/alias", allowed.parent)
    helper = root / "wrapper/lib/codex_launch_skills.py"
    marker = "    return keep, notices"
    source = helper.read_text()
    assert source.count(marker) == 1
    helper.write_text(source.replace(marker, f"""
    alias = Path({str(alias)!r})
    if alias.readlink() == Path({str(allowed.parent)!r}):
        alias.unlink()
        alias.symlink_to({str(replacement.parent)!r}, target_is_directory=True)
{marker}"""))

    result = run("review", variant, CODEX_SKILLS_ALLOW="extra", CODEX_SKILLS_AUTOVERIFY="off")
    assert alias.resolve() == replacement.parent
    assert result.returncode == 2, result.stderr
    assert "extra" in result.stderr and reason in result.stderr
    assert not (root / "capture").exists()
    assert not list((root / "state").glob("*.state"))
    assert not list((root / "state").glob("*.prompt.*"))


def assert_skip_state(root, result, reason):
    state = root / "state" / (result.stdout.strip() + ".state")
    records = [line for line in state.read_text().splitlines() if line.startswith("launch_skills_filter=")]
    assert records == [f"launch_skills_filter=skipped:{reason}"]


@pytest.mark.parametrize("kind", ["impl", "review"])
@pytest.mark.parametrize(("variant", "version", "reason"), [
    ("new-version", "0.171.1", "未検証の版"),
    ("bad-version", "版不明", "版を識別できません"),
    ("version-exit-error", "版不明", "版を識別できません"),
], ids=["new-version", "bad-version", "version-exit-error"])
def test_unverified_version_launches_without_filter(launch, kind, variant, version, reason):
    root, skill, _, run, child = launch
    skill("unlisted", "home/.codex/skills/unlisted/SKILL.md")
    result = run(kind, variant, CODEX_SKILLS_AUTOVERIFY="off")
    assert configs(child(result)) == {}
    assert result.stderr.startswith("警告: skill と記憶の絞り込みを省略"), result.stderr
    assert len([line for line in result.stderr.splitlines() if "絞り込み" in line]) == 1
    assert version in result.stderr and reason in result.stderr and "codex --version" in result.stderr
    assert_skip_state(root, result, "unverified_version")


def test_unverified_version_skips_inventory_for_ordinary_launch(launch):
    root, _, _, run, child = launch
    (root / "home/.codex/skills").write_text("private fixture content")
    result = run("impl", "new-version", CODEX_SKILLS_AUTOVERIFY="off")
    assert configs(child(result)) == {}
    assert "未検証の版" in result.stderr and "読み取り失敗" not in result.stderr
    assert_skip_state(root, result, "unverified_version")


def test_unverified_version_checks_safe_review_addition(launch):
    root, skill, _, run, child = launch
    skill("extra", "home/.codex/skills/extra/SKILL.md")
    result = run("review", "new-version", CODEX_SKILLS_ALLOW="extra", CODEX_SKILLS_AUTOVERIFY="off")
    observed = child(result)
    assert configs(observed) == {}
    assert "を読み込んではならない" in observed["prompt"]
    assert_skip_state(root, result, "unverified_version")


def test_unreadable_location_blocks_unverified_review_addition(launch):
    root, _, _, run, _ = launch
    (root / "home/.codex/skills").write_text("private fixture content")
    result = run("review", "new-version", CODEX_SKILLS_ALLOW="extra")
    assert result.returncode != 0
    assert "読み込み禁止に当たらないか確認できません" in result.stderr
    assert "private fixture content" not in result.stderr
    assert not (root / "capture").exists()
    assert not list((root / "state").glob("*.state"))


@pytest.mark.parametrize("kind", ["impl", "review"])
def test_file_at_skill_location_launches_without_filter(launch, kind):
    root, _, _, run, child = launch
    (root / "home/.codex/skills").write_text("private fixture content")
    result = run(kind)
    assert configs(child(result)) == {}
    assert "ディレクトリではありません" in result.stderr
    assert "private fixture content" not in result.stderr
    assert len([line for line in result.stderr.splitlines() if "絞り込み" in line]) == 1
    assert_skip_state(root, result, "unverified_version")


@pytest.mark.parametrize("kind", ["impl", "review"])
def test_unsupported_skill_header_launches_without_filter(launch, kind):
    root, skill, _, run, child = launch
    path = skill("extra", "home/.codex/skills/extra/SKILL.md")
    path.write_text("---\n{name: extra, description: fixture}\n---\n")
    result = run(kind)
    observed = child(result)
    assert configs(observed) == {}
    assert ("を読み込んではならない" in observed["prompt"]) == (kind == "review")
    warnings = [line for line in result.stderr.splitlines() if "絞り込み" in line]
    assert len(warnings) == 1 and warnings[0].startswith("警告:")
    assert str(path) in warnings[0] and "見出しを解決できません" in warnings[0]
    assert_skip_state(root, result, "unverified_version")


@pytest.mark.parametrize("variant", ["verified", "new-version"])
def test_unsupported_skill_header_blocks_review_addition(launch, variant):
    root, skill, _, run, _ = launch
    path = skill("extra", "home/.codex/skills/extra/SKILL.md")
    path.write_text("---\n{name: extra, description: fixture}\n---\n")
    result = run("review", variant, CODEX_SKILLS_ALLOW="extra")
    assert result.returncode == 2
    assert "読み込み禁止に当たらないか確認できません" in result.stderr
    assert str(path) in result.stderr
    assert not (root / "capture").exists()
    assert not list((root / "state").glob("*.state"))


@pytest.mark.parametrize(("requested", "message"), [
    ("extra", "有効"), ("part", "未知"), ("duplicate", "複数実体"), ("*extra", "不正"),
    ("extra,", "不正"), ("extra\t", "不正"), ("ghost", "未知"),
])
def test_extra_requires_exact_enabled_unambiguous_name(launch, requested, message):
    root, skill, _, run, _ = launch
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


@pytest.mark.parametrize(("settings", "message"), [
    ({"CODEX_SKILLS_FILTER": "yes"}, "CODEX_SKILLS_FILTER"),
    ({"CODEX_MEMORIES": ""}, "CODEX_MEMORIES"),
    ({"CODEX_SKILLS_FILTER": "off", "CODEX_SKILLS_ALLOW": "extra"}, "併用"),
])
def test_invalid_modes_fail_before_version(launch, settings, message):
    root, _, _, run, _ = launch
    result = run("impl", **settings)
    assert result.returncode != 0
    assert message in result.stderr
    assert not (root / "version-called").exists()
    assert not (root / "capture").exists()


def test_custom_home_project_markers_and_scan_boundaries(launch):
    root, skill, link, run, child = launch
    custom_home = root / "custom-home"
    custom_home.mkdir()
    (custom_home / "config.toml").write_text('project_root_markers = ["marker"]\n')
    (root / "project/marker").touch()
    (root / "project/nested/.git").touch()
    ancestor = skill("ancestor", "project/.agents/skills/ancestor/SKILL.md")
    project = skill("project", "project/.codex/skills/project/SKILL.md")
    alt_home = skill("custom", "custom-home/skills/custom/SKILL.md")
    boundary = skill("depth6", "custom-home/skills/a/b/c/d/e/f/SKILL.md")
    skill("depth7", "custom-home/skills/a/b/c/d/e/f/g/SKILL.md")
    skill("hidden", "custom-home/skills/.hidden/SKILL.md")
    skill("other-home", "home/.codex/skills/other/SKILL.md")
    system = skill("system", "custom-home/skills/.system/system/SKILL.md")
    outside = skill("outside", "outside/system/SKILL.md")
    link("custom-home/skills/.system/outside", outside.parent)
    link("custom-home/skills/a/broken", root / "absent")
    link("custom-home/skills/a/loop", alt_home.parents[1])
    result = child(run("impl", CODEX_HOME=str(custom_home), CODEX_MEMORIES="keep"))
    assert configs(result) == {"skills": {"config": [
        {"path": str(path), "enabled": False}
        for path in sorted((ancestor, project, alt_home, boundary, system))
    ]}}


def test_plugin_manifest_formats_and_local_version(launch):
    root, skill, link, run, child = launch
    cache = "home/.codex/plugins/cache/market"
    legacy = skill("legacy", f"{cache}/legacy/local/custom/nested/legacy/SKILL.md")
    migrated = skill("migrated", f"{cache}/legacy/local/.codex-plugin/migrated-command-skills/item/SKILL.md")
    tool = skill("tool", f"{cache}/agent/1.0.0/skills/tool/SKILL.md")
    old = skill("old", f"{cache}/legacy/99.0.0/skills/old/SKILL.md")
    deep = skill("deep", f"{cache}/agent/1.0.0/skills/nested/too/deep/SKILL.md")
    foreign = skill("foreign", "outside/foreign/SKILL.md")
    link(f"{cache}/agent/1.0.0/skills/foreign", foreign.parent)
    disabled = skill("disabled", f"{cache}/disabled/local/skills/disabled/SKILL.md")
    for plug_root, name in ((legacy.parents[3], "legacy"), (old.parents[2], "legacy"),
                            (disabled.parents[2], "disabled")):
        manifest = plug_root / ".claude-plugin/plugin.json"
        manifest.parent.mkdir()
        manifest.write_text(json.dumps({"name": name, "skills": "./custom"}))
    (tool.parents[2] / "plugin.json").write_text(json.dumps({
        "name": "agent", "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
    }))
    (root / "home/.codex/config.toml").write_text("""
[plugins]
"legacy@market".enabled = true
"agent@market".enabled = true
"disabled@market".enabled = false
""")
    result = child(run("impl", CODEX_SKILLS_ALLOW="agent:tool"))
    blocked = configs(result)["skills"]["config"]
    assert blocked == [{"path": str(path), "enabled": False} for path in sorted((legacy, migrated))]
    for name in ("agent:deep", "agent:foreign", "disabled:disabled", "legacy:old"):
        rejected = run("impl", CODEX_SKILLS_ALLOW=name)
        assert rejected.returncode != 0
        assert "未知" in rejected.stderr
        assert not (root / "capture").exists()


@pytest.mark.parametrize("kind", ["impl", "review"])
def test_remote_cache_filters_unregistered_plugins(launch, kind):
    root, skill, link, run, child = launch
    cache = "home/.codex/plugins/cache/openai-curated-remote"
    skill("old", f"{cache}/figma/19.0.0/skills/old/SKILL.md")
    legacy = skill("design", "shared/design/SKILL.md")
    version = root / cache / "figma/20.0.0"
    link(f"{cache}/figma/20.0.0/custom/design", legacy.parent)
    manifest = version / ".codex-plugin/plugin.json"
    manifest.parent.mkdir()
    manifest.write_text('{"name": "figma", "skills": "./custom"}')
    agent = skill("deploy", f"{cache}/netlify/1.6.0/skills/deploy/SKILL.md")
    (agent.parents[2] / "plugin.json").write_text(json.dumps({
        "name": "netlify", "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
    }))
    commit = skill("commit", "home/.claude/skills/commit/SKILL.md")
    link("home/.agents/skills/commit", commit.parent)
    result = run(kind)
    blocked = configs(child(result))["skills"]["config"]
    assert blocked == [{"path": str(path), "enabled": False} for path in sorted((legacy, agent))]
    assert "列挙=3 残す=1 外す=2" in result.stderr

    allowed = child(run(kind, CODEX_SKILLS_ALLOW="figma:design"))
    assert configs(allowed)["skills"]["config"] == [{"path": str(agent), "enabled": False}]


@pytest.mark.parametrize("shape", ["file", "unreadable", "no-version", "bad-manifest", "bad-skill-root"])
def test_unreadable_remote_cache_launches_without_filter(launch, shape):
    root, skill, _, run, child = launch
    skill("unlisted", "home/.codex/skills/unlisted/SKILL.md")
    cache = root / "home/.codex/plugins/cache/openai-curated-remote"
    cache.parent.mkdir(parents=True)
    if shape == "file":
        cache.touch()
    elif shape == "unreadable":
        cache.mkdir(mode=0)
    elif shape == "no-version":
        (cache / "figma").mkdir(parents=True)
    else:
        manifest = cache / "figma/20.0.0/.codex-plugin/plugin.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text("{" if shape == "bad-manifest" else '{"name":"figma","skills":"/unexpected"}')
    try:
        result = run("impl")
        assert configs(child(result)) == {}
        assert result.stderr.startswith("警告:")
        assert str(cache) in result.stderr
        assert_skip_state(root, result, "unverified_version")
    finally:
        if shape == "unreadable":
            cache.chmod(0o700)


def test_name_fallback_namespace_and_ordered_rules(launch):
    root, skill, link, run, child = launch
    legacy = skill("ignored", "home/.claude/skills/namespace/skills/real-folder/SKILL.md")
    legacy.write_text("---\nname: ''\ndescription: fixture\n---\nname: body\n")
    manifest = legacy.parents[2] / ".claude-plugin/plugin.json"
    manifest.parent.mkdir()
    manifest.write_text('{"name":"namespace"}')
    link("home/.agents/skills/alias", legacy.parent)
    (root / "home/.codex/config.toml").write_text("""
[[skills.config]]
name = "namespace:real-folder"
enabled = false
[[skills.config]]
path = "~/.agents/skills/alias/SKILL.md"
enabled = true
""")
    result = child(run("impl", CODEX_SKILLS_ALLOW="namespace:real-folder"))
    assert configs(result)["skills"] == {"config": []}
    rejected = run("impl", CODEX_SKILLS_ALLOW="namespace:alias")
    assert rejected.returncode != 0
    assert "未知" in rejected.stderr


@pytest.mark.parametrize("kind", ["impl", "review"])
@pytest.mark.parametrize(("statement", "message"), [
    ("os.kill(os.getpid(), signal.SIGALRM)", "期限"),
    ('(home / ".codex/config.toml").write_text("# fixture config changed")', "変更"),
    ('(codex_home / "plugins/cache/market/plugin/2.0.0").mkdir()', "変更"),
    ('check_arg_size(["x" * 131072])', "引数がシステムの上限"),
])
def test_scan_failures_stop_before_dispatch(launch, kind, statement, message):
    root, skill, _, run, _ = launch
    skill("test", "home/.agents/skills/test/SKILL.md")
    plugin = root / "home/.codex/plugins/cache/market/plugin/1.0.0"
    plugin.mkdir(parents=True)
    (root / "home/.codex/config.toml").write_text('[plugins]\n"plugin@market".enabled = true\n')
    helper = root / "wrapper/lib/codex_launch_skills.py"
    marker = "    disabled = disabled_paths(user, codex_home, skills)"
    source = helper.read_text()
    assert source.count(marker) == 1
    helper.write_text(source.replace(marker, f"    {statement}\n{marker}"))
    result = run(kind)
    assert result.returncode != 0
    assert message in result.stderr, result.stderr
    assert not (root / "capture").exists()
    assert not list((root / "state").glob("*.state"))


@pytest.mark.parametrize("kind", ["impl", "review"])
def test_child_config_failure_is_visible_in_status(launch, kind):
    root, _, _, run, child = launch
    result = run(kind, "child-error")
    child(result)
    run_id = result.stdout.strip()
    command = ["bash", str(root / "wrapper/bin/codex-status"), run_id]
    deadline = time.monotonic() + 4
    while True:
        status = subprocess.run(command, env={**os.environ, "CODEX_WATCH_DIR": str(root / "state")},
                                capture_output=True, text=True, timeout=5, check=True)
        if "異常終了（判定行なし・ログを確認）" in status.stdout or time.monotonic() >= deadline:
            break
        time.sleep(0.02)
    assert "異常終了（判定行なし・ログを確認）" in status.stdout
    assert "test config error" in (root / "state" / f"{run_id}.log").read_text()


@pytest.mark.parametrize("kind", ["impl", "review"])
def test_unreadable_directory_launches_without_filter(launch, kind):
    root, skill, _, run, child = launch
    nested = skill("hidden", "home/.codex/skills/hidden/SKILL.md").parent
    for path in (nested.parent, nested):
        path.chmod(0)
        try:
            with pytest.raises(PermissionError):
                list(path.iterdir())
            result = run(kind)
            assert configs(child(result)) == {}
            assert str(path) in result.stderr and "読み取り" in result.stderr
            assert "0.171.0" in result.stderr and "codex --version" in result.stderr
            assert result.stderr.startswith("警告:")
            assert len([line for line in result.stderr.splitlines() if "絞り込み" in line]) == 1
            assert_skip_state(root, result, "unverified_version")
        finally:
            path.chmod(0o700)


def test_review_permission_uses_path_components(launch):
    _, skill, link, run, child = launch
    actual = skill("allowed", "home/.agents-neighbor/allowed/SKILL.md")
    link("project/nested/.agents/skills/alias", actual.parent)
    observed = child(run("review", CODEX_SKILLS_ALLOW="allowed"))
    assert configs(observed)["skills"] == {"config": []}
    assert "を読み込んではならない" in observed["prompt"]


def test_review_rejects_case_alias_on_case_insensitive_home(launch):
    root, skill, link, run, _ = launch
    skill("linked", "home/.agents/private/SKILL.md")
    alias = root / "home/.AGENTS/private"
    if not alias.exists():
        pytest.skip("filesystem distinguishes case")
    link("project/nested/.agents/skills/alias", alias)
    result = run("review", CODEX_SKILLS_ALLOW="linked")
    assert result.returncode != 0
    assert "CODEX_REVIEW_ALLOW_SKILLS=1" in result.stderr
    assert not (root / "capture").exists()


def skills_message(*pairs, alias_dir=None):
    lines = ["<skills_instructions>", "## Skills"]
    if alias_dir is not None:
        lines.extend(["### Skill roots", f"- `r0` = `{alias_dir}`"])
    lines.append("### Available skills")
    lines.extend(f"- {name}: fixture (file: {path})" for name, path in pairs)
    return "\n".join([*lines, "</skills_instructions>"])


def plan_probe(root, messages=None, **options):
    (root / "probe-plan").write_text(json.dumps({"messages": messages, **options}))


def version_file(root):
    return root / "state/cli-versions/0.171.1.json"


def state_fields(root, result):
    return dict(line.split("=", 1) for line in
                (root / "state" / (result.stdout.strip() + ".state")).read_text().splitlines()
                if "=" in line)


@pytest.mark.parametrize("kind", ["impl", "review"])
def test_newest_is_used_for_probe_and_launch(launch, kind):
    root, skill, _, run, child = launch
    skill("kept", "home/.agents/skills/kept/SKILL.md")
    skill("dropped", "home/.agents/skills/dropped/SKILL.md")
    plan_probe(root, [])
    newer = root / "nvm/versions/node/v2/bin/codex"
    newer.parent.mkdir(parents=True)
    # The fake records invocation paths but shares the original fixture data.
    code = FAKE_CODEX.replace("pathlib.Path(__file__).resolve().parent.parent", f"pathlib.Path({str(root)!r})")
    code = code.replace("variant = (root / 'variant').read_text()", "variant = 'new-version'")
    executable(newer, code)
    result = run(kind, NVM_DIR=str(root / "nvm"))
    assert child(result)["executable"] == str(newer)
    assert state_fields(root, result)["codex_path"] == str(newer)
    assert json.loads((root / 'probe-calls').read_text().splitlines()[0])["executable"] == str(newer)
    assert '0.171.0' in result.stderr and '0.171.1' in result.stderr


@pytest.mark.parametrize("case,expected", [
    ("numeric", "nvm"), ("tie", "path"), ("invalid", "path"),
    ("override", "override"), ("single", "path"), ("path_order", "second"),
])
def test_candidate_selection(tmp_path, case, expected):
    path = tmp_path / 'path/codex'
    second = tmp_path / 'second/codex'
    nvm = tmp_path / 'nvm/versions/node/v1/bin/codex'
    override = tmp_path / 'explicit/codex'
    for candidate in (path, second, nvm, override):
        candidate.parent.mkdir(parents=True, exist_ok=True)
    def fake(candidate, version):
        candidate.write_text(f'#!/bin/sh\nprintf "%s\\n" "{version}"\n')
        candidate.chmod(0o755)
    fake(path, 'codex-cli 0.99.0' if case == 'numeric' else 'codex-cli 0.171.0')
    if case not in ('single', 'path_order'):
        fake(nvm, {'numeric': 'codex-cli 0.171.0', 'tie': 'codex-cli 0.171.0',
                   'invalid': 'not a version', 'override': 'codex-cli 9.0.0'}[case])
    if case == 'path_order':
        fake(second, 'codex-cli 0.172.0')
    fake(override, 'codex-cli 0.1.0')
    env = dict(os.environ, PATH=os.pathsep.join([str(path.parent), str(second.parent)]),
               NVM_DIR=str(tmp_path / 'nvm'), HOME=str(tmp_path))
    if case == 'override':
        env['CODEX_WATCH_CODEX'] = str(override)
    result = subprocess.run([sys.executable, str(ROOT / 'lib/codex_launch_skills.py'),
                             str(tmp_path), 'no', 'off', 'off'], env=env,
                            capture_output=True, text=True, check=True)
    fields = dict(line.split('=', 1) for line in result.stdout.splitlines())
    assert fields['executable'] == str({'path': path, 'second': second, 'nvm': nvm, 'override': override}[expected])
    assert len(result.stderr.splitlines()) == (1 if case in ('numeric', 'path_order', 'override') else 0)



@pytest.mark.parametrize("case", ["relative", "outside", "group_write", "other_write", "owner"])
def test_nvm_unsafe_candidate_is_never_executed(tmp_path, monkeypatch, case):
    monkeypatch.syspath_prepend(str(ROOT / "lib"))
    import codex_launch_skills as launcher
    nvm = tmp_path / "nvm"
    candidate = nvm / "versions/node/v1/bin/codex"
    candidate.parent.mkdir(parents=True)
    marker = tmp_path / "executed"
    target = tmp_path / "outside" if case == "outside" else candidate
    target.write_text(f"#!/bin/sh\n: > '{marker}'\nprintf 'codex-cli 9.0.0\\n'\n")
    target.chmod(0o775 if case == "group_write" else 0o757 if case == "other_write" else 0o755)
    if case == "outside":
        candidate.symlink_to(target)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("NVM_DIR", "nvm" if case == "relative" else str(nvm))
    monkeypatch.delenv("CODEX_WATCH_CODEX", raising=False)
    if case == "owner":
        monkeypatch.setattr(launcher.os, "getuid", lambda: candidate.stat().st_uid + 1)
    assert launcher.select_codex() == (None, None)
    assert not marker.exists()


def test_resolve_error_skips_only_bad_candidate(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "lib"))
    import codex_launch_skills as launcher
    bad = tmp_path / "bad/codex"
    good = tmp_path / "good/codex"
    for path in (bad, good):
        path.parent.mkdir()
        path.write_text("#!/bin/sh\nprintf 'codex-cli 0.171.0\\n'\n")
        path.chmod(0o755)
    original = Path.resolve
    def resolve(path, *args, **kwargs):
        if path == bad:
            raise PermissionError("fixture")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "resolve", resolve)
    monkeypatch.setenv("PATH", os.pathsep.join([str(bad.parent), str(good.parent)]))
    monkeypatch.setenv("NVM_DIR", str(tmp_path / "missing"))
    monkeypatch.delenv("CODEX_WATCH_CODEX", raising=False)
    assert launcher.select_codex()[0] == str(good)

def check_launch(root, result, child, status, count, *, version="0.171.1"):
    observed = child(result)
    fields = state_fields(root, result)
    assert fields["cli_version"] == version
    assert fields["launch_skills_filter"] == status
    assert len((root / "launch-calls").read_text().splitlines()) == count
    assert ("skills" in configs(observed)) == status.startswith("on")
    return observed


@pytest.mark.parametrize("kind", ["impl", "review"])
def test_autoverify_exact_matches_and_reuses_result(launch, kind):
    root, skill, link, run, child = launch
    kept = skill("agent-browser", "home/.agents/skills/agent-browser/SKILL.md")
    dropped = skill("agent-browser", "home/.agents/skills/agent-browser.backup/SKILL.md")
    # Exercise normalization as well as the role and first-message boundaries.
    alias = link("outside/alias", kept.parent) / "SKILL.md"
    plan_probe(root, [
        ("user", skills_message()),
        ("developer", "unrelated developer message"),
        ("developer", skills_message(("agent-browser", f"r0/{alias.name}"), alias_dir=alias.parent)),
        ("developer", skills_message(("agent-browser", dropped))),
    ], hook_warning=True)
    helper = root / "wrapper/lib/codex_launch_skills.py"
    marker = "def run_probe(executable, work, override):\n"
    source = helper.read_text()
    assert source.count(marker) == 1
    helper.write_text(source.replace(marker, marker + "    assert signal.alarm(0) == 0\n"))
    result = run(kind, "new-version")
    observed = check_launch(root, result, child, "on:autoverified", 1)
    assert configs(observed) == {"skills": {"config": [{"path": str(dropped), "enabled": False}]}}
    probe, = map(json.loads, (root / "probe-calls").read_text().splitlines())
    work = str(root / "project/nested")
    assert probe["cwd"] == observed["cwd"]
    assert probe["codex_home"] == observed["codex_home"] == str(root / "home/.codex")
    assert probe["executable"] == observed["executable"] == str(root / "fake-bin/codex")
    assert probe["argv"][:9] == [
        "exec", "-C", work, "-s", "read-only", "-m", "gpt-6.1-terra",
        "-c", 'model_reasoning_effort="low"',
    ]
    assert probe["argv"][-1] == "-"
    assert configs(probe) == configs(observed)
    assert "OK" in probe["prompt"] and probe["prompt"] not in observed["prompt"]
    assert "a startup hook failed" not in result.stderr
    assert json.loads(version_file(root).read_text()) == {
        "status": "verified", "probe_run": "019a0000-0000-7000-8000-000000000001", "transient": 0,
    }

    newer = skill("extra", "alternate-codex-home/skills/new/SKILL.md")
    result = run(kind, "new-version", CODEX_HOME=str(root / "alternate-codex-home"))
    observed = check_launch(root, result, child, "on:autoverified", 2)
    assert configs(observed) == {"skills": {"config": [
        {"path": str(path), "enabled": False} for path in sorted([newer, dropped])
    ]}}
    assert len((root / "probe-calls").read_text().splitlines()) == 1


def test_autoverify_system_reinstalled(launch):
    root, skill, _, run, child = launch
    kept = skill("agent-browser", "home/.agents/skills/agent-browser/SKILL.md")
    skill("extra", "home/.codex/skills/unlisted/SKILL.md")
    skill("bundled", "home/.codex/skills/.system/bundled/SKILL.md")
    plan_probe(root, [("developer", skills_message(("agent-browser", kept)))], reinstall_system=True)
    check_launch(root, run("impl", "new-version"), child, "on:autoverified", 1)


@pytest.mark.parametrize("change", ["replace_real_system_link", "replace_system_parent",
                                    "change_system_content", "replace_system_content"])
def test_autoverify_system_change_is_transient(launch, change):
    root, skill, _, run, child = launch
    kept = skill("agent-browser", "home/.agents/skills/agent-browser/SKILL.md")
    skill("extra", "home/.agents/skills/unlisted/SKILL.md")
    skill("bundled", "home/.codex/skills/.system/bundled/SKILL.md")
    (root / "other-system").mkdir()
    plan_probe(root, [("developer", skills_message(("agent-browser", kept)))], **{change: True})
    check_launch(root, run("impl", "new-version"), child, "skipped:autoverify_transient", 1)
    assert "FilterError:" in json.loads(version_file(root).read_text())["last_reason"]


def test_autoverify_config_change_is_transient(launch):
    root, skill, _, run, child = launch
    kept = skill("agent-browser", "home/.agents/skills/agent-browser/SKILL.md")
    skill("extra", "home/.codex/skills/unlisted/SKILL.md")
    (root / "home/.codex/skills/.system").mkdir()
    plan_probe(root, [("developer", skills_message(("agent-browser", kept)))],
               reinstall_system=True, change_config=True)
    check_launch(root, run("impl", "new-version"), child, "skipped:autoverify_transient", 1)
    assert "FilterError:" in json.loads(version_file(root).read_text())["last_reason"]


def test_autoverify_new_sibling_is_transient(launch):
    root, skill, _, run, child = launch
    kept = skill("agent-browser", "home/.agents/skills/agent-browser/SKILL.md")
    skill("extra", "home/.codex/skills/unlisted/SKILL.md")
    (root / "home/.codex/skills/.system").mkdir()
    plan_probe(root, [("developer", skills_message(("agent-browser", kept)))],
               reinstall_system=True, add_skill=True)
    check_launch(root, run("impl", "new-version"), child, "skipped:autoverify_transient", 1)


def test_autoverify_system_symlink_change_is_transient(launch):
    root, skill, link, run, child = launch
    kept = skill("agent-browser", "home/.agents/skills/agent-browser/SKILL.md")
    skill("extra", "home/.codex/skills/unlisted/SKILL.md")
    (root / "other-system").mkdir()
    (root / "initial-system").mkdir()
    link("home/.codex/skills/.system", root / "initial-system")
    plan_probe(root, [("developer", skills_message(("agent-browser", kept)))], replace_system_link=True)
    check_launch(root, run("impl", "new-version"), child, "skipped:autoverify_transient", 1)


def test_autoverify_retry_failure_resets_wait(launch):
    root, skill, _, run, child = launch
    skill("extra", "home/.codex/skills/unlisted/SKILL.md")
    state = version_file(root)
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"status": "failed", "transient": 3, "failed_at": time.time() - 86500}))
    plan_probe(root)
    for attempt in (1, 2):
        check_launch(root, run("impl", "new-version"), child, "skipped:autoverify_failed", attempt)
    assert len((root / "probe-calls").read_text().splitlines()) == 1
    assert json.loads(state.read_text())["last_reason"] == "記録なし"


@pytest.mark.parametrize("age,retry", [(86300, False), (86500, True), (None, True)])
def test_autoverify_failed_retry(launch, age, retry):
    root, skill, _, run, child = launch
    kept = skill("agent-browser", "home/.agents/skills/agent-browser/SKILL.md")
    skill("extra", "home/.codex/skills/unlisted/SKILL.md")
    state = {"status": "failed", "transient": 3, "probe_run": None}
    if age is not None:
        state["failed_at"] = time.time() - age
    version_file(root).parent.mkdir(parents=True)
    version_file(root).write_text(json.dumps(state))
    plan_probe(root, [("developer", skills_message(("agent-browser", kept)))])
    check_launch(root, run("impl", "new-version"), child,
                 "on:autoverified" if retry else "skipped:autoverify_failed", 1)
    assert (root / "probe-calls").exists() == retry


@pytest.mark.parametrize("mode", ["verified", "filter-off", "autoverify-off"])
def test_autoverify_bypass(launch, mode):
    root, skill, _, run, child = launch
    skill("unlisted", "home/.codex/skills/unlisted/SKILL.md")
    variant, env, status, version = {
        "verified": ("verified", {}, "on", "0.171.0"),
        "filter-off": ("new-version", {"CODEX_SKILLS_FILTER": "off"}, "off", "0.171.1"),
        "autoverify-off": ("new-version", {"CODEX_SKILLS_AUTOVERIFY": "off"},
                           "skipped:unverified_version", "0.171.1"),
    }[mode]
    observed = check_launch(root, run("impl", variant, **env), child, status, 1, version=version)
    assert ("memories" in configs(observed)) == (mode == "verified")
    assert not (root / "probe-calls").exists()
    assert not version_file(root).exists()


@pytest.mark.parametrize("catalog", ["same-name-other-path", "empty", "omitted"])
def test_autoverify_mismatch_is_final(launch, catalog):
    root, skill, _, run, child = launch
    kept = skill("agent-browser", "home/.agents/skills/agent-browser/SKILL.md")
    dropped = skill("agent-browser", "home/.agents/skills/agent-browser.backup/SKILL.md")
    message = {
        "same-name-other-path": skills_message(("agent-browser", dropped)),
        "empty": skills_message(),
        "omitted": skills_message(("agent-browser", kept)).replace(
            "</skills_instructions>", "- 1 additional skill omitted from this bounded skills list.\n</skills_instructions>"
        ),
    }[catalog]
    plan_probe(root, [("developer", message)])
    for attempt in (1, 2):
        result = run("impl", "new-version")
        check_launch(root, result, child, "skipped:autoverify_failed", attempt)
        warnings = [line for line in result.stderr.splitlines() if "自動確認" in line]
        assert len(warnings) == (1 if attempt == 1 else 0)
        assert len((root / "probe-calls").read_text().splitlines()) == 1
    assert json.loads(version_file(root).read_text())["status"] == "failed"


@pytest.mark.parametrize("problem", ["no-section", "no-record", "timeout", "no-removals", "nonzero"])
def test_autoverify_transient_budget(launch, problem):
    root, skill, _, run, child = launch
    kept = skill("agent-browser", "home/.agents/skills/agent-browser/SKILL.md")
    if problem != "no-removals":
        skill("extra", "home/.codex/skills/unlisted/SKILL.md")
    if problem == "no-section":
        plan_probe(root, [
            ("developer", "<skills_instructions>no catalog</skills_instructions>"),
            ("developer", skills_message(("agent-browser", kept))),
        ])
    elif problem == "timeout":
        plan_probe(root, timeout=True)
        helper = root / "wrapper/lib/codex_launch_skills.py"
        source = helper.read_text()
        assert source.count("PROBE_TIMEOUT = 120") == 1
        helper.write_text(source.replace("PROBE_TIMEOUT = 120", "PROBE_TIMEOUT = 0.75"))
    elif problem == "nonzero":
        plan_probe(root, exit=1)
    else:
        plan_probe(root)

    for attempt in range(1, 5):
        result = run("impl", "new-version")
        status = "failed" if attempt >= 3 else "transient"
        check_launch(root, result, child, f"skipped:autoverify_{status}", attempt)
        state = json.loads(version_file(root).read_text())
        assert state["status"] == ("pending" if attempt < 3 else "failed")
        assert state["transient"] == min(attempt, 3)
        assert state["last_reason"] == {
            "no-section": "節なし", "no-record": "記録なし", "nonzero": "記録なし",
            "no-removals": "外す実体0件",
        }.get(problem, state["last_reason"])
        if problem == "timeout":
            assert state["last_reason"].startswith("TimeoutExpired:")
        assert sum("自動確認" in line for line in result.stderr.splitlines()) == (attempt == 3)
    if problem == "no-removals":
        assert not (root / "probe-calls").exists()
    else:
        assert len((root / "probe-calls").read_text().splitlines()) == 3
    if problem == "timeout":
        time.sleep(1.6)
        assert not (root / "probe-orphan").exists()


@pytest.mark.parametrize("failure", ["FilterError", "SIGALRM"])
def test_autoverify_preparation_failure_falls_back(launch, failure):
    root, skill, _, run, child = launch
    skill("extra", "home/.codex/skills/unlisted/SKILL.md")
    helper = root / "wrapper/lib/codex_launch_skills.py"
    marker = "    disabled = disabled_paths(user, codex_home, skills)"
    source = helper.read_text()
    assert source.count(marker) == 1
    statement = ('raise FilterError("fixture preparation failed")' if failure == "FilterError"
                 else "os.kill(os.getpid(), signal.SIGALRM)")
    helper.write_text(source.replace(marker, f"    {statement}\n{marker}"))
    check_launch(root, run("impl", "new-version"), child, "skipped:autoverify_transient", 1)
    state = json.loads(version_file(root).read_text())
    assert state["transient"] == 1
    assert state["last_reason"].startswith("FilterError:")
    assert not (root / "probe-calls").exists()


def test_autoverify_never_waits_on_busy_version_lock(launch):
    root, skill, _, run, child = launch
    skill("extra", "home/.codex/skills/unlisted/SKILL.md")
    state = version_file(root)
    state.parent.mkdir(parents=True)
    with state.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = run("impl", "new-version")
        check_launch(root, result, child, "skipped:unverified_version", 1)
    assert "自動確認" not in result.stderr
    assert not state.exists()
    assert not (root / "probe-calls").exists()


def test_autoverify_rereads_state_after_lock(launch):
    root, skill, _, run, child = launch
    skill("extra", "home/.codex/skills/unlisted/SKILL.md")
    state = version_file(root)
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"status": "pending", "transient": 2, "probe_run": None}))
    failed = {"status": "failed", "transient": 3, "probe_run": "previous", "failed_at": time.time()}
    helper = root / "wrapper/lib/codex_launch_skills.py"
    source = helper.read_text()
    # Simulate the competing process committing the third failure before our flock.
    helper.write_text(source.replace('    try:\n        main()\n', f'''
    real_flock = fcntl.flock
    def flock_after_competitor(fd, flags):
        state = Path({str(state)!r})
        with state.with_suffix(".lock").open("a") as competitor:
            real_flock(competitor, flags)
            write_version_state(state, {failed!r})
        real_flock(fd, flags)

    fcntl.flock = flock_after_competitor
    try:
        main()
'''))
    plan_probe(root)
    result = run("impl", "new-version")
    check_launch(root, result, child, "skipped:autoverify_failed", 1)
    assert not (root / "probe-calls").exists()
    assert "自動確認" not in result.stderr
    assert json.loads(state.read_text()) == failed


@pytest.mark.parametrize("kind", ["impl", "review"])
def test_off_continues_when_helper_fails(launch, kind):
    root, _, _, run, child = launch
    (root / "wrapper/lib/codex_launch_skills.py").write_text("raise SystemExit(2)\n")
    result = run(kind, "new-version", CODEX_SKILLS_FILTER="off")
    check_launch(root, result, child, "off", 1, version="不明")


def test_nonzero_probe_with_matching_record_verifies(launch):
    root, skill, _, run, child = launch
    kept = skill("agent-browser", "home/.agents/skills/agent-browser/SKILL.md")
    skill("extra", "home/.codex/skills/unlisted/SKILL.md")
    plan_probe(root, [("developer", skills_message(("agent-browser", kept)))], exit=1)
    check_launch(root, run("impl", "new-version"), child, "on:autoverified", 1)
    assert json.loads(version_file(root).read_text())["status"] == "verified"


def test_override_still_selected_when_path_compare_fails(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "lib"))
    import codex_launch_skills as launcher
    first = tmp_path / "first/codex"
    fixed = tmp_path / "fixed/codex"
    for path in (first, fixed):
        path.parent.mkdir()
        path.write_text("#!/bin/sh\nprintf 'codex-cli 0.171.0\\n'\n")
        path.chmod(0o755)
    original = Path.resolve
    def resolve(path, *args, **kwargs):
        if path == first:
            raise PermissionError("fixture")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "resolve", resolve)
    monkeypatch.setenv("PATH", str(first.parent))
    monkeypatch.setenv("CODEX_WATCH_CODEX", str(fixed))
    assert launcher.select_codex() == (str(fixed), "0.171.0")
