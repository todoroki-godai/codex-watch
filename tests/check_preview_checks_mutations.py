"""Offline mutation probes. All scratch files stay under the checkout's .tmp/pc.

Run with python3 tests/check_preview_checks_mutations.py.
Each variant is an isolated copy; production files are never mutated.
"""
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.tmp/pc/preview-mutations'
OUT.mkdir(parents=True, exist_ok=True)
SHELL = 'bin/codex-review'
GATE = 'lib/round_gate.py'
cases = [
    ('M1-no-section', GATE,
     'sections: list[set[str]] = []\n    current: set[str] | None = None',
     'sections: list[set[str]] = [set()]\n    current: set[str] | None = sections[0]',
     'negative', 'current: set[str] | None = sections[0]', True),
    ('M2-empty-value', GATE,
     'if line.startswith(prefix) and line[len(prefix):].strip():',
     'if line.startswith(prefix):',
     'negative', 'if line.startswith(prefix):', True),
    ('M3-no-followup-item', GATE,
     'if round_no >= 2:', 'if False:',
     'negative', 'if False:', True),
    ('M4-record-on-stop', SHELL,
     'if missing:\n    print(',
     'if missing:\n    Path(__import__("os").environ["CODEX_WATCH_DIR"], "stopped.state").write_text("review_target=issue:example-org/example-repo#1\\nround=1\\n")\n    print(',
     'negative', 'stopped.state', True),
    ('M5-section-leak', GATE,
     'elif re.match(r"#{1,6}\\s", line):', 'elif False:',
     'negative', 'elif False:', True),
    ('M6-item-prefix', GATE,
     'prefix = f"- {item}:"', 'prefix = f"- {item}"',
     'negative', 'prefix = f"- {item}"', True),
    ('positive-equivalent', GATE,
     'if round_no >= 2:', 'if round_no > 1:',
     '', 'if round_no > 1:', False),
]
results = []
for name, rel, old, new, selector, anchor, red in cases:
    folder = OUT / name
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir()
    for sub in ('bin', 'lib', 'templates', 'tests'):
        shutil.copytree(ROOT / sub, folder / sub,
                        ignore=shutil.ignore_patterns('__pycache__'))
    path = folder / rel
    before = path.read_text()
    assert before.count(old) == 1, (name, before.count(old))
    after = before.replace(old, new)
    assert after != before
    path.write_text(after)
    delta = ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                       fromfile=rel, tofile=rel))
    (folder / 'mutation.diff').write_text(delta)
    # Child bash launchers send actual commands and line numbers to one file.
    shell_trace = folder / 'shell.trace'
    bash_env = folder / 'trace.bash'
    bash_env.write_text('exec 2>>"$PROBE_SHELL_TRACE"\n'
                        "PS4='+${BASH_SOURCE##*/}:${LINENO}: '\nset -x\n")
    # Child Python processes log executed round_gate source lines (including
    # imported helpers inside the launcher's python -c) via the stdlib tracer.
    python_trace = folder / 'python.trace'
    (folder / 'sitecustomize.py').write_text('''import os, sys, linecache, json
_trace_path = os.environ['PROBE_PYTHON_TRACE']
def _trace(frame, event, arg):
    if event == 'line' and (frame.f_code.co_filename.endswith('/round_gate.py') or frame.f_code.co_filename == '<stdin>'):
        with open(_trace_path, 'a') as f:
            f.write(json.dumps({'file': frame.f_code.co_filename, 'line': frame.f_lineno,
                                'source': linecache.getline(frame.f_code.co_filename, frame.f_lineno).strip()}, ensure_ascii=False) + '\\n')
    return _trace
sys.settrace(_trace)
''')
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(folder)] + [p for p in sys.path if 'site-packages' in p]), PYTHONDONTWRITEBYTECODE='1',
               TMPDIR=str(OUT), GIT_CEILING_DIRECTORIES=str(folder),
               PROBE_SHELL_TRACE=str(shell_trace),
               PROBE_PYTHON_TRACE=str(python_trace))
    command = [shutil.which('python3'), '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
               '--basetemp=' + str(folder / 'base'),
               'tests/test_preview_checks.py']
    if selector:
        command += ['-k', selector]
    run = subprocess.run(command, cwd=folder, env=env, capture_output=True, text=True)
    output = run.stdout + run.stderr
    (folder / 'pytest.log').write_text(output)
    if rel == SHELL:
        # macOS bash 3.2 has no BASH_XTRACEFD. Trace in a separate witness run
        # so redirecting stderr cannot affect the actual test verdict above.
        witness = subprocess.run(command, cwd=folder, env=dict(env, BASH_ENV=str(bash_env)),
                                 capture_output=True)
        (folder / 'witness.log').write_bytes(witness.stdout + witness.stderr)
    trace = shell_trace if rel == SHELL else python_trace
    trace_lines = trace.read_text(errors='replace').splitlines()
    hits = [line for line in trace_lines
            if anchor in (line if rel == SHELL else json.loads(line)['source'])]
    # For removed empty-file guard, show that cat now executes on that path.
    if name == 'allow-empty':
        hits = [line for line in hits if ': cat ' in line]
    if name == 'M4-record-on-stop':
        witnesses = list((folder / 'base').rglob('stopped.state'))
        hits = [str(p.relative_to(folder)) + ':' + p.read_text() for p in witnesses]
    assert hits, (name, 'mutated path was not executed')
    assert run.returncode == (1 if red else 0), (name, output)
    assert ('failed' in output if red else 'passed' in output), (name, output)
    assert 'UnicodeDecodeError' not in output and 'ERROR at setup' not in output, output
    record = dict(name=name, file=rel, red_expected=red, exit_code=run.returncode,
                  before_sha256=hashlib.sha256(before.encode()).hexdigest(),
                  after_sha256=hashlib.sha256(after.encode()).hexdigest(),
                  diff=delta, command=command, selector=selector,
                  executed_evidence=hits[:3], execution_hit_count=len(hits),
                  pytest_summary=output[output.rfind('=========================== short test summary info'):]
                  if 'short test summary info' in output else output.strip().splitlines()[-1])
    results.append(record)
    print(name, run.returncode, 'execution_hits=' + str(len(hits)), flush=True)
(ROOT / 'evidence/preview-checks-mutations.json').write_text(
    json.dumps(results, ensure_ascii=False, indent=2) + '\n')
