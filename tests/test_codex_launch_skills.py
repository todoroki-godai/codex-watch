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
    if variant == 'version-exit-error':
        sys.exit(7)
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
    assert blocked == {duplicate, other, system, admin, ancestor, project, external}
    assert blocked.isdisjoint({commit, normal, extra, disabled, old, current})
    assert len(values["skills"]["config"]) == len(blocked)
    assert values.get("memories") == {"use_memories": False}
    assert observed["argv"][1:3] == ["-C", str(root / "project/nested")]
    assert ("を読み込んではならない" in observed["prompt"]) == (kind == "review")
    assert snapshot() == before

@pytest.mark.parametrize("kind", ["impl", "review"])
def test_off_preserves_legacy_args(launch, kind):
    root, _, _, run, child = launch
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


def assert_skip_state(root, result, reason):
    state = root / "state" / (result.stdout.strip() + ".state")
    records = [line for line in state.read_text().splitlines() if line.startswith("launch_skills_filter=")]
    assert records == [f"launch_skills_filter=skipped:{reason}"]


@pytest.mark.parametrize("kind", ["impl", "review"])
@pytest.mark.parametrize(("variant", "version", "reason"), [
    ("new-version", "0.169.2", "未検証の版"),
    ("bad-version", "版不明", "版を識別できません"),
    ("version-exit-error", "版不明", "版を識別できません"),
], ids=["new-version", "bad-version", "version-exit-error"])
def test_unverified_version_launches_without_filter(launch, kind, variant, version, reason):
    root, skill, _, run, child = launch
    skill("unlisted", "home/.codex/skills/unlisted/SKILL.md")
    result = run(kind, variant)
    assert configs(child(result)) == {}
    assert result.stderr.startswith("警告: skill と記憶の絞り込みを省略"), result.stderr
    assert len([line for line in result.stderr.splitlines() if "絞り込み" in line]) == 1
    assert version in result.stderr and reason in result.stderr and "codex --version" in result.stderr
    assert_skip_state(root, result, "unverified_version")


def test_unverified_version_skips_inventory_for_ordinary_launch(launch):
    root, _, _, run, child = launch
    (root / "home/.codex/skills").write_text("private fixture content")
    result = run("impl", "new-version")
    assert configs(child(result)) == {}
    assert "未検証の版" in result.stderr and "読み取り失敗" not in result.stderr
    assert_skip_state(root, result, "unverified_version")


def test_unverified_version_checks_safe_review_addition(launch):
    root, skill, _, run, child = launch
    skill("extra", "home/.codex/skills/extra/SKILL.md")
    result = run("review", "new-version", CODEX_SKILLS_ALLOW="extra")
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
    assert_skip_state(root, result, "inventory_unreadable")


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
            assert "0.169.1" in result.stderr and "codex --version" in result.stderr
            assert result.stderr.startswith("警告:")
            assert len([line for line in result.stderr.splitlines() if "絞り込み" in line]) == 1
            assert_skip_state(root, result, "inventory_unreadable")
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
