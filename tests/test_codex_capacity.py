"""Run the actual watch/status entry points; no Codex, network, or real state writes."""
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
ERROR = "ERROR: Selected model is at capacity. Please try a different model."


def run_cli(folder, cli, log, report="マージ可\n途中結果\n", alive=False):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "run.log"
    path.write_text(log)
    (folder / "run.report").write_text(report)
    (folder / "run.state").write_text(
        f"run_id=run\npid={os.getpid() if alive else 2147483647}\n"
        f"log={path}\nworkdir={folder}\nstarted_at=0\n"
    )
    result = subprocess.run(
        [str(ROOT / "bin" / cli), "run", *(["9999999999", "0"] if cli == "codex-watch" else [])],
        env={**os.environ, "CODEX_WATCH_DIR": str(folder)},
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


@pytest.mark.parametrize("cli", ["codex-watch", "codex-status"])
@pytest.mark.parametrize("report", ["", "マージ可\n途中結果\n"])
@pytest.mark.parametrize("ending", [
    ERROR + "\n" + ERROR + "\ntokens used\n46,333\n",
    "ERROR: The selected MODEL is overloaded; retry later.\ntokens used\n1\n",
    "ERROR: No free slots for this model.\n",
    "ERROR: Service at capacity.\ntokens used\n42\n",
    "ERROR: Selected model is at\n  capacity. Please retry.\ntokens used\n42\n",
    "ERROR: No free\n  slots for this model.\ntokens used\n42\n",
    ERROR + "\ntokens used\n",
    ERROR + "\n\n\ntokens used\n\n42\n",
    "\x1b[31mERROR: Model AT\tCAPACITY\x1b[0m\r\n\r\ntokens used\r\n42\r\n",
])
def test_terminal_capacity_is_unfinished(tmp_path, cli, report, ending):
    output = run_cli(tmp_path, cli, "codex\n途中経過\nhook: done\n" + ending, report)
    assert "容量不足" in output
    assert "モデルの空き" in output
    assert "作業未完了" in output
    assert "VERDICT:" not in output
    assert "報告あり" not in output
    assert "完了（判定行あり）" not in output
    assert "受領可:" not in output
    assert "--- 判定:" not in output
    if cli == "codex-watch":
        assert "CAPACITY:" in output
        assert "EXIT: run モデルの空きがなくて停止" in output


@pytest.mark.parametrize("cli", ["codex-watch", "codex-status"])
@pytest.mark.parametrize("log", [
    "codex\nマージ可\n本文\ntokens used\n42\n",
    "user\n" + ERROR + "\n依頼本文\ncodex\nマージ可\ntokens used\n42\n",
    ERROR + "\n" + "x" * 200000 + "\ncodex\nマージ可\ntokens used\n42\n",
    "codex\nモデルが at capacity となる例を説明しました\ntokens used\n42\n",
    "ERROR: Permission denied\ntokens used\n42\n",
    "ERROR: Request timed out\ntokens used\n42\n",
    "ERROR: Model is not at capacity; authentication failed.\ntokens used\n42\n",
    "ERROR: Model is no longer overloaded; permission denied.\ntokens used\n42\n",
    "user\n" + ERROR + "\n  quoted continuation\ncodex\nマージ可\ntokens used\n42\n",
    "codex\nマージ可\ntokens used\n42\n引用: " + ERROR + "\n",
])
def test_normal_or_noncapacity_is_not_capacity(tmp_path, cli, log):
    output = run_cli(tmp_path, cli, log)
    assert "容量不足" not in output
    assert "CAPACITY:" not in output
    if cli == "codex-watch":
        assert "VERDICT:" in output
        assert "報告あり" in output
    else:
        assert "完了（判定行あり）" in output


@pytest.mark.parametrize("cli", ["codex-watch", "codex-status"])
def test_live_capacity_suppresses_verdict(tmp_path, cli):
    output = run_cli(tmp_path, cli, ERROR + "\ntokens used\n42\n", alive=True)
    assert "容量不足" in output
    assert "VERDICT:" not in output
    assert "完了（判定行あり）" not in output


@pytest.mark.parametrize("cli", ["codex-watch", "codex-status"])
def test_capacity_without_tokens_or_report(tmp_path, cli):
    output = run_cli(tmp_path, cli, ERROR + "\n", report="")
    assert "容量不足" in output
    assert "作業未完了" in output


def test_existing_filter_notification(tmp_path):
    output = run_cli(tmp_path, "codex-watch",
        "This content was flagged for possible cybersecurity risk\ntokens used\n42\n")
    assert "FILTERED:" in output
    assert "VERDICT:" not in output
    assert "報告あり" not in output


@pytest.mark.parametrize("cli", ["codex-watch", "codex-status"])
def test_capacity_after_large_tool_output(tmp_path, cli):
    output = run_cli(tmp_path, cli, "tool output\n" * 20000 + ERROR + "\ntokens used\n42\n")
    assert "容量不足" in output
    assert "作業未完了" in output
    assert "報告あり" not in output
    assert "完了（判定行あり）" not in output


@pytest.mark.parametrize("cli", ["codex-watch", "codex-status"])
@pytest.mark.parametrize("role", ["codex", "user"])
def test_advisory_bypassable_role_section_error_quote_is_not_capacity(tmp_path, cli, role):
    # 平文区間の推定は迂回可能。通常の role 内の引用を CLI 障害にしない。
    output = run_cli(tmp_path, cli,
        role + "\nマージ可\n引用例:\nERROR: Selected model is at capacity.\ntokens used\n42\n")
    assert "容量不足" not in output
    if cli == "codex-watch":
        assert "VERDICT:" in output
        assert "報告あり" in output
    else:
        assert "完了（判定行あり）" in output
        assert "受領     :" in output
        assert "--- 判定:" in output


def test_watch_rechecks_capacity_after_recovery(tmp_path):
    # 2段階の模擬観測。sleep で次のログへ進め、kill -0 は生存→終了を返す。
    # signal は一切送らず、CLI・ネットワークも呼ばない。
    startup = tmp_path / "observe.sh"
    startup.write_text('''
kill() { [[ ! -e "$CODEX_WATCH_DIR/advanced" ]]; }
sleep() {
  printf 'codex\\nマージ可\\n回復しました\\ntokens used\\n42\\n' >> "$CODEX_WATCH_DIR/run.log"
  touch "$CODEX_WATCH_DIR/advanced"
}
''')
    (tmp_path / "run.log").write_text(ERROR + "\n")
    (tmp_path / "run.report").write_text("マージ可\n回復しました\n")
    (tmp_path / "run.state").write_text(
        f"run_id=run\npid={os.getpid()}\nlog={tmp_path / 'run.log'}\nstarted_at=0\n")
    result = subprocess.run(
        [str(ROOT / "bin/codex-watch"), "run", "9999999999", "60"],
        env={**os.environ, "CODEX_WATCH_DIR": str(tmp_path), "BASH_ENV": str(startup)},
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "advanced").exists()
    assert result.stdout.count("CAPACITY:") == 1
    assert "VERDICT:" in result.stdout
    exit_lines = [line for line in result.stdout.splitlines() if line.startswith("EXIT:")]
    assert len(exit_lines) == 1
    assert "報告あり" in exit_lines[0]
    assert "容量不足" not in exit_lines[0]


@pytest.mark.parametrize("cli", ["codex-watch", "codex-status"])
@pytest.mark.parametrize("ending", [
    "ERROR: stream disconnected before completion\n",
    "codex\n途中で停止\n",
])
def test_other_failure_with_dead_process_is_not_silent(tmp_path, cli, ending):
    output = run_cli(tmp_path, cli, ending, report="")
    assert "容量不足" not in output
    assert "EXIT:" in output if cli == "codex-watch" else "異常終了" in output


def test_live_orphan_or_hung_process_reaches_timeout(tmp_path):
    # 起動親の有無は state にない。生存中だが途中で止まった走行を模擬。
    output = run_cli(tmp_path, "codex-watch", "codex\n途中\n", report="", alive=True)
    assert "TIMEOUT:" in output


def test_advisory_bypassable_plaintext_hook_marker_limitation(tmp_path):
    # 既知の非保証範囲: 本文に CLI と同じ区切りを埋め込めば推定は迂回可能。
    output = run_cli(tmp_path, "codex-status",
        "codex\n引用するログ:\nhook: done\n" + ERROR + "\n")
    assert "容量不足" in output


def test_advisory_bypassable_real_error_inside_body_is_not_detected(tmp_path):
    # 逆方向の限界: 混在ログでは本文中の実stderrを引用と区別できない。
    output = run_cli(tmp_path, "codex-status", "codex\n途中\n" + ERROR + "\n", report="")
    assert "容量不足" not in output
    assert "異常終了" in output


@pytest.mark.parametrize("signal_number", [1, 15])
def test_watcher_itself_terminated_has_no_final_notification(tmp_path, signal_number):
    # 範囲外の既存経路を実測。自分で起動した watcher だけを終了する。
    import time
    startup = tmp_path / "wait.sh"
    startup.write_text('''
kill() { return 0; }
sleep() { touch "$CODEX_WATCH_DIR/waiting"; read -r -t 10 ignored; }
''')
    (tmp_path / "run.log").write_text("codex\n途中\n")
    (tmp_path / "run.state").write_text(f"pid={os.getpid()}\nlog={tmp_path / 'run.log'}\n")
    process = subprocess.Popen(
        [str(ROOT / "bin/codex-watch"), "run", "9999999999", "60"],
        env={**os.environ, "CODEX_WATCH_DIR": str(tmp_path), "BASH_ENV": str(startup)},
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        deadline = time.monotonic() + 5
        while not (tmp_path / "waiting").exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert (tmp_path / "waiting").exists()
        process.send_signal(signal_number)
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == -signal_number, stderr
        assert "EXIT:" not in stdout
    finally:
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=5)
