"""Prepare startup overrides and check review skill additions."""
import errno
from functools import cmp_to_key
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time
import tomllib
import unicodedata
from collections import defaultdict
from dataclasses import dataclass

CLI_VERSION = "0.169.1"
SCAN_TIMEOUT = 15
SYSTEM_CONFIG = Path("/etc/codex")
REMOTE_MARKETPLACE = "openai-curated-remote"
ALLOWLIST = Path(__file__).resolve().parents[1] / "templates/codex-skills-allowlist.tsv"
LEGACY_MANIFESTS = (".codex-plugin/plugin.json", ".claude-plugin/plugin.json",
                    ".cursor-plugin/plugin.json")
AGENT_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"


class FilterError(Exception):
    pass


class InventoryReadError(FilterError):
    pass


def metadata(path, *, follow=True):
    try:
        return path.stat(follow_symlinks=follow)
    except FileNotFoundError:
        return None


def read_file(path):
    info = metadata(path)
    if info is None:
        return None
    if not stat.S_ISREG(info.st_mode):
        raise InventoryReadError(f"{path}: 読み取り失敗（通常ファイルではありません）")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeError:
        raise InventoryReadError(f"{path}: 文字コードを解釈できません") from None


def parse_config(contents, path, parser):
    try:
        value = parser(contents)
    except (ValueError, UnicodeError):
        raise FilterError(f"{path}: 設定の形式を解釈できません") from None
    return table(value, str(path))


def table(value, location):
    if not isinstance(value, dict):
        raise FilterError(f"{location}: 設定がテーブルではありません")
    return value


def merge(base, overlay):
    result = base.copy()
    for key, value in overlay.items():
        old = result.get(key)
        result[key] = merge(old, value) if isinstance(old, dict) and isinstance(value, dict) else value
    return result


def config_flag(config, key, default):
    value = config.get(key, default)
    if type(value) is not bool:
        raise FilterError(f"{key}: 真偽値の設定が不正です")
    return value


class Scan:
    def __init__(self):
        self.observed = {}

    @staticmethod
    def fingerprint(path):
        def identity(info):
            return None if info is None else (
                info.st_dev, info.st_ino, info.st_mode, info.st_mtime_ns, info.st_ctime_ns
            )
        return identity(metadata(path, follow=False)), identity(metadata(path))

    def watch(self, path):
        if path not in self.observed:
            self.observed[path] = self.fingerprint(path)

    def unchanged(self):
        for path, before in self.observed.items():
            if self.fingerprint(path) != before:
                raise FilterError(f"{path}: 列挙中に設定または置き場が変更されました")

    def config(self, path):
        self.watch(path)
        contents = read_file(path)
        return {} if contents is None else parse_config(contents, path, tomllib.loads)

    def installed_manifest(self, root):
        for relative in ("plugin.json", *LEGACY_MANIFESTS):
            path = root / relative
            self.watch(path)
            info = metadata(path, follow=False)
            if info is None:
                continue
            if not stat.S_ISREG(info.st_mode) or path.parent.is_symlink():
                return None
            contents = read_file(path)
            if contents is None:
                raise FilterError(f"{path}: 列挙中にプラグイン定義が変更されました")
            if relative != "plugin.json":
                return parse_config(contents, path, json.loads), False
            try:
                manifest = json.loads(contents)
            except ValueError:
                continue  # An unrelated root plugin.json is not a Codex manifest.
            schema = manifest.get("$schema") if isinstance(manifest, dict) else None
            if not isinstance(schema, str) or not schema.startswith("https://agent-plugins.org/schemas/"):
                continue
            if schema != AGENT_SCHEMA:
                raise FilterError(f"{path}: Agent Plugin の定義版が未検証です")
            return manifest, True
        return None


def ancestors(work, markers, *, require_git_head=False):
    chain = (work, *work.parents)
    for index, parent in enumerate(chain):
        for marker in markers:
            path = parent / marker
            info = metadata(path)
            if info is None:
                continue
            if (require_git_head and marker == ".git" and stat.S_ISDIR(info.st_mode)
                    and metadata(path / "HEAD") is None):
                continue
            return chain[:index + 1]
    return (work,)


def project_config(scan, work, codex_home, config, markers):
    layers = ancestors(work, markers, require_git_head=True)
    projects = table(config.get("projects", {}), "projects")
    common = None
    if projects:
        git = subprocess.run(
            ["git", "-C", str(work), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=5,
        )
        if git.returncode == 0:
            common = Path(git.stdout.rstrip("\n"))
    trust_root = common.parent if common is not None and common.name == ".git" else layers[-1]

    project_dirs = []
    for layer in reversed(layers):
        directory = layer / ".codex"
        scan.watch(directory)
        info = metadata(directory)
        if info is None or not stat.S_ISDIR(info.st_mode) or directory.resolve(strict=True) == codex_home:
            continue
        project_dirs.append(directory)
        path = directory / "config.toml"
        scan.watch(path)
        keys = dict.fromkeys(str(item) for parent in (layer, layers[-1], trust_root)
                             for item in (parent.resolve(strict=True), parent))
        trust = next(
            (projects[key]["trust_level"] for key in keys
             if key in projects and "trust_level" in table(projects[key], "projects")),
            None,
        )
        if trust == "trusted":
            config = merge(config, scan.config(path))
    return project_dirs, config


@dataclass(frozen=True)
class Skill:
    discovery: Path
    actual: Path
    name: str | None
    plugin: str | None
    plugin_relative: Path | None


def discover(root, *, follow=True, agent_root=None):
    """Yield discovery paths, keeping aliases while bounding symlink cycles."""
    dirs, entries = 0, 0

    def walk(folder, visiting, depth):
        nonlocal dirs, entries
        info = metadata(folder)
        if info is None:
            return
        if not stat.S_ISDIR(info.st_mode):
            raise InventoryReadError(f"{folder}: 置き場の読み取り失敗（ディレクトリではありません）")
        actual_dir = folder.resolve(strict=True)
        if actual_dir in visiting:
            return
        dirs += 1
        if dirs > 2000:
            raise FilterError(f"{root}: 探索ディレクトリ数が上限を超えました")
        for path in sorted(folder.iterdir()):
            entries += 1
            if entries > 20_000:
                raise FilterError(f"{root}: 探索項目数が上限を超えました")
            if path.name.startswith("."):
                continue
            link = path.is_symlink()
            if link and not follow:
                continue
            info = metadata(path)
            if info is None:
                if link:
                    continue
                raise FilterError(f"{path}: 列挙中にファイルが変更されました")
            if stat.S_ISDIR(info.st_mode) and depth < (1 if agent_root else 6):
                yield from walk(path, visiting | {actual_dir}, depth + 1)
            elif (path.name == "SKILL.md" and stat.S_ISREG(info.st_mode)
                  and (agent_root is None or depth == 1)):
                actual = path.resolve(strict=True)
                if agent_root is None or actual.is_relative_to(agent_root):
                    yield path, actual

    yield from walk(root, set(), 0)


# Codex reads the YAML header. Keep name matching independent of the Markdown body.
# An unsupported mapping or name scalar makes the inventory unreadable.
HEADER_KEY = re.compile(r"""(?:([\w.-]+)|'([^']+)'|"([^"\\]+)")\s*:(?:\s+|$)(.*)""")
QUOTED_NAME = re.compile(r"""("(?:[^"\\]|\\.)*"|'(?:[^']|'')*')(?:\s+#.*|\s*)""")


def skill_name(path):
    try:
        with path.open(encoding="utf-8") as stream:
            if stream.readline().strip() != "---":
                return None
            header = []
            for line in stream:
                if line.strip() == "---":
                    break
                header.append(line.rstrip("\r\n"))
            else:
                return None
    except UnicodeError:
        raise InventoryReadError(f"{path}: SKILL.md の文字コードを解釈できません") from None
    active = [(len(line) - len(line.lstrip(" ")), line.lstrip(" "))
              for line in header if line.strip() and not line.lstrip().startswith("#")]
    if not active:
        return None
    indent = min(level for level, _ in active)
    fields = {}
    current = None
    for level, line in active:
        if line.startswith("\t"):
            raise InventoryReadError(f"{path}: SKILL.md の見出しを解決できません")
        if level != indent:
            if current is not None:
                fields[current][1].append(line)
            continue
        match = HEADER_KEY.fullmatch(line)
        if not match:
            raise InventoryReadError(f"{path}: SKILL.md の見出しを解決できません")
        key = next(value for value in match.groups()[:3] if value is not None)
        if key in fields:
            return None  # duplicate keys are invalid in Codex's frontmatter
        fields[key] = (match[4], [])
        current = key

    if "description" not in fields:
        return None
    description, description_lines = fields["description"]
    if not re.split(r"\s+#|^#", description.strip(), maxsplit=1)[0] and not description_lines:
        return None
    if description.strip() in ("null", "~", "''", '""'):
        return None

    value, continued = fields.get("name", ("", []))
    value = value.strip()
    if value.startswith(("'", '"')):
        quoted = QUOTED_NAME.fullmatch(value)
        if not quoted or continued:
            raise InventoryReadError(f"{path}: SKILL.md の name を解決できません")
        scalar = quoted[1]
        try:
            value = json.loads(scalar) if scalar.startswith('"') else scalar[1:-1].replace("''", "'")
        except ValueError:
            raise InventoryReadError(f"{path}: SKILL.md の name を解決できません") from None
    else:
        value = re.split(r"\s+#|^#", value, maxsplit=1)[0].strip()
        if value.lower() in ("null", "~"):
            value = ""
        if re.fullmatch(r"[>|][1-9+-]{0,2}", value):
            value = " ".join(continued)
        elif value.startswith(("[", "{", "&", "*", "!", "?", ">", "|")):
            raise InventoryReadError(f"{path}: SKILL.md の name を解決できません")
        else:
            value = " ".join([value, *continued])
    name = " ".join(value.split()) or " ".join(path.parent.name.split()) or "skill"
    return name if len(name) <= 64 else None


def path_namespace(path, cache):
    for parent in path.parents:
        if parent not in cache:
            cache[parent] = None
            for relative in LEGACY_MANIFESTS:
                manifest = parent / relative
                contents = read_file(manifest)
                if contents is None:
                    continue
                try:
                    data = json.loads(contents)
                except ValueError:
                    break
                if isinstance(data, dict) and isinstance(data.get("name", ""), str):
                    value = data.get("name", "")
                    cache[parent] = value if value.strip() else parent.name
                break
        if cache[parent] is not None:
            return cache[parent]
    return None


def semver(version):
    match = re.fullmatch(
        r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
        r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
        r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?",
        version,
    )
    if not match:
        return None
    numbers = tuple(map(int, match.groups()[:3]))
    if max(numbers) >= 2**64:
        return None
    pre = match[4].split(".") if match[4] else []
    if any(item.isdigit() and item.startswith("0") and len(item) > 1 for item in pre):
        return None
    build = version.partition("+")[2].split(".") if "+" in version else []
    return (numbers, not pre, tuple((0, int(item)) if item.isdigit() else (1, item) for item in pre),
            tuple((0, len(item.lstrip("0")), item.lstrip("0"), len(item))
                  if item.isdigit() else (1, item) for item in build))


def compare_versions(left, right):
    a, b = semver(left), semver(right)
    if a is None or b is None:
        a, b = left, right
    return (a > b) - (a < b)


def active_version(scan, base):
    scan.watch(base)
    info = metadata(base)
    if info is None:
        return None
    if not stat.S_ISDIR(info.st_mode):
        raise InventoryReadError(f"{base}: 採用版の置き場の読み取り失敗")
    versions = [path.name for path in sorted(base.iterdir())
                if stat.S_ISDIR(path.lstat().st_mode) and re.fullmatch(r"[A-Za-z0-9._+-]+", path.name)]
    if not versions:
        return None
    return base / ("local" if "local" in versions else sorted(versions, key=cmp_to_key(compare_versions))[-1])


def remote_plugin_keys(scan, cache):
    # Remote enablement comes from the account's installed list at runtime.
    # Inventory all local candidates without reading auth or querying the service.
    root = cache / REMOTE_MARKETPLACE
    scan.watch(root)
    if metadata(root, follow=False) is None:
        return set()
    keys = set()
    for path in sorted(root.iterdir()):
        if path.name.startswith("."):
            continue
        if (not re.fullmatch(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*", path.name)
                or not path.is_dir()):
            raise InventoryReadError(f"{path}: リモートプラグインの置き場を解決できません")
        keys.add(f"{path.name}@{REMOTE_MARKETPLACE}")
    return keys


def plugin_skills(scan, codex_home, config):
    features = table(config.get("features", {}), "features")
    if not config_flag(features, "plugins", True):
        return
    cache = codex_home / "plugins/cache"
    plugins = table(config.get("plugins", {}), "plugins")
    default = config_flag(table(plugins.get("_default", {}), "plugins._default"), "enabled", True)
    remote = remote_plugin_keys(scan, cache)
    for key in sorted((plugins.keys() - {"_default"}) | remote):
        is_remote = key in remote
        enabled = config_flag(table(plugins.get(key, {}), "plugins"), "enabled", default)
        if not enabled and not is_remote:
            continue
        match = re.fullmatch(r"([A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*)@([A-Za-z0-9_-]+)", key)
        if match is None:
            raise FilterError("plugins: プラグイン ID の形式が不正です")
        base = cache / match[2] / match[1]
        version = active_version(scan, base)
        error_type = InventoryReadError if is_remote else FilterError
        if version is None:
            if is_remote:
                raise InventoryReadError(f"{base}: リモートプラグインの採用版を解決できません")
            continue
        try:
            loaded = scan.installed_manifest(version)
        except FilterError as error:
            if is_remote:
                raise InventoryReadError(str(error)) from None
            raise
        if loaded is None:
            if is_remote:
                raise InventoryReadError(f"{version}: リモートプラグインの定義を解決できません")
            continue
        manifest, agent = loaded
        namespace = manifest.get("name", "" if not agent else None)
        if not isinstance(namespace, str):
            raise error_type(f"{version}: プラグイン名を解決できません")
        namespace = namespace if namespace.strip() else version.name
        paths = "./skills" if agent else manifest.get("skills", [])
        if isinstance(paths, str):
            paths = [paths]
        if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
            raise error_type(f"{version}: プラグインの skill の置き場を解決できません")
        relative_roots = [path[2:] for path in paths
                          if path.startswith("./") and len(path) > 2
                          and not path.startswith(".//") and ".." not in Path(path[2:]).parts]
        if is_remote and len(relative_roots) != len(paths):
            raise InventoryReadError(f"{version}: リモートプラグインの skill の置き場を解決できません")
        roots = {version / relative for relative in relative_roots} or {version / "skills"}
        if not agent:
            roots.add(version / ".codex-plugin/migrated-command-skills")
        actual_version = version.resolve(strict=True)
        for root in sorted(roots):
            scan.watch(root)
            for discovery, actual in discover(root, agent_root=actual_version if agent else None):
                name = skill_name(actual)
                yield Skill(discovery, actual, qualified_name(namespace, name), key,
                            discovery.relative_to(version))


def qualified_name(namespace, name):
    if namespace and name:
        qualified = f"{namespace}:{name}"
        return qualified if len(qualified) <= 129 else None
    return name


def inventory(scan, home, codex_home, work, base, managed):
    discovery_config = merge(base, managed)
    markers = discovery_config.get("project_root_markers", [".git"])
    if not isinstance(markers, list) or any(not isinstance(marker, str) for marker in markers):
        raise FilterError("project_root_markers: 文字列の配列を指定してください")
    project_dirs, effective = project_config(scan, work, codex_home, discovery_config, markers)
    effective = merge(effective, managed)
    roots = [(home / ".agents/skills", True), (codex_home / "skills", True),
             (SYSTEM_CONFIG / "skills", True)]
    roots += [(folder / ".agents/skills", True) for folder in ancestors(work, markers)]
    roots += [(folder / "skills", True) for folder in project_dirs]
    bundled = table(table(effective.get("skills", {}), "skills").get("bundled", {}), "skills.bundled")
    if config_flag(bundled, "enabled", True):
        roots.append((codex_home / "skills/.system", False))

    names = {}
    namespaces = {}
    skills = []
    for root, follow in dict.fromkeys(roots):
        scan.watch(root)
        for discovery, actual in discover(root, follow=follow):
            if actual not in names:
                names[actual] = skill_name(actual)
            name = names[actual]
            namespace = path_namespace(actual, namespaces) if name else None
            skills.append(Skill(discovery, actual, qualified_name(namespace, name), None, None))
    skills.extend(plugin_skills(scan, codex_home, effective))
    return skills


def disabled_paths(user, codex_home, skills):
    rules = table(user.get("skills", {}), "skills").get("config", [])
    if not isinstance(rules, list):
        raise FilterError("skills.config: 配列を指定してください")
    disabled = set()
    by_name = defaultdict(set)
    for skill in skills:
        by_name[skill.name].add(skill.actual)
    for rule in rules:
        rule = table(rule, "skills.config")
        path, name = rule.get("path"), rule.get("name")
        if (path is None) == (name is None):
            continue
        enabled = config_flag(rule, "enabled", None)
        if path is not None:
            if not isinstance(path, str) or not path:
                raise FilterError("skills.config: パスが不正です")
            selector = Path(path)
            if selector.parts[:1] == ("~",):
                selector = Path.home().joinpath(*selector.parts[1:])
            selector = Path(os.path.abspath(codex_home / selector))
            selected = {selector.resolve(strict=True) if metadata(selector) is not None else selector}
        else:
            if not isinstance(name, str):
                raise FilterError("skills.config: 名前が不正です")
            selected = by_name[name.strip()]
        if enabled:
            disabled.difference_update(selected)
        else:
            disabled.update(selected)
    return disabled


def requested_names(raw):
    if not raw:
        return ()
    if any(unicodedata.category(char) in ("Cc", "Cf", "Zl", "Zp") or char in "*?[]" for char in raw):
        raise FilterError("CODEX_SKILLS_ALLOW: 制御文字またはワイルドカードは不正です")
    names = tuple(dict.fromkeys(value.strip() for value in raw.split(",")))
    if "" in names:
        raise FilterError("CODEX_SKILLS_ALLOW: 空の要素は不正です")
    return names


def under_agents(path, agents, actual_agents, agents_stat):
    if path.is_relative_to(agents) or path.is_relative_to(actual_agents):
        return True
    # On case-insensitive filesystems realpath can preserve an alias's spelling.
    return agents_stat is not None and any(
        os.path.samestat(info, agents_stat)
        for parent in path.parents if (info := metadata(parent)) is not None
    )


def keep_paths(rows, home, skills, disabled, requested, suppress, *, recheck=False):
    by_name = defaultdict(list)
    by_path = defaultdict(list)
    for skill in skills:
        by_name[skill.name].append(skill)
        by_path[skill.actual].append(skill)
    keep = set()
    notices = []
    for name, provider, rel in rows:
        matches = by_name[name]
        if provider == "home":
            placed = home / rel
            expected = placed.resolve(strict=True) if metadata(placed) is not None else placed
            paths = {skill.actual for skill in matches if skill.plugin is None and skill.actual == expected}
        else:
            paths = {skill.actual for skill in matches if skill.plugin == provider
                     and skill.plugin_relative == Path(rel)}
        if len(paths) > 1:
            raise FilterError(f"{name}: 初期項目が複数実体に一致します")
        enabled = paths - disabled
        if enabled:
            keep.update(enabled)
        else:
            reason = "既存設定で無効" if paths else "未導入または対象外"
            notices.append(f"skill 絞り込み: {name}（{reason}）")

    agents = home / ".agents"
    agents_stat = metadata(agents) if suppress and requested else None
    actual_agents = agents.resolve(strict=True) if agents_stat is not None else agents
    for name in requested:
        matches = by_name[name]
        paths = {skill.actual for skill in matches}
        if not paths:
            raise FilterError(f"CODEX_SKILLS_ALLOW: {name!r} は未知の名前です")
        if len(paths) > 1:
            raise FilterError(f"CODEX_SKILLS_ALLOW: {name!r} は複数実体に一致します")
        actual = next(iter(paths))
        if suppress:
            for skill in by_path[actual]:
                resolved = skill.discovery.resolve(strict=True) if recheck else skill.actual
                if (under_agents(skill.discovery, agents, actual_agents, agents_stat)
                        or under_agents(resolved, agents, actual_agents, agents_stat)):
                    raise FilterError(f"CODEX_SKILLS_ALLOW: {name!r} は探索経路または実体が ~/.agents 配下で"
                                      "レビューの前置きが読み込みを禁止します。CODEX_REVIEW_ALLOW_SKILLS=1 で許可できます")
                if resolved != skill.actual:
                    raise FilterError(f"CODEX_SKILLS_ALLOW: {name!r} は列挙後に実体が変更されました")
        if paths & disabled:
            raise FilterError(f"CODEX_SKILLS_ALLOW: {name!r} は既存設定で無効です。有効な skill を指定してください")
        keep.update(paths)
    return keep, notices


def skill_override(paths):
    encoded = "skills.config=[" + ", ".join(
        "{path=" + json.dumps(str(path), ensure_ascii=False) + ", enabled=false}" for path in paths
    ) + "]"
    expected = [{"path": str(path), "enabled": False} for path in paths]
    try:
        decoded = tomllib.loads(encoded)["skills"]["config"]
    except ValueError:
        raise FilterError("skill 起動引数を TOML として解釈できません") from None
    if decoded != expected or any(item["enabled"] is not False for item in decoded):
        raise FilterError("skill 起動引数が想定したパスと型に一致しません")
    return encoded


def check_arg_size(args):
    arg_sizes = [len(os.fsencode(arg)) + 1 for arg in args]
    env_size = sum(len(key) + len(value) + 2 for key, value in os.environb.items())
    # Leave room for exec bookkeeping and environment changes by the shell and nohup.
    if (max(arg_sizes) >= 131072 or sum(arg_sizes) + env_size
            + 8 * (len(args) + len(os.environ) + 2) + 4096 >= os.sysconf("SC_ARG_MAX")):
        raise FilterError("skill 起動引数がシステムの上限を超えます")


def read_version():
    try:
        result = subprocess.run(["codex", "--version"], capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    version = re.fullmatch(rb"codex-cli ([0-9][0-9A-Za-z.+-]{0,63})\s*", result.stdout)
    if result.returncode or version is None:
        return None
    return version[1].decode("ascii")


def skip_filter(version, status, reason):
    # Paths may contain newlines. Keep the diagnostic to one stderr line.
    reason = " ".join(reason.splitlines())
    check = f"codex --version（検証済み {CLI_VERSION}）"
    if status == "inventory_unreadable":
        check += "と表示された置き場の種類・読み取り権限"
    print(f"警告: skill と記憶の絞り込みを省略（Codex CLI {version or '版不明'}、{reason}）。"
          f" {check}を確認してください。", file=sys.stderr)
    print(f"launch_skills_filter=skipped:{status}")


def timed_out(_signal, _frame):
    raise FilterError("skill 列挙の期限を超えました")


def prepare_filter(work, memories, argv, requested, check_review, version_supported):
    signal.signal(signal.SIGALRM, timed_out)
    signal.alarm(SCAN_TIMEOUT)
    start = time.monotonic()
    home = Path(os.environ["HOME"]).absolute()
    custom_home = os.environ.get("CODEX_HOME")
    codex_home = Path(custom_home).resolve(strict=True) if custom_home else home / ".codex"
    if custom_home and not codex_home.is_dir():
        raise InventoryReadError(f"{codex_home}: CODEX_HOME の読み取り失敗（ディレクトリではありません）")
    scan = Scan()
    system = scan.config(SYSTEM_CONFIG / "config.toml")
    user = scan.config(codex_home / "config.toml")
    managed = scan.config(SYSTEM_CONFIG / "managed_config.toml")
    skills = inventory(scan, home, codex_home, Path(work).resolve(strict=True), merge(system, user), managed)
    if not version_supported:
        # Resolve review additions even when no filter overrides will be passed.
        keep_paths([], home, skills, set(), requested, check_review)
        scan.unchanged()
        keep_paths([], home, skills, set(), requested, check_review, recheck=True)
        return
    rows = [line.split("\t") for line in ALLOWLIST.read_text(encoding="utf-8").splitlines()]
    disabled = disabled_paths(user, codex_home, skills)
    keep, notices = keep_paths(rows, home, skills, disabled, requested, check_review)
    paths = {skill.actual for skill in skills}
    removed = sorted(paths - keep - disabled)
    override = skill_override(removed)
    memory_args = ["-c", "memories.use_memories=false"] if memories == "off" else []
    check_arg_size(["nohup", "codex", *argv, "-c", override, *memory_args])
    scan.unchanged()
    if check_review:
        keep_paths([], home, skills, disabled, requested, check_review, recheck=True)
    for notice in notices:
        print(notice, file=sys.stderr)
    print(f"skill 絞り込み: on 列挙={len(paths)} 残す={len(keep)} 外す={len(removed)} "
          f"記憶={memories} {time.monotonic() - start:.3f}s", file=sys.stderr)
    print(override)
    if memory_args:
        print(memory_args[1])


def main():
    work, suppressed, memories, *argv = sys.argv[1:]
    requested = requested_names(os.environ.get("CODEX_SKILLS_ALLOW", ""))
    check_review = suppressed == "yes" and bool(requested)
    version = read_version()
    version_supported = version == CLI_VERSION
    if version_supported or check_review:
        try:
            prepare_filter(work, memories, argv, requested, check_review, version_supported)
        except (InventoryReadError, OSError) as error:
            if isinstance(error, OSError):
                detail = os.strerror(error.errno) if error.errno in errno.errorcode else "入出力エラー"
                reason = f"{error.filename or '置き場'}: 読み取り・パス解決失敗（{detail}）"
            else:
                reason = str(error)
            if check_review:
                raise FilterError(f"{reason}。レビューの追加指定が読み込み禁止に当たらないか確認できません") from None
            skip_filter(version, "inventory_unreadable", reason)
            return
        finally:
            signal.alarm(0)
    if not version_supported:
        reason = "未検証の版" if version else "--version の出力から版を識別できません"
        skip_filter(version, "unverified_version", reason)


if __name__ == "__main__":
    try:
        main()
    except FilterError as error:
        sys.exit(f"skill 絞り込み: {error}")
    except (ValueError, UnicodeError, RuntimeError, subprocess.TimeoutExpired):
        sys.exit("skill 絞り込み: 設定またはパスを解決できません")
