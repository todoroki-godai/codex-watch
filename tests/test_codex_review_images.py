"""bin/codex-review の画像の口（CODEX_REVIEW_IMAGES）の試験。

2026-10-28 追加。見ること:
  - 変数なし／空 → `codex exec` の引数列が従来と同一（陽性対照）
  - 変数に画像N件 → `-i <パス>` が N 件、与えた順に付く（陽性対照）
  - 無いパス／拡張子違い／ディレクトリ／先頭 `-`／`,` 入り → exit 2 で、codex も gh も起こさず、
    状態ファイルも作らない
  - 空白を含むパス → 拒否せず `-i` 1件のまま壊れずに渡る（採用した扱い）
  - モデル指定は既存の CODEX_REVIEW_MODEL と併用できる

実際の `codex` / `gh` は一切呼ばない（fake スタブ。fake codex は argv を側路ファイルへ書くだけ）。
"""
from __future__ import annotations

import os
import stat
import subprocess
import time
from pathlib import Path

import pytest

CODEX_REVIEW = Path(__file__).resolve().parent.parent / "bin" / "codex-review"
VALID_GOAL_CUT = "30.04分/周 | 根拠: pitfall #588 の実測（2026-08-26 cider-power-lp） | 取得日: 2026-08-26"


def _exe(path: Path, script: str) -> None:
    path.write_text(script)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture()
def env_dir(tmp_path: Path) -> Path:
    d = tmp_path / "fakebin"
    d.mkdir()
    # gh は呼ばれた事実を残す（拒否時に巡数ゲートまで進んでいないことの証跡）
    _exe(
        d / "gh",
        "#!/bin/sh\n"
        "echo called >> \"$GH_CALLED_FILE\"\n"
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
    _exe(
        d / "codex",
        "#!/bin/sh\n"
        "cat >/dev/null\n"
        "if [ -n \"$ARGV_CAPTURE_FILE\" ]; then\n"
        "  : > \"$ARGV_CAPTURE_FILE.tmp\"\n"
        "  for a in \"$@\"; do printf '%s\\n' \"$a\" >> \"$ARGV_CAPTURE_FILE.tmp\"; done\n"
        "  mv \"$ARGV_CAPTURE_FILE.tmp\" \"$ARGV_CAPTURE_FILE\"\n"
        "fi\n"
        "exit 0\n",
    )
    return d


def _run(env_dir: Path, tmp_path: Path, images: str | None, model: str | None = None,
         cwd: Path | None = None) -> subprocess.CompletedProcess:
    workdir = tmp_path / "workdir"
    workdir.mkdir(exist_ok=True)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("dummy prompt\n")
    state_dir = tmp_path / "state"
    state_dir.mkdir(exist_ok=True)
    env = dict(os.environ)
    for key in ("CODEX_REVIEW_MODEL", "CODEX_REVIEW_EFFORT", "CODEX_REVIEW_NO_GATE",
                "CODEX_REVIEW_ACK_PHRASING", "CODEX_REVIEW_IMAGES", "CODEX_REVIEW_GATE_CHECK"):
        env.pop(key, None)
    env["PATH"] = f"{env_dir}:{env.get('PATH', '')}"
    env["CODEX_WATCH_DIR"] = str(state_dir)
    env["REVIEW_TARGET"] = "issue:example-org/example-repo#1"
    env["REVIEW_GOAL_CUT"] = VALID_GOAL_CUT
    env["CODEX_REVIEW_KIND_LABEL"] = "コード"
    env["FAKE_GH_BODY"] = str(tmp_path / "fake_gh_body.txt")
    env["GH_CALLED_FILE"] = str(tmp_path / "gh_called.txt")
    env["ARGV_CAPTURE_FILE"] = str(tmp_path / "argv.txt")
    if images is not None:
        env["CODEX_REVIEW_IMAGES"] = images
    if model is not None:
        env["CODEX_REVIEW_MODEL"] = model
    return subprocess.run([str(CODEX_REVIEW), str(workdir), str(prompt), "imgtest"],
                          env=env, capture_output=True, text=True, timeout=30,
                          cwd=str(cwd) if cwd else None)


def _argv(tmp_path: Path) -> list[str]:
    cap = tmp_path / "argv.txt"
    deadline = time.monotonic() + 3
    while not cap.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert cap.exists(), "fake codex が呼ばれていない"
    return cap.read_text().splitlines()


def _image_args(argv: list[str]) -> list[str]:
    return [argv[i + 1] for i, a in enumerate(argv) if a == "-i"]


def _png(tmp_path: Path, name: str) -> Path:
    p = tmp_path / name
    p.write_bytes(b"\x89PNG\r\n\x1a\n")
    return p


def _assert_rejected_before_anything(tmp_path: Path, r: subprocess.CompletedProcess) -> None:
    assert r.returncode == 2, r.stdout + r.stderr
    assert "CODEX_REVIEW_IMAGES" in r.stderr, r.stderr
    assert not (tmp_path / "argv.txt").exists(), "codex が起こされている"
    assert not (tmp_path / "gh_called.txt").exists(), "巡数ゲート（gh）まで進んでいる"
    assert list((tmp_path / "state").glob("*.state")) == [], "状態ファイルが作られている"


# ---- 陽性対照 ----

def test_no_env_has_no_image_flag_and_same_argv_as_before(env_dir, tmp_path):
    r = _run(env_dir, tmp_path, None)
    assert r.returncode == 0, r.stdout + r.stderr
    argv = _argv(tmp_path)
    assert "-i" not in argv
    # 従来の起動の行どおり（exec -C <dir> -s read-only -o <report> -）。余計な引数が1つも無い
    assert len(argv) == 8, argv
    assert argv[0] == "exec" and argv[1] == "-C" and argv[3:5] == ["-s", "read-only"], argv
    assert argv[5] == "-o" and argv[7] == "-", argv


def test_empty_env_same_argv_as_unset(env_dir, tmp_path):
    r = _run(env_dir, tmp_path, "")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "-i" not in _argv(tmp_path)


def test_blank_lines_only_adds_nothing(env_dir, tmp_path):
    r = _run(env_dir, tmp_path, "\n\n")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "-i" not in _argv(tmp_path)


def test_two_pngs_give_two_dash_i_in_order(env_dir, tmp_path):
    b = _png(tmp_path, "b.png")
    a = _png(tmp_path, "a.png")
    r = _run(env_dir, tmp_path, f"{b}\n{a}")
    assert r.returncode == 0, r.stdout + r.stderr
    argv = _argv(tmp_path)
    assert argv.count("-i") == 2
    assert _image_args(argv) == [str(b), str(a)], argv  # 与えた順（辞書順でない）


def test_other_allowed_extensions_and_uppercase(env_dir, tmp_path):
    files = []
    for n in ("x.jpg", "y.jpeg", "z.webp", "W.PNG"):
        p = tmp_path / n
        p.write_bytes(b"x")
        files.append(str(p))
    r = _run(env_dir, tmp_path, "\n".join(files))
    assert r.returncode == 0, r.stdout + r.stderr
    assert _image_args(_argv(tmp_path)) == files


def test_images_combine_with_existing_model_port(env_dir, tmp_path):
    a = _png(tmp_path, "a.png")
    r = _run(env_dir, tmp_path, str(a), model="gpt-6.1-terra")
    assert r.returncode == 0, r.stdout + r.stderr
    argv = _argv(tmp_path)
    assert argv[argv.index("-m") + 1] == "gpt-6.1-terra"
    assert _image_args(argv) == [str(a)]
    assert argv.index("-i") < argv.index("-o")  # 画像は -o より前（variadic に -o/- を飲ませない）


def test_path_with_spaces_is_one_dash_i(env_dir, tmp_path):
    d = tmp_path / "dir with space"
    d.mkdir()
    p = d / "my shot.png"
    p.write_bytes(b"x")
    r = _run(env_dir, tmp_path, str(p))
    assert r.returncode == 0, r.stdout + r.stderr
    argv = _argv(tmp_path)
    assert _image_args(argv) == [str(p)] and argv.count("-i") == 1


# ---- 陰性（codex・gh・状態ファイルより前に止まる） ----

def test_missing_path_rejected(env_dir, tmp_path):
    ok = _png(tmp_path, "ok.png")
    r = _run(env_dir, tmp_path, f"{ok}\n{tmp_path}/nope.png")  # 2件目だけ外れても全体を止める
    _assert_rejected_before_anything(tmp_path, r)


def test_txt_extension_rejected(env_dir, tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("x")
    _assert_rejected_before_anything(tmp_path, _run(env_dir, tmp_path, str(p)))


def test_no_extension_rejected(env_dir, tmp_path):
    p = tmp_path / "png"
    p.write_text("x")
    _assert_rejected_before_anything(tmp_path, _run(env_dir, tmp_path, str(p)))


def test_directory_named_png_rejected(env_dir, tmp_path):
    d = tmp_path / "dir.png"
    d.mkdir()
    _assert_rejected_before_anything(tmp_path, _run(env_dir, tmp_path, str(d)))


def test_comma_in_path_rejected(env_dir, tmp_path):
    p = tmp_path / "a,b.png"
    p.write_bytes(b"x")
    _assert_rejected_before_anything(tmp_path, _run(env_dir, tmp_path, str(p)))


def test_leading_dash_rejected(env_dir, tmp_path):
    p = tmp_path / "-x.png"
    p.write_bytes(b"x")
    # cwd を tmp_path にして、実在する相対パス "-x.png" で試す（先頭 - の拒否が絶対パス判定より先に効く）
    r = _run(env_dir, tmp_path, "-x.png", cwd=tmp_path)
    _assert_rejected_before_anything(tmp_path, r)
    assert "先頭が -" in r.stderr, r.stderr


def test_existing_relative_path_rejected(env_dir, tmp_path):
    _png(tmp_path, "rel.png")
    r = _run(env_dir, tmp_path, "rel.png", cwd=tmp_path)  # cwd から見て実在する相対パス
    _assert_rejected_before_anything(tmp_path, r)
    assert "絶対パスで指定してください" in r.stderr, r.stderr


def test_absolute_symlink_to_regular_file_accepted_as_given(env_dir, tmp_path):
    real = _png(tmp_path, "real.png")
    link = tmp_path / "link.png"
    link.symlink_to(real)
    r = _run(env_dir, tmp_path, str(link))
    assert r.returncode == 0, r.stdout + r.stderr
    assert _image_args(_argv(tmp_path)) == [str(link)]  # 解決後でなく指定どおりの文字列
