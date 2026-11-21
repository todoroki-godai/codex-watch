"""Resolve a launcher model before dispatch and validate Astra's launch reason."""

import ctypes
import json
import os
from pathlib import Path
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import tomllib

from codex_launch_skills import FilterError, read_file
from round_gate import is_single_line

ASTRA_MODEL = re.compile(r"gpt-\d+(?:\.\d+)*-astra(?:[-_.][a-z0-9]+)*")
RESOLVE_TIMEOUT = 5
MAX_REPLY_BYTES = 2 * 1024 * 1024


def project_user_config(source, destination):
    """Copy only inputs the native loader needs for model and project trust."""
    contents = read_file(source)
    if contents is None and source.is_symlink():
        raise ValueError("Codex 設定のリンク先を読めません")
    settings = tomllib.loads(contents) if contents is not None else {}

    def string(value):
        if not isinstance(value, str):
            raise ValueError("モデルまたは信頼設定の型が不正です")
        return json.dumps(value, ensure_ascii=False).replace("\x7f", r"\u007f")

    lines = []
    for key in ("model", "profile"):
        if key in settings:
            lines.append(f"{key} = {string(settings[key])}")
    if "project_root_markers" in settings:
        markers = settings["project_root_markers"]
        if not isinstance(markers, list):
            raise ValueError("project_root_markers の型が不正です")
        lines.append(f"project_root_markers = [{', '.join(map(string, markers))}]")
    projects = settings.get("projects", {})
    if not isinstance(projects, dict):
        raise ValueError("projects の型が不正です")
    for path, project in projects.items():
        if not isinstance(project, dict):
            raise ValueError("プロジェクト設定の型が不正です")
        if "trust_level" in project:
            lines.append(f"projects.{string(path)}.trust_level = {string(project['trust_level'])}")

    # Legacy [profiles] has no supported selector in current Codex. The launchers
    # don't supply --profile, so no named <profile>.config.toml is active.
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_native_model(executable, workdir, isolated):
    """Read one config RPC under a single deadline and reap the isolated server."""
    # Keep only variables needed for local process startup. In particular, no API
    # credentials, AWS/GH tokens, real state paths, or launch reason are passed.
    env = {
        "PATH": os.environ.get("PATH", os.defpath),
        "HOME": str(isolated), "CODEX_HOME": str(isolated), "TMPDIR": str(isolated),
        "XDG_CONFIG_HOME": str(isolated), "XDG_CACHE_HOME": str(isolated),
        "XDG_DATA_HOME": str(isolated), "XDG_STATE_HOME": str(isolated),
    }
    command = [executable, "app-server", "--listen", "stdio://", "--disable", "plugins",
               "-c", f"sqlite_home={json.dumps(str(isolated))}",
               "-c", f"log_dir={json.dumps(str(isolated))}",
               "-c", 'cli_auth_credentials_store="file"']
    deadline = time.monotonic() + RESOLVE_TIMEOUT
    with subprocess.Popen(command, cwd=workdir, env=env, start_new_session=True,
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL) as server:
        pending = bytearray()
        received = 0

        def send(message):
            server.stdin.write((json.dumps(message) + "\n").encode())
            server.stdin.flush()

        def reply(request_id):
            nonlocal received
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                if b"\n" not in pending:
                    if not select.select([server.stdout], [], [], remaining)[0]:
                        raise TimeoutError
                    chunk = os.read(server.stdout.fileno(), 65536)
                    received += len(chunk)
                    if not chunk or received > MAX_REPLY_BYTES:
                        raise ValueError("Codex の設定応答を受信できません")
                    pending.extend(chunk)
                    continue
                line, _, rest = pending.partition(b"\n")
                pending[:] = rest
                response = json.loads(line)
                if response.get("id") == request_id:
                    return response["result"]

        try:
            send({"id": 1, "method": "initialize",
                  "params": {"clientInfo": {"name": "codex-watch", "version": "1.0"}}})
            reply(1)
            send({"method": "initialized"})
            send({"id": 2, "method": "config/read",
                  "params": {"cwd": workdir, "includeLayers": False}})
            config = reply(2)["config"]
            if config.get("profile") is not None:
                raise ValueError("旧形式の profile が有効です")
            return config["model"]
        finally:
            if server.poll() is None:
                try:
                    os.killpg(server.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except PermissionError:
                    server.kill()


def valid_model(model):
    return (isinstance(model, str) and bool(model.strip()) and is_single_line(model)
            and "\0" not in model and not model.startswith("-"))


def ensure_unmanaged_resolution():
    # Managed Codex settings can override even CLI state paths or re-enable
    # plugins. Only credential-free, local configuration is supported here.
    for path in ("/etc/codex/managed_config.toml", "/etc/codex/requirements.toml"):
        try:
            Path(path).lstat()
        except FileNotFoundError:
            continue
        raise ValueError("管理対象の Codex 設定があります")
    if sys.platform != "darwin":
        return
    cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    cf.CFStringCreateWithCString.argtypes = (ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32)
    cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    cf.CFPreferencesAppValueIsForced.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    cf.CFPreferencesAppValueIsForced.restype = ctypes.c_ubyte
    cf.CFRelease.argtypes = (ctypes.c_void_p,)
    cf.CFRelease.restype = None
    names = []
    try:
        for name in (b"com.openai.codex", b"config_toml_base64", b"requirements_toml_base64"):
            ref = cf.CFStringCreateWithCString(None, name, 0x08000100)  # UTF-8
            if not ref:
                raise ValueError("管理対象の Codex 設定を確認できません")
            names.append(ref)
        if any(cf.CFPreferencesAppValueIsForced(key, names[0]) for key in names[1:]):
            raise ValueError("管理対象の Codex 設定があります")
    finally:
        for ref in names:
            cf.CFRelease(ref)


def resolve_model(workdir):
    ensure_unmanaged_resolution()
    home_override = os.environ.get("CODEX_HOME", "")
    if home_override:
        original = Path(home_override).resolve(strict=True)
        if not original.is_dir():
            raise ValueError("CODEX_HOME がディレクトリではありません")
    else:
        original = (Path.home() / ".codex").resolve()
    executable = shutil.which("codex")
    if not executable:
        raise FileNotFoundError("codex")
    with tempfile.TemporaryDirectory(prefix="codex-watch-model-") as temporary:
        isolated = Path(temporary).resolve()
        project_user_config(original / "config.toml", isolated / "config.toml")
        model = read_native_model(str(Path(executable).absolute()), workdir, isolated)
    if not valid_model(model):
        raise ValueError("実効モデルが空または不正です")
    return model


def astra_reason(model, raw, kind="", gate_json="", must_only="no"):
    if not ASTRA_MODEL.fullmatch(model.strip().casefold()):
        return ""
    if must_only == "yes":
        raise ValueError("Must 解消だけを確認する巡には Astra を使えません")
    reason = raw.strip()
    basis = reason[1:].lstrip(" :：\t\u3000")
    if (not is_single_line(raw) or not reason or reason[0] not in "①②③"
            or not any(char.isalpha() for char in basis)):
        raise ValueError("Astra には CODEX_ASTRA_REASON に ①〜③ と具体的な根拠を1行で指定してください")
    if reason[0] == "①":
        # The prompt's fallback round 1 is not evidence (e.g. none: or bypass).
        round_number = json.loads(gate_json).get("total_round") if gate_json else None
        if kind != "設計" or type(round_number) is not int or round_number != 1:
            raise ValueError("Astra の理由①は、巡数ゲートで設計巡1が確認できたレビューに限ります")
    return reason


def main():
    workdir, model, model_option, *review = sys.argv[1:]
    if not model:
        try:
            model = resolve_model(workdir)
        except TimeoutError:
            print(f"拒否: モデルの設定照会が時間切れです。{model_option} でモデルを明示してください。", file=sys.stderr)
            return 2
        except (OSError, ValueError, FilterError, KeyError, TypeError, AttributeError):
            # Native errors and TOML diagnostics can include values from configuration.
            print(f"拒否: モデルを安全に確定できません。{model_option} でモデルを明示してください。", file=sys.stderr)
            return 2
    if not valid_model(model):
        print(f"拒否: {model_option} には有効なモデル名を1行で指定してください。", file=sys.stderr)
        return 2
    try:
        reason = astra_reason(model, os.environ.get("CODEX_ASTRA_REASON", ""), *review)
    except ValueError as error:
        print(f"拒否: {error}", file=sys.stderr)
        return 2
    # The launchers read the resolved model and reason on separate lines.
    print(reason)
    print(model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
