"""Apply startup-filter faults to isolated copies and save executed-line evidence."""
from concurrent.futures import ThreadPoolExecutor
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HELPER = Path("lib/codex_launch_skills.py")
TEST = "tests/test_codex_launch_skills.py"
DEFAULT = "test_default_filters_skills_and_memories[impl]"
LINKS = "test_review_linked_extra_rejected_or_explicitly_allowed"
VERSION = "test_unverified_version_launches_without_filter[new-version-impl]"
RECHECK = "test_review_rechecks_nested_alias_after_keep_paths"
HEADER = "test_unsupported_skill_header_launches_without_filter"
DISCOVERY_CHECK = "under_agents(skill.discovery, agents, actual_agents, agents_stat)"
RESOLVED_CHECK = "under_agents(resolved, agents, actual_agents, agents_stat)"
FINAL_RECHECK = (
    "    if check_review:\n"
    "        keep_paths([], home, skills, disabled, requested, check_review, recheck=True)"
)
MUTATIONS = (
    ("all-disabled", "    removed = sorted(paths - keep - disabled)",
     "    removed = sorted(paths - disabled)", DEFAULT),
    ("memory-override-omitted",
     '    memory_args = ["-c", "memories.use_memories=false"] if memories == "off" else []',
     "    memory_args = []", DEFAULT),
    ("unreadable-skipped", "        for path in sorted(folder.iterdir()):",
     "        try:\n            children = sorted(folder.iterdir())\n"
     "        except PermissionError:\n            return\n        for path in children:",
     "test_unreadable_directory_launches_without_filter[impl]"),
    ("discovery-path-ignored",
     f"                if ({DISCOVERY_CHECK}\n"
     f"                        or {RESOLVED_CHECK}):",
     f"                if {RESOLVED_CHECK}:",
     f"{LINKS}[verified-out-of-agents]"),
    ("unverified-version-filtered",
     "    version_supported = version == CLI_VERSION",
     "    version_supported = version is not None",
     VERSION),
    ("unverified-version-warning-omitted",
     '    print(f"警告: skill と記憶の絞り込みを省略（Codex CLI {version or \'版不明\'}、{reason}）。"\n'
     '          f" {check}を確認してください。", file=sys.stderr)',
     "    pass  # Emit the state record without the warning.",
     VERSION),
    ("substring-name",
     "    for name in requested:\n        matches = by_name[name]",
     "    for name in requested:\n"
     "        matches = [skill for skill in skills if skill.name and name in skill.name]",
     "test_extra_requires_exact_enabled_unambiguous_name[part-\\u672a\\u77e5]"),
    ("discovery-used-as-override", "    removed = sorted(paths - keep - disabled)",
     "    removed = sorted({skill.discovery for skill in skills if skill.actual not in keep | disabled})",
     DEFAULT),
    ("real-path-ignored",
     f"                if ({DISCOVERY_CHECK}\n"
     f"                        or {RESOLVED_CHECK}):",
     f"                if {DISCOVERY_CHECK}:",
     f"{LINKS}[verified-into-agents]"),
    ("all-enabled", "    removed = sorted(paths - keep - disabled)", "    removed = []", DEFAULT),
    ("review-recheck-omitted", FINAL_RECHECK, "    pass", f"{RECHECK}[verified]"),
    ("review-recheck-error-ignored", FINAL_RECHECK,
     "    if check_review:\n"
     "        try:\n"
     "            keep_paths([], home, skills, disabled, requested, check_review, recheck=True)\n"
     "        except FilterError:\n"
     "            pass",
     f"{RECHECK}[verified]"),
    ("unsupported-header-stops",
     '        if not match:\n            raise InventoryReadError(f"{path}: SKILL.md の見出しを解決できません")',
     '        if not match:\n            raise FilterError(f"{path}: SKILL.md の見出しを解決できません")',
     f"{HEADER}[impl]"),
    ("unsupported-header-silently-skipped",
     '        if not match:\n            raise InventoryReadError(f"{path}: SKILL.md の見出しを解決できません")',
     "        if not match:\n            return None",
     f"{HEADER}[review]"),
    ("toml-path-unquoted", "json.dumps(str(path), ensure_ascii=False)", "str(path)", DEFAULT),
    ("review-recheck-verified-only",
     "        keep_paths([], home, skills, set(), requested, check_review, recheck=True)",
     "        pass", f"{RECHECK}[new-version]"),
    ("review-recheck-first-alias-only", "            for skill in by_path[actual]:",
     "            for skill in (by_path[actual][:1] if recheck else by_path[actual]):",
     f"{RECHECK}[verified]"),
    ("review-recheck-allows-different-target", "                if resolved != skill.actual:",
     "                if False:", f"{RECHECK}[different-public-target]"),
    ("unreadable-review-falls-back",
     "            if check_review:\n                raise FilterError",
     "            if False:\n                raise FilterError",
     "test_unsupported_skill_header_blocks_review_addition[verified]"),
    ("toml-backslash-unescaped", "json.dumps(str(path), ensure_ascii=False)",
     r'json.dumps(str(path), ensure_ascii=False).replace("\\\\", "\\")', DEFAULT),
)


def trace_source(source, lines):
    trace = f"""
    def trace(frame, event, _arg, filename=__file__, lines={lines!r},
              path=Path(__file__).resolve().parents[2] / "mutation-hit"):
        if event == "line" and frame.f_code.co_filename == filename and frame.f_lineno in lines:
            with path.open("a") as output:
                output.write(f"{{frame.f_lineno}}\\n")
        return trace

    sys.settrace(trace)
"""
    return source.replace('if __name__ == "__main__":\n', 'if __name__ == "__main__":\n' + trace)


def check_case(folder, original, case):
    name, before, after, test = case
    source = folder / name / "source"
    source.mkdir(parents=True)
    for part in ("bin", "lib", "templates"):
        shutil.copytree(ROOT / part, source / part, ignore=shutil.ignore_patterns("__pycache__"))
    assert original.count(before) == 1, name
    mutated = original.replace(before, after)
    first = original[:original.index(before)].count("\n") + 1
    # For replacement error paths, require reaching the changed statement.
    last_line_only = {"unreadable-skipped": 3, "review-recheck-error-ignored": 4,
                      "unsupported-header-stops": 1, "unsupported-header-silently-skipped": 1}
    lines = ([first + last_line_only[name]] if name in last_line_only
             else list(range(first, first + len(after.splitlines()))))
    (source / HELPER).write_text(trace_source(mutated, lines))
    base = source.parent / "pytest"
    node = f"{TEST}::{test}"
    command = [sys.executable, "-m", "pytest", "-q", "--tb=short", "-p", "no:cacheprovider",
               f"--basetemp={base}", node]
    environment = {**os.environ, "CODEX_SKILLS_TEST_ROOT": str(source), "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, timeout=60)
    output = result.stdout + result.stderr
    (source.parent / "pytest.log").write_text(output)
    diff = "".join(difflib.unified_diff(
        original.splitlines(keepends=True), mutated.splitlines(keepends=True),
        fromfile=f"a/{HELPER}", tofile=f"b/{HELPER}", n=2,
    ))
    (source.parent / "mutation.diff").write_text(diff)
    markers = {path.resolve() for path in base.glob("test_*/mutation-hit")}
    visits = sorted({int(line) for marker in markers for line in marker.read_text().splitlines()})
    failure = re.search(rf"^{re.escape(TEST)}:(\d+): in test_", output, re.MULTILINE)
    assertion = re.search(r"^E\s+(?:assert\b|AssertionError\b)", output, re.MULTILINE)
    if not (result.returncode == 1 and failure and assertion and visits):
        raise RuntimeError(f"{name}: fault was not detected at an executed line\n{output}")
    summary = next(line for line in output.splitlines() if line.startswith("FAILED "))
    print(f"{name} {HELPER}:{visits} -> {TEST}:{failure[1]} {summary}", flush=True)
    return {"mutation": name, "diff": diff, "executed_lines": visits, "test": node,
            "assertion_line": int(failure[1]), "pytest_exit": result.returncode,
            "pytest_failure": summary}


def main():
    original = (ROOT / HELPER).read_text()
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    parent = ROOT / ".tmp"
    parent.mkdir(exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="launch-skill-mutations-", dir=parent))
    print(f"Isolated logs and diffs: {folder}", flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(lambda case: check_case(folder, original, case), MUTATIONS))
    assert (ROOT / HELPER).read_text() == original
    report = {
        "source_commit": sha,
        "source_sha256": hashlib.sha256(original.encode()).hexdigest(),
        "mutations": rows,
        "undetected_mutations": 0,
    }
    (folder / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(rows)} mutations detected, 0 survived", flush=True)


if __name__ == "__main__":
    main()
