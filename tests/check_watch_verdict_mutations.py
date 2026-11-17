"""Disconnect/misroute/corrupt the real notification path in disposable copies."""
import difflib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".tmp/watch-verdict-mutations"
CASES = [
    ("disconnect-watch", "bin/codex-watch", '${MODEL_SUFFIX}${VERDICT_NOTICE}',
     '${MODEL_SUFFIX}', "negative", 2),
    ("skip-reviews", "lib/watch_verdict.py", '== "workspace-write"',
     '!= "workspace-write"', "negative or positive", 1),
    ("check-impl-too", "lib/watch_verdict.py", 'if read_state_file(state_file).get("mode") == "workspace-write":',
     'if False:', "positive", 1),
    ("erase-reason", "lib/watch_verdict.py", '{result.reason}', '', "negative", 1),
    ("fold-newlines", "lib/watch_verdict.py", 'report.open(newline="")',
     'report.open()', "control_bytes", 1),
    ("helper-fail-closed", "lib/watch_verdict.py", '    except Exception:\n        pass',
     '    except Exception:\n        return " / 判定行の受領不可: 検査障害"', "exception_fail_open", 1),
    ("validator-fail-closed", "lib/round_gate.py", 'except Exception:\n        return ReceiptCheck("ok", "")',
     'except Exception:\n        return ReceiptCheck("rejected", "検査障害")', "exception_fail_open", 1),
]


def main():
    results = []
    originals = {source: (ROOT / source).read_bytes() for _, source, *_ in CASES}
    for name, source, old, new, selector, count in CASES:
        folder = OUT / name
        if folder.exists():
            shutil.rmtree(folder)
        for sub in ("bin", "lib", "tests"):
            shutil.copytree(ROOT / sub, folder / sub, ignore=shutil.ignore_patterns("__pycache__"))
        path = folder / source
        before = path.read_text()
        assert before.count(old) == count, name
        after = before.replace(old, new)
        path.write_text(after)
        (folder / "mutation.diff").write_text(''.join(difflib.unified_diff(
            before.splitlines(True), after.splitlines(True), fromfile=source, tofile=source)))
        run = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
             "--basetemp=" + str(folder / "tmp"), "tests/test_watch_verdict.py", "-k", selector],
            cwd=folder, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True, text=True, timeout=60,
        )
        output = run.stdout + run.stderr
        (folder / "pytest.log").write_text(output)
        killed = run.returncode == 1 and " failed" in output and "ERROR collecting" not in output
        row = dict(name=name, source=source, old=old, new=new,
                   result="red" if killed else "green" if run.returncode == 0 else "error",
                   summary=output.strip().splitlines()[-1])
        results.append(row)
        print(name, row["result"], row["summary"], flush=True)
    assert all((ROOT / source).read_bytes() == data for source, data in originals.items())
    (ROOT / "evidence/watch-verdict-mutations.json").write_text(
        json.dumps(dict(originals_unchanged=True, results=results), ensure_ascii=False, indent=2) + "\n")
    return 0 if all(row["result"] == "red" for row in results) else 1


if __name__ == "__main__":
    sys.exit(main())
