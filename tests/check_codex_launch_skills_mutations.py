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
MUTATIONS = (
    ("all-disabled", "    removed = sorted(paths - keep - disabled)",
     "    removed = sorted(paths - disabled)", DEFAULT),
    ("memory-override-omitted",
     '    memory_args = ["-c", "memories.use_memories=false"] if memories == "off" else []',
     "    memory_args = []", DEFAULT),
    ("unreadable-skipped", "        for path in sorted(folder.iterdir()):",
     "        try:\n            children = sorted(folder.iterdir())\n"
     "        except PermissionError:\n            return\n        for path in children:",
     "test_unreadable_directory_stops_before_dispatch[impl]"),
    ("discovery-path-ignored",
     "            under_agents(skill.discovery, agents, actual_agents, agents_stat)\n"
     "            or under_agents(skill.actual, agents, actual_agents, agents_stat)",
     "            under_agents(skill.actual, agents, actual_agents, agents_stat)",
     f"{LINKS}[out-of-agents]"),
    ("unverified-version-accepted",
     "    if version[1].decode(\"ascii\") != CLI_VERSION:",
     "    if False and version[1].decode(\"ascii\") != CLI_VERSION:",
     "test_reject_before_exec[new-version-0.169.2-impl]"),
    ("substring-name",
     "    for name in requested:\n        matches = by_name[name]",
     "    for name in requested:\n"
     "        matches = [skill for skill in skills if skill.name and name in skill.name]",
     "test_extra_requires_exact_enabled_unambiguous_name[part-\\u672a\\u77e5]"),
    ("discovery-used-as-override", "    removed = sorted(paths - keep - disabled)",
     "    removed = sorted({skill.discovery for skill in skills if skill.actual not in keep | disabled})",
     DEFAULT),
    ("real-path-ignored",
     "            under_agents(skill.discovery, agents, actual_agents, agents_stat)\n"
     "            or under_agents(skill.actual, agents, actual_agents, agents_stat)",
     "            under_agents(skill.discovery, agents, actual_agents, agents_stat)",
     f"{LINKS}[into-agents]"),
    ("all-enabled", "    removed = sorted(paths - keep - disabled)", "    removed = []", DEFAULT),
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
    # Returning from PermissionError is the fault, so reaching the try alone is insufficient.
    lines = [first + 3] if name == "unreadable-skipped" else list(range(first, first + len(after.splitlines())))
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
