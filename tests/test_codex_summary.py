"""Launch real wrappers with the existing fake codex/gh; compare both state readers."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from test_codex_model_effort import fake_bin, VALID_GOAL_CUT

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from round_gate import read_state_file

# Verbatim parseState body from claude-config 9b2d7c5 register.tsx:58-65,
# with only TypeScript annotations removed. Run in Node, not a Python imitation.
BOARD_PARSE = r"""
const parseState = (text) => {
  const out = {}
  for (const line of text.split('\n')) {
    const cut = line.indexOf('=')
    if (cut > 0) out[line.slice(0, cut)] = line.slice(cut + 1)
  }
  return out
}
process.stdout.write(JSON.stringify(parseState(require('fs').readFileSync(0, 'utf8'))))
"""


def readers(path):
    result = subprocess.run(['node', '-e', BOARD_PARSE], input=path.read_bytes().decode('utf-8'),
                            capture_output=True, text=True, check=True, timeout=5)
    return read_state_file(path), json.loads(result.stdout)


@pytest.fixture(params=['codex-impl', 'codex-review'])
def launch(request, tmp_path, fake_bin):
    # Copy the launcher as in receipt tests; keep all preflights and the state writer.
    # Fix only naturally varying run metadata immediately before serialization, so
    # ALL existing keys/values can be compared exactly against the no-summary run.
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    shutil.copy2(ROOT / 'bin/_codex_common.sh', bindir / '_codex_common.sh')
    shutil.copytree(ROOT / 'lib', tmp_path / 'lib')
    source = (ROOT / 'bin' / request.param).read_text()
    anchor = '{\n  echo "run_id=$RUN_ID"'
    assert source.count(anchor) == 1
    source = source.replace(anchor, '''RUN_ID=fixed
CODEX_PID=4242
STATE_FILE="$STATE_DIR/fixed.state"
LOG_FILE="$STATE_DIR/fixed.log"
REPORT_FILE="$STATE_DIR/fixed.report"
EFFECTIVE_PROMPT="$STATE_DIR/fixed.prompt"
''' + anchor)
    launcher = bindir / request.param
    launcher.write_text(source)
    workdir = tmp_path / 'workdir'
    workdir.mkdir()
    home = tmp_path / 'home'
    home.mkdir()
    prompt = tmp_path / 'prompt.txt'
    prompt.write_text('直しの出所: なし\ndummy prompt\n')
    # Existing fake codex/gh from model/effort tests; never call the real CLI.
    date = fake_bin / 'date'
    date.write_text('#!/bin/sh\nprintf "20261110\\n"\n')
    date.chmod(0o755)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('CODEX_', 'REVIEW_', 'GH_', 'GITHUB_', 'AWS_'))}
    env.update(PATH=f'{fake_bin}:{os.environ["PATH"]}', HOME=str(home),
               CODEX_WATCH_DIR=str(tmp_path / 'state'), CODEX_IMPL_ALLOW_MAIN='1',
               CODEX_IMPL_ALLOW_MISSING_NODE_MODULES='1',
               CODEX_REVIEW_KIND_LABEL='コード',
               REVIEW_TARGET='issue:example-org/example-repo#1',
               REVIEW_GOAL_CUT=VALID_GOAL_CUT, FAKE_GH_BODY=str(tmp_path / 'gh-body'))
    # Keep the mutation-runner's trace sink; it is never used by normal code.
    if 'SUMMARY_MUTATION_TRACE' in os.environ:
        env['SUMMARY_MUTATION_TRACE'] = os.environ['SUMMARY_MUTATION_TRACE']

    def run(value, **env_overrides):
        Path(env["FAKE_GH_BODY"]).write_text("")
        run_env = dict(env)
        run_env.update(env_overrides)
        if value is not None:
            run_env['CODEX_SUMMARY'] = value
        result = subprocess.run(['bash', str(launcher), str(workdir), str(prompt), 'summary-test'],
                                env=run_env, text=True, capture_output=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        run_id = result.stdout.strip().splitlines()[-1]
        path = tmp_path / 'state' / f'{run_id}.state'
        return path.read_text(), readers(path)
    return run


def assert_preserved(before, after, expected):
    for baseline, state in zip(before, after):
        assert 'summary' not in baseline
        assert set(state) == set(baseline) | ({'summary'} if expected is not None else set())
        assert {k: v for k, v in state.items() if k != 'summary'} == baseline
        if expected is not None:
            assert state['summary'] == expected
    assert after[0] == after[1]


# Negative tests: each boundary tries both an existing-key overwrite and a new key.
@pytest.mark.parametrize('boundary', ['\n', '\r', '\v', '\f', '\x1c', '\x1d', '\x1e',
                                     '\x85', '\u2028', '\u2029'])
def test_negative_line_injection(launch, boundary):
    baseline_text, baseline = launch(None)
    raw, states = launch('説明' + boundary + 'review_target=none:other' + boundary + 'injected=yes')
    expected = '説明 review_target=none:other injected=yes'
    assert_preserved(baseline, states, expected)
    assert len(raw.splitlines()) == len(baseline_text.splitlines()) + 1


@pytest.mark.parametrize('value', ['', ' \t\u3000\u00a0', '\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029'])
def test_negative_empty_after_normalization(launch, value):
    raw_before, baseline = launch(None)
    raw, states = launch(value)
    assert_preserved(baseline, states, None)
    assert raw == raw_before


def test_negative_invalid_utf8_summary(launch):
    locale = dict(LANG='en_US.UTF-8', LC_ALL='en_US.UTF-8')
    raw_before, baseline = launch(None, **locale)
    raw, states = launch(os.fsdecode(b'\xe4\xbc\x9a\xe7\xa4'), **locale)
    assert_preserved(baseline, states, None)
    assert raw == raw_before


@pytest.mark.parametrize('value,expected', [
    ('\u3000  日本語の説明  \t', '日本語の説明'),
    (' ' * 65 + '説明' + ' ' * 65, '説明'),
    ('あ' * 61, 'あ' * 60),
    ('あ' * 59 + '😀' + '末尾', 'あ' * 59 + '😀'),
    ('😀' * 61, '😀' * 60),
])
def test_negative_trim_and_codepoint_limit(launch, value, expected):
    _, baseline = launch(None)
    _, states = launch(value)
    assert_preserved(baseline, states, expected)


# Positive controls, counted separately from negative cases.
@pytest.mark.parametrize('value', ['日本語の説明', '日本語=a=b', None])
def test_positive_controls(launch, value):
    _, baseline = launch(None)
    _, states = launch(value)
    assert_preserved(baseline, states, value)
    assert states[0]['pid'] == '4242'
