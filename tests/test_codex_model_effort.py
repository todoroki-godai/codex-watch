"""bin/_codex_common.sh + codex-review/codex-impl/codex-status/codex-watch の
model/effort 配線を試験する。

経緯:
- 2026-09-08 codex レビュー巡1 [Must]1+2: config.toml の自前 awk 解析（TOML の
  字句規則を実装しておらず食い違いが構成された）を撤去し、実際に起動された値は
  codex 起動ログのヘッダーから読む方式にした。
- 2026-09-08 codex レビュー巡2 [Must]1: 起動側がヘッダー出力を待ってから run id を
  返す設計は、待機中に中断すると codex プロセスだけ記録なしで残る。**起動側は待たず
  requested_* のみを即時に state へ書き、実効値は読み手側（codex-status /
  codex-watch）が呼び出し時に毎回ログから導出する**方式へ変更した。
- 2026-09-08 codex レビュー巡2 [Must]2: 「任意の2本目の --------」で打ち切る実装は
  プロンプト本文に混ざった偽ヘッダーを拾う。`^OpenAI Codex v` 行の**直後**が
  `--------` である場合だけをヘッダー区間の開始とする厳密な判定へ変更した。
- 2026-09-08 codex レビュー巡3（族2巡で打ち切り・ユーザー裁定「縮小してマージ」）:
  文字列の形での同定は「実効値」の証明にならない（レビュー側が
  `extract_codex_log_header tests/test_codex_model_effort.py` に値を返させることを
  実際に構成した）。表示の名乗りを「実効値」から「ログ先頭のヘッダー（参考・
  run同一性は未検証）」へ変更し、①先頭200行だけを読む ②1行目が
  `^OpenAI Codex v` で始まらないファイルは即 unresolved、の2点で機構を増やさず
  探索範囲を縮小した。

ここで試験するのは:
  ① env 未指定時、codex へ渡る引数列に -m/-c が付かないこと（従来と同一）
  ② env 指定時、-m が1つだけ付くこと
  ③ state には requested_* のみが即時に書かれ、model=/effort=/*_source= は
     書かれないこと（起動側は待たない）
  ④ run id が待たずに返ること（ヘッダーの無いログでもラッパーが即座に state と
     run id を返す）
  ⑤ extract_codex_log_header() 単体: 正常ヘッダーからログ先頭の参考値が取れる
  ⑥ 同: ヘッダー不在で unresolved になる
  ⑦ 回帰: 行頭固定を外すと埋め込み文字列を誤検出すること（陰性試験の固定化）
  ⑧ 回帰: 偽ヘッダー→本物のヘッダーの順で並ぶログで、偽ヘッダーの値
     （gpt-wrong）を返さないこと（巡2 [Must]2 の再現ケース。巡3の1行目固定で
     常に unresolved になる）
  ⑨ codex-status が読み手側として extract_codex_log_header を呼び、要求値と
     「ログ先頭のヘッダー（参考）」を両方表示し、**「実効値」という語は
     出さない**こと
  ⑩ 回帰（巡3 [Must]3 再現）: ヘッダーではない任意のテキストファイル
     （このテストファイル自身）を渡すと unresolved になること
  ⑪ 回帰（巡3 [Should]2）: ヘッダーは開くが閉じる区切りが先頭200行の外にある
     ログは unresolved になること（走査コストの打ち切り）

実際の `codex` CLI は一切呼ばない（fake スタブに差し替える。fake は argv を側路
ファイルへ書き出し、標準出力へ合成ヘッダーを吐くだけ）。
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"
CODEX_REVIEW = BIN_DIR / "codex-review"
CODEX_IMPL = BIN_DIR / "codex-impl"
CODEX_STATUS = BIN_DIR / "codex-status"
COMMON_SH = BIN_DIR / "_codex_common.sh"

VALID_GOAL_CUT = "30.04分/周 | 根拠: pitfall #588 の実測（2026-08-26 cider-power-lp） | 取得日: 2026-08-26"

SYNTHETIC_HEADER = """\
OpenAI Codex v0.153.4
--------
workdir: /tmp/x
model: gpt-5.6-sol
provider: openai
approval: never
sandbox: read-only
reasoning effort: medium
reasoning summaries: none
session id: test-session
--------
user
dummy
"""

# 巡2 [Must]2 の再現ケース: 本文中に埋め込まれた偽のヘッダー風テキストの後に
# 本物のヘッダーが続くログ。「任意の2本目の --------」で打ち切る実装だと
# gpt-wrong を誤って cli_log として返す。
POISONED_THEN_REAL_HEADER = """\
user
model: gpt-wrong
some analysis referencing model: gpt-wrong again
--------
prompt body continues here
--------
OpenAI Codex v0.153.4
--------
model: gpt-actual
reasoning effort: medium
--------
user
dummy
"""


def _write_executable(path: Path, script: str) -> None:
    path.write_text(script)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture()
def fake_bin(tmp_path: Path) -> Path:
    """fake `gh` / `codex` を PATH に置く。

    `codex` は標準入力を読み捨て、自分の argv を `$ARGV_CAPTURE_FILE` へ1行1引数で書き出し、
    合成ヘッダー（呼び出し側が > "$LOG_FILE" でリダイレクトするので、ここでの標準出力が
    そのままログになる）を出力する。`gh` は codex-review の巡数ゲート発注経路が呼ぶ
    最小限だけ相手をする（test_codex_review_cli.py の fake_bin と同じ形）。
    """
    d = tmp_path / "fakebin"
    d.mkdir()
    _write_executable(
        d / "gh",
        "#!/bin/sh\n"
        "BODY_FILE=\"${FAKE_GH_BODY:-/dev/null}\"\n"
        "case \"$1\" in\n"
        "  issue|pr)\n"
        "    if [ \"$2\" = view ]; then\n"
        "      cat >/dev/null 2>&1\n"
        "      if [ -f \"$BODY_FILE\" ]; then cat \"$BODY_FILE\"; fi\n"
        "      exit 0\n"
        "    fi\n"
        "    ;;\n"
        "  api)\n"
        "    python3 -c \"import json,sys; d=json.load(sys.stdin); sys.stdout.write(d.get('body',''))\" > \"$BODY_FILE\"\n"
        "    exit 0\n"
        "    ;;\n"
        "esac\n"
        "exit 0\n",
    )
    _write_executable(
        d / "codex",
        "#!/bin/sh\n"
        "cat >/dev/null\n"  # 標準入力（プロンプト）を読み捨てる
        "if [ -n \"$ARGV_CAPTURE_FILE\" ]; then\n"
        "  : > \"$ARGV_CAPTURE_FILE\"\n"
        "  for a in \"$@\"; do printf '%s\\n' \"$a\" >> \"$ARGV_CAPTURE_FILE\"; done\n"
        "fi\n"
        "if [ -n \"$FAKE_CODEX_HEADER_FILE\" ] && [ -f \"$FAKE_CODEX_HEADER_FILE\" ]; then\n"
        "  cat \"$FAKE_CODEX_HEADER_FILE\"\n"
        "fi\n"
        "exit 0\n",
    )
    return d


def _run_impl(
    fake_bin: Path,
    tmp_path: Path,
    *,
    argv_capture: Path,
    header_file: Path | None,
    model_env: str = "",
    effort_env: str = "",
) -> subprocess.CompletedProcess:
    workdir = tmp_path / "workdir"
    workdir.mkdir(exist_ok=True)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("dummy prompt\n")
    state_dir = tmp_path / "state"
    state_dir.mkdir(exist_ok=True)

    env = dict(os.environ)
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
    env["CODEX_WATCH_DIR"] = str(state_dir)
    env["CODEX_IMPL_ALLOW_MAIN"] = "1"  # tmp_path は git repo ではないため
    env["ARGV_CAPTURE_FILE"] = str(argv_capture)
    if header_file is not None:
        env["FAKE_CODEX_HEADER_FILE"] = str(header_file)
    else:
        env.pop("FAKE_CODEX_HEADER_FILE", None)
    if model_env:
        env["CODEX_IMPL_MODEL"] = model_env
    else:
        env.pop("CODEX_IMPL_MODEL", None)
    if effort_env:
        env["CODEX_IMPL_EFFORT"] = effort_env
    else:
        env.pop("CODEX_IMPL_EFFORT", None)

    return subprocess.run(
        [str(CODEX_IMPL), str(workdir), str(prompt), "clitest"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _state_dict(state_file: Path) -> dict[str, str]:
    return dict(ln.split("=", 1) for ln in state_file.read_text().splitlines() if "=" in ln)


def _wait_for_file(path: Path, timeout_s: float = 2.0, contains: str | None = None) -> None:
    """テスト側の待機。ラッパー自体は待たない設計（[Must]1）なので、バックグラウンドの
    fake codex がファイルを書き終えるまでの短いレースはテスト側で吸収する。
    `contains` を渡すと、単なる非空チェックでなく指定文字列が現れるまで待つ
    （ストリーミング書込み中の部分読みを避ける）。
    """
    import time

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if path.exists():
            if contains is None:
                if path.stat().st_size > 0:
                    return
            elif contains in path.read_text(errors="ignore"):
                return
        time.sleep(0.02)


# ---------------------------------------------------------------------------
# ① env 未指定時、codex へ渡る引数列に -m/-c が付かない（従来と同一）
# ---------------------------------------------------------------------------


def test_impl_no_model_env_produces_no_extra_flags(fake_bin: Path, tmp_path: Path):
    header_file = tmp_path / "header.txt"
    header_file.write_text(SYNTHETIC_HEADER)
    argv_capture = tmp_path / "argv.txt"

    result = _run_impl(fake_bin, tmp_path, argv_capture=argv_capture, header_file=header_file)
    assert result.returncode == 0, result.stdout + result.stderr

    _wait_for_file(argv_capture)
    argv_lines = argv_capture.read_text().splitlines()
    assert "-m" not in argv_lines, argv_lines
    assert not any(a.startswith("model_reasoning_effort=") for a in argv_lines), argv_lines


# ---------------------------------------------------------------------------
# ② env 指定時、-m が1つだけ付く
# ---------------------------------------------------------------------------


def test_impl_model_env_adds_exactly_one_dash_m(fake_bin: Path, tmp_path: Path):
    header_file = tmp_path / "header.txt"
    header_file.write_text(SYNTHETIC_HEADER)
    argv_capture = tmp_path / "argv.txt"

    result = _run_impl(
        fake_bin, tmp_path, argv_capture=argv_capture, header_file=header_file, model_env="gpt-test-model"
    )
    assert result.returncode == 0, result.stdout + result.stderr

    _wait_for_file(argv_capture)
    argv_lines = argv_capture.read_text().splitlines()
    assert argv_lines.count("-m") == 1, argv_lines
    idx = argv_lines.index("-m")
    assert argv_lines[idx + 1] == "gpt-test-model", argv_lines


# ---------------------------------------------------------------------------
# ③④ state には requested_* のみが即時に書かれ、model=/effort=/*_source= は
#    書かれない（起動側は待たない・run id は待たず返る）
# ---------------------------------------------------------------------------


def test_impl_state_has_requested_only_no_effective_fields(fake_bin: Path, tmp_path: Path):
    header_file = tmp_path / "header.txt"
    header_file.write_text(SYNTHETIC_HEADER)
    argv_capture = tmp_path / "argv.txt"

    result = _run_impl(
        fake_bin,
        tmp_path,
        argv_capture=argv_capture,
        header_file=header_file,
        model_env="gpt-test-model",
        effort_env="high",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    run_id = result.stdout.strip().splitlines()[-1]
    state_file = tmp_path / "state" / f"{run_id}.state"
    assert state_file.is_file()
    lines = _state_dict(state_file)

    assert lines["requested_model"] == "gpt-test-model"
    assert lines["requested_effort"] == "high"
    # 起動側は実効値を書かない（読み手側の責務）。
    assert "model" not in lines
    assert "effort" not in lines
    assert "model_source" not in lines
    assert "effort_source" not in lines


def test_impl_returns_run_id_without_waiting_when_header_absent(fake_bin: Path, tmp_path: Path):
    """ヘッダーの無いログ（fake codex がヘッダーを一切出さない）でも、
    ラッパーが待たずに即座に state と run id を返すことを確認する（[Must]1）。
    タイムアウトを要求しない（サブプロセス自体に長い timeout を掛けているが、
    実際の所要時間はヘッダー待ちが無ければ数百ms以内で完了するはず）。
    """
    argv_capture = tmp_path / "argv.txt"
    result = _run_impl(fake_bin, tmp_path, argv_capture=argv_capture, header_file=None)
    assert result.returncode == 0, result.stdout + result.stderr
    run_id = result.stdout.strip().splitlines()[-1]
    state_file = tmp_path / "state" / f"{run_id}.state"
    assert state_file.is_file()
    lines = _state_dict(state_file)
    # 待たずに返る設計では、そもそも model_source 自体が state に存在しない
    assert "model_source" not in lines
    assert "effort_source" not in lines


# ---------------------------------------------------------------------------
# ⑤⑥ extract_codex_log_header 単体（bin/_codex_common.sh 直接試験）
# ---------------------------------------------------------------------------


def _run_extract(log_text: str | None, tmp_path: Path) -> str:
    log_file = tmp_path / "extract.log"
    if log_text is not None:
        log_file.write_text(log_text)
    script = f'source "{COMMON_SH}"\nextract_codex_log_header "{log_file}"\n'
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


def test_extract_log_header_reads_effective_values(tmp_path: Path):
    out = _run_extract(SYNTHETIC_HEADER, tmp_path)
    model, model_source, effort, effort_source = out.split("\t")
    assert model == "gpt-5.6-sol"
    assert model_source == "cli_log"
    assert effort == "medium"
    assert effort_source == "cli_log"


def test_extract_log_header_unresolved_when_absent(tmp_path: Path):
    out = _run_extract("no header at all\njust some text\n", tmp_path)
    model, model_source, effort, effort_source = out.split("\t")
    assert model == "unresolved"
    assert model_source == "unresolved"
    assert effort == "unresolved"
    assert effort_source == "unresolved"


# ---------------------------------------------------------------------------
# ⑦ 陰性試験（回帰防止）: 行頭固定を外すと埋め込み文字列を誤って拾う
# ---------------------------------------------------------------------------


def test_extract_log_header_line_anchor_prevents_embedded_match(tmp_path: Path):
    poisoned = (
        "OpenAI Codex v0.153.4\n"
        "--------\n"
        "note: see model: not-the-real-model in this comment line\n"
        "model: gpt-5.6-sol\n"
        "reasoning effort: medium\n"
        "--------\n"
    )
    out = _run_extract(poisoned, tmp_path)
    model, model_source, _effort, _effort_source = out.split("\t")
    assert model == "gpt-5.6-sol", "行頭固定が外れて埋め込み文字列を拾った可能性がある"
    assert model_source == "cli_log"


# ---------------------------------------------------------------------------
# ⑧ 陰性試験（巡2 [Must]2 再現）: 偽ヘッダー→本物ヘッダーの順で並ぶログで
#    偽ヘッダーの値（gpt-wrong）を返さない
# ---------------------------------------------------------------------------


def test_extract_log_header_does_not_return_poisoned_value_before_real_header(tmp_path: Path):
    out = _run_extract(POISONED_THEN_REAL_HEADER, tmp_path)
    model, model_source, _effort, _effort_source = out.split("\t")
    assert model != "gpt-wrong", f"偽ヘッダー由来の値を返した: {out}"
    # 巡3で1行目固定を導入したため、1行目が "user" のこのログは即座に unresolved になる
    # （本物のヘッダーが後続行にあっても、1行目でないため拾わない＝仕様どおり）。
    assert model == "unresolved", out
    assert model_source == "unresolved", out


def test_extract_log_header_loose_boundary_would_misdetect_poisoned_value(tmp_path: Path):
    """「任意の2本目の -------- で打ち切る」旧実装を模した壊れた関数で、
    実際に gpt-wrong を誤検出することを確認する（回帰の再発防止・実際に壊して赤にする）。
    """
    log_file = tmp_path / "poisoned.log"
    log_file.write_text(POISONED_THEN_REAL_HEADER)
    script = f"""
extract_broken() {{
  local log_file="$1" model="" effort="" dash_count=0 line
  while IFS= read -r line; do
    if [[ "$line" == "--------" ]]; then
      dash_count=$((dash_count + 1))
      if (( dash_count >= 2 )); then break; fi
      continue
    fi
    if [[ "$line" =~ ^model:\\ (.+)$ ]]; then
      model="${{BASH_REMATCH[1]}}"
    fi
  done < "$log_file"
  printf '%s\\n' "$model"
}}
extract_broken "{log_file}"
"""
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "gpt-wrong", "壊れた実装が期待どおり誤検出しなかった"


# ---------------------------------------------------------------------------
# ⑩ 回帰（巡3 [Must]3 再現）: ヘッダーではない任意のテキストファイルを渡すと
#    unresolved になる（レビュー実測: extract_codex_log_header に
#    tests/test_codex_model_effort.py 自身を渡しても値を拾わないこと）
# ---------------------------------------------------------------------------


def test_extract_log_header_rejects_non_log_file():
    this_file = Path(__file__).resolve()
    script = f'source "{COMMON_SH}"\nextract_codex_log_header "{this_file}"\n'
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    model, model_source, effort, effort_source = result.stdout.strip().split("\t")
    assert model == "unresolved", result.stdout
    assert model_source == "unresolved", result.stdout
    assert effort == "unresolved", result.stdout
    assert effort_source == "unresolved", result.stdout


# ---------------------------------------------------------------------------
# ⑪ 回帰（巡3 [Should]2）: ヘッダーは開くが、閉じる区切りが先頭200行の外にある
#    ログは unresolved になる（走査コストの打ち切り）
# ---------------------------------------------------------------------------


def test_extract_log_header_unresolved_when_closing_delimiter_beyond_200_lines(tmp_path: Path):
    lines = ["OpenAI Codex v0.153.4", "--------"]
    lines += [f"model: not-yet-closed-{i}" for i in range(250)]
    lines.append("--------")
    log_text = "\n".join(lines) + "\n"
    out = _run_extract(log_text, tmp_path)
    model, model_source, effort, effort_source = out.split("\t")
    assert model == "unresolved", out
    assert model_source == "unresolved", out
    assert effort == "unresolved", out
    assert effort_source == "unresolved", out


def test_extract_log_header_performance_on_large_non_header_file(tmp_path: Path):
    """巨大な非ヘッダーファイルでも1行目で即座に unresolved を返し、全体走査しない
    （レビュー実測: 300MB grep 6.58秒 相当のコストを避ける）。ここでは数MB規模で
    実行時間を確認する（フルスイートを遅くしない範囲でのスモーク）。
    """
    import time

    log_file = tmp_path / "big.log"
    with log_file.open("w") as f:
        f.write("not a codex log at all\n")
        for _ in range(200_000):
            f.write("x" * 80 + "\n")

    script = f'source "{COMMON_SH}"\nextract_codex_log_header "{log_file}"\n'
    started = time.monotonic()
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=30)
    elapsed = time.monotonic() - started
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "unresolved\tunresolved\tunresolved\tunresolved"
    assert elapsed < 2.0, f"1行目不一致での即時棄却が効いていない可能性: {elapsed}秒"


# ---------------------------------------------------------------------------
# ⑨ codex-status が読み手側として要求値・「ログ先頭のヘッダー（参考）」を
#    両方表示し、「実効値」という語は出さない
# ---------------------------------------------------------------------------


def test_status_shows_requested_and_effective(fake_bin: Path, tmp_path: Path):
    header_file = tmp_path / "header.txt"
    header_file.write_text(SYNTHETIC_HEADER)
    argv_capture = tmp_path / "argv.txt"

    result = _run_impl(
        fake_bin,
        tmp_path,
        argv_capture=argv_capture,
        header_file=header_file,
        model_env="gpt-test-model",
        effort_env="high",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    run_id = result.stdout.strip().splitlines()[-1]
    state_dir = tmp_path / "state"
    log_file = state_dir / f"{run_id}.log"
    _wait_for_file(log_file, contains="reasoning effort:")

    env = dict(os.environ)
    env["CODEX_WATCH_DIR"] = str(state_dir)
    status_result = subprocess.run(
        [str(CODEX_STATUS), run_id], env=env, capture_output=True, text=True, timeout=30
    )
    assert status_result.returncode == 0, status_result.stdout + status_result.stderr
    assert "要求値" in status_result.stdout
    assert "gpt-test-model" in status_result.stdout
    assert "ログ先頭のヘッダー" in status_result.stdout
    assert "参考" in status_result.stdout
    assert "gpt-5.6-sol" in status_result.stdout
    assert "cli_log" in status_result.stdout
    # [Must]1 の受け: 「実効値」という言い切りの語は表示に出さない
    assert "実効値" not in status_result.stdout
