#!/usr/bin/env python3
"""Load vault.toml and check the toolchain. Every script imports this first.

Importing runs the preflight: it exits 2 with the fix when Python or PyYAML is
too old or missing. Keep this module free of syntax newer than Python 3.6 above
the version check, so an old interpreter reaches the message.
"""
import sys


def _use_venv():
    """Re-run the script under the repository's .venv (from make setup) when this interpreter
    cannot run it and scripts/venv-python names a safe one (untracked, not a symlink, or the
    primary checkout's from a worktree). Returns only when there is nothing to switch to."""
    import os
    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        exe = subprocess.check_output(["sh", os.path.join(root, "scripts", "venv-python")], cwd=root,
                                      stderr=subprocess.DEVNULL).decode().strip()
    except (OSError, subprocess.CalledProcessError):
        return
    script = sys.argv[0] if sys.argv else ""
    venv = os.path.dirname(os.path.dirname(exe)) if exe else ""
    if (exe and os.path.realpath(sys.prefix) != os.path.realpath(venv) and os.access(exe, os.X_OK)
            and os.path.isfile(script)):
        os.execv(exe, [exe] + sys.argv)


if sys.version_info < (3, 11):
    _use_venv()
    sys.stderr.write(
        "vault-kit needs Python >= 3.11 (found %d.%d.%d); run make setup SETUP_PYTHON=python3.12 "
        "to build .venv with a newer one\n" % sys.version_info[:3])
    raise SystemExit(2)
try:
    import yaml  # noqa: F401
except ImportError:
    _use_venv()
    sys.stderr.write("PyYAML missing; run make setup, which installs requirements-dev.txt into "
                     ".venv (scripts switch to .venv/bin/python3 when it exists)\n")
    raise SystemExit(2)

import os
from pathlib import Path
import re
import stat
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parent.parent
INIT_HINT = 'run scripts/init-vault --name <slug> --title "<Title>" --scope "<scope>"'


def symlink_component(root, path):
    """The first path from root down to path (inclusive) that is a symlink, or None.

    path must sit lexically under root. A committed symlink anywhere on that walk would
    send a write outside the vault, so every writer checks this first.
    """
    root = Path(root)
    current = root
    for part in Path(path).relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            return current
    return None


def refuse_symlink(root, path):
    link = symlink_component(root, path)
    if link is not None:
        raise SystemExit(f"{Path(path).relative_to(root)}: refusing to write through the symlink "
                         f"{link.relative_to(root)}; replace it with a regular file or directory")


def safe_write(root, path, text):
    """Write text to path under root via a temp file and a rename, never through a symlink."""
    path = Path(path)
    refuse_symlink(root, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(tmp, stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def load(root=None):
    """Return {template, name, title, scope, root_env, deny} from vault.toml."""
    path = Path(root or ROOT) / "vault.toml"
    data = _read_toml(path)
    deny = deny_list(data, path)
    config = {"template": data.get("template", False)}
    for key in ("name", "title", "scope", "root_env"):
        value = data.get(key, "")
        if not isinstance(value, str):
            raise SystemExit(f"{path}: {key} must be a string")
        config[key] = value
    if not isinstance(config["template"], bool):
        raise SystemExit(f"{path}: template must be true or false")
    if config["name"] and not config["root_env"]:
        config["root_env"] = derive_root_env(config["name"])
    config["deny"] = deny
    return config


def _read_toml(path):
    try:
        return tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"{path}: not found; vault.toml is required at the vault root")
    except tomllib.TOMLDecodeError as error:
        raise SystemExit(f"{path}: invalid TOML: {error}")


def deny_list(data, path):
    """The [redaction] deny list from parsed vault.toml data, checked and compiled once."""
    deny = data.get("redaction", {}).get("deny", [])
    if not isinstance(deny, list) or any(not isinstance(p, str) for p in deny):
        raise SystemExit(f"{path}: [redaction] deny must be a list of regex strings")
    compile_deny(deny, path)  # refuse a bad pattern here, so every caller sees the same error
    return deny


def load_deny(path):
    """The deny list of another copy of vault.toml (HEAD's, or a range base's)."""
    return deny_list(_read_toml(path), path)


def compile_deny(deny, path="vault.toml"):
    """Compile [redaction] deny patterns, case-insensitive, numbered from 1.

    An error names the pattern by number only: the deny list names what must stay
    private, so its text never goes to a terminal or CI log.
    """
    compiled = []
    for number, pattern in enumerate(deny, 1):
        try:
            compiled.append(re.compile(pattern, re.IGNORECASE))
        except re.error as error:
            # error.msg can quote the pattern (a group name, say), so only the position is shown.
            raise SystemExit(f"{path}: [redaction] deny pattern {number} is not a valid regex "
                             f"(error at position {error.pos}); patterns are numbered from 1")
    return compiled


# Vault identity. The slug becomes skill names and the QMD collection; the root env var is
# rendered into shell commands, so both are held to a strict charset.
SLUG_RE = r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$"
SLUG_MAX = 31
ROOT_ENV_RE = r"^[A-Z][A-Z0-9_]*$"
# Title and scope are rendered into YAML frontmatter and Markdown prose: one printable line,
# none of the characters that would let them break out of either. Only printable ASCII and
# Latin-1 letters are allowed, which also keeps out invisible characters that isprintable()
# accepts (U+115F, U+1160, U+3164, U+FFA0, U+2800, U+180E and format characters).
FREE_TEXT_FORBIDDEN = set('`"\\${}<>|')
FREE_TEXT_ALLOWED = re.compile(r"[\x20-\x7e\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u00ff]*")
TITLE_MAX, SCOPE_MAX = 64, 160
TEMPLATES_DIR = "templates/skills"
PLACEHOLDER = re.compile(r"\{\{(name|title|scope|root_env)\}\}")
DESCRIPTION_MAX, COMPATIBILITY_MAX = 1024, 500


def derive_root_env(name):
    return re.sub(r"[^A-Za-z0-9]+", "_", name).upper() + "_ROOT"


def identity_errors(config):
    """Problems with name/title/scope/root_env, as messages naming the field and value."""
    errors = []
    name = config.get("name", "")
    if not re.fullmatch(SLUG_RE, name) or len(name) > SLUG_MAX:
        errors.append(f"name {name!r} must match {SLUG_RE} and be at most {SLUG_MAX} characters")
    for key, limit in (("title", TITLE_MAX), ("scope", SCOPE_MAX)):
        value = config.get(key, "")
        bad = sorted(FREE_TEXT_FORBIDDEN.intersection(value))
        if not value.strip():
            errors.append(f"{key} is empty")
        elif len(value) > limit:
            errors.append(f"{key} is {len(value)} characters; the limit is {limit}")
        elif not FREE_TEXT_ALLOWED.fullmatch(value) or bad or "{{" in value:
            others = sorted({f"U+{ord(c):04X}" for c in value if not FREE_TEXT_ALLOWED.fullmatch(c)})
            shown = " ".join(bad + others) or "{{"
            errors.append(f"{key} {value!r} contains {shown}; use one plain line of printable ASCII "
                          f"and Latin-1 letters, without {''.join(sorted(FREE_TEXT_FORBIDDEN))}")
        if key == "scope" and ";" in value:
            errors.append(f"scope {value!r} must be one clause (no ';')")
    root_env = config.get("root_env", "")
    if not re.fullmatch(ROOT_ENV_RE, root_env):
        errors.append(f"root_env {root_env!r} must match {ROOT_ENV_RE}")
    return errors


def skill_targets(root, name):
    """Map each template under templates/skills/ to its rendered path under skills/.

    templates/skills/<kind>/skill.md.tmpl          -> skills/<name>-<kind>/SKILL.md
    templates/skills/<kind>/<rest>/<file>.md.tmpl  -> skills/<name>-<kind>/<rest>/<file>.md
    """
    base = Path(root) / TEMPLATES_DIR
    targets = {}
    if not base.is_dir():
        return targets
    for template in sorted(base.rglob("*.tmpl")):
        rel = template.relative_to(base)
        kind, rest = rel.parts[0], Path(*rel.parts[1:])
        out = Path("SKILL.md") if rest == Path("skill.md.tmpl") else rest.with_suffix("")
        targets[template.relative_to(root)] = Path("skills") / f"{name}-{kind}" / out
    return targets


def _yaml_single(value):
    return value.replace("'", "''")


def render_text(text, config, template_rel):
    """Substitute placeholders and add the generated-file comment.

    Inside frontmatter, values sit in single-quoted YAML scalars, so a single quote is
    doubled. The comment goes after the frontmatter (SKILL.md must open with it) or at the
    top of a file without frontmatter.
    """
    def substitute(chunk, in_yaml):
        return PLACEHOLDER.sub(
            lambda m: _yaml_single(config[m.group(1)]) if in_yaml else config[m.group(1)], chunk)

    notice = (f"<!-- Generated from {template_rel.as_posix()} by scripts/init-vault --render-skills; "
              "do not edit. Edit the template and re-render. -->\n")
    if text.startswith("---\n"):
        front, body = text[4:].split("\n---\n", 1)
        rendered = "---\n" + substitute(front, True) + "\n---\n" + notice + substitute(body, False)
    else:
        rendered = notice + substitute(text, False)
    if "{{" in rendered or "}}" in rendered:
        raise SystemExit(f"{template_rel}: unknown placeholder left after rendering; "
                         "only {{name}} {{title}} {{scope}} {{root_env}} are defined")
    return rendered


def split_frontmatter(text):
    """(mapping, body) for text that opens with a `---` frontmatter block; ({}, text) otherwise.

    Raises ValueError when the block is unclosed, is not valid YAML, or is empty or not a
    mapping, so every caller rejects the same malformed files the same way.
    """
    if not text.startswith("---\n"):
        return {}, text
    rest = text[4:]
    if rest.startswith("---\n"):
        front, body = "", rest[4:]
    elif "\n---\n" in rest:
        front, body = rest.split("\n---\n", 1)
    else:
        raise ValueError("frontmatter has no closing ---")
    try:
        data = yaml.safe_load(front)
    except yaml.YAMLError as error:
        raise ValueError(f"frontmatter is not valid YAML: {error}") from None
    if not isinstance(data, dict) or not data:
        raise ValueError("frontmatter must be a non-empty mapping")
    return data, body


def frontmatter_errors(rel, text):
    """Agent Skills limits on a rendered SKILL.md: name matches its directory, lengths."""
    if rel.name != "SKILL.md":
        return []
    try:
        front, _ = split_frontmatter(text)
    except ValueError as error:
        return [f"{rel}: {error}"]
    if not front:
        return [f"{rel}: SKILL.md must open with a frontmatter block"]
    errors = []
    if front.get("name") != rel.parent.name:
        errors.append(f"{rel}: name {front.get('name')!r} must equal its directory {rel.parent.name!r}")
    for key, limit in (("description", DESCRIPTION_MAX), ("compatibility", COMPATIBILITY_MAX)):
        value = front.get(key)
        if not isinstance(value, str) or not value or len(value) > limit:
            size = len(value) if isinstance(value, str) else 0
            errors.append(f"{rel}: {key} is {size} characters; it must be 1-{limit}")
    return errors


def render_skills(root, config):
    """Return {skills/<path>: text} for every template, checked against the skill limits."""
    errors = identity_errors(config)
    if errors:
        raise SystemExit("vault identity: " + "; ".join(errors))
    rendered = {}
    for template_rel, out in skill_targets(root, config["name"]).items():
        text = render_text((Path(root) / template_rel).read_text(encoding="utf-8"), config, template_rel)
        problems = frontmatter_errors(out, text)
        if problems:
            raise SystemExit("\n".join(problems))
        rendered[out] = text
    if not rendered:
        raise SystemExit(f"no templates under {Path(root) / TEMPLATES_DIR}")
    return rendered


def rendered_skill_errors(root, config):
    """Differences between skills/ and a fresh render of templates/ into a temp dir."""
    import filecmp
    import tempfile
    root = Path(root)
    expected = render_skills(root, config)
    errors = []
    with tempfile.TemporaryDirectory(prefix="vault-render-") as temp:
        for rel, text in expected.items():
            (Path(temp) / rel).parent.mkdir(parents=True, exist_ok=True)
            (Path(temp) / rel).write_text(text, encoding="utf-8")
        for rel in sorted(expected):
            live = root / rel
            if not live.is_file() or live.is_symlink() or not filecmp.cmp(live, Path(temp) / rel, shallow=False):
                errors.append(f"{rel} differs from templates/; run scripts/init-vault --render-skills")
    # A file inside a rendered skill dir that no template produces is also drift.
    for skill_dir in sorted({rel.parts[1] for rel in expected}):
        for live in sorted((root / "skills" / skill_dir).rglob("*")):
            rel = live.relative_to(root)
            if live.is_file() and rel not in expected and "__pycache__" not in rel.parts:
                errors.append(f"{rel} differs from templates/ (no template renders it); "
                              "run scripts/init-vault --render-skills")
    return errors


COMMIT_RE = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


def checked_base(root, base):
    """base when it is empty or a full commit id Git can read; otherwise exit 2."""
    import subprocess
    if base and not COMMIT_RE.fullmatch(base):
        sys.stderr.write("SECRETS_BASE must be empty or a full lowercase commit id "
                         "(40 or 64 hex characters); nothing was scanned\n")
        raise SystemExit(2)
    if base and subprocess.run(["git", "cat-file", "-e", f"{base}^{{commit}}"], cwd=root,
                               capture_output=True).returncode:
        sys.stderr.write(f"SECRETS_BASE {base} is not a commit in this repository (fetch it first); "
                         "nothing was scanned\n")
        raise SystemExit(2)
    return base


# Vale config is read by editor plugins (vale-ls and friends) the moment it lands on disk,
# before anyone reviews an engine update, so its contents are allowlisted rather than trusted.
# engine-update runs vale_errors on a fetched ref before copying; check-vault runs it on the tree.
VALE_INI = ".vale.ini"
# Names Vale loads as config when it walks up from a linted file. Only the root .vale.ini is allowed.
VALE_CONFIG_NAMES = {".vale.ini", "_vale.ini", "vale.ini", ".vale", "_vale"}
VALE_STYLES_PATH = ".vale/styles"
VALE_ROOT_KEYS = {"stylespath", "minalertlevel"}
VALE_UNCHECKED_KEYS = {"tokenignores", "blockignores"}  # regex values; a line can hold nothing else
VALE_LEVELS = {"suggestion", "warning", "error"}
VALE_RULE_SETTINGS = VALE_LEVELS | {"yes", "no"}
VALE_BUILTIN_STYLE = "vale"  # Vale.Spelling and friends; never enabled from here
# Every rule kind except `script` (Tengo code) and `spelling` (reads dictionaries from disk).
VALE_RULE_KINDS = {"existence", "substitution", "occurrence", "repetition", "consistency",
                   "conditional", "capitalization", "metric", "sequence"}
VALE_NAME_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
VALE_SECTION_RE = re.compile(r"\[([^\[\]]+)\]")
VALE_LINE_BREAKS = re.compile("[\r\x0b\x0c\x1c-\x1e\x85\u2028\u2029]")
VALE_KEY_RE = re.compile(r"([A-Za-z0-9_.-]+)[ \t]*=[ \t]*(.*)")


def vale_ini_lines(text):
    """(section, key, value) for each setting, or a refusal.

    Parsed line by line on purpose: Python's configparser and Vale's Go INI library disagree
    (an indented line is a continuation to one and a new key or section to the other), so
    only the subset both read the same way is accepted: flush-left `[section]` and
    `key = value` lines, `#`/`;` comment lines, and blank lines. No continuations, no
    multi-line or quoted-block values, no duplicate keys, no [DEFAULT].
    """
    settings, seen, section = [], set(), None
    # Split on newline only, as go-ini does: str.splitlines() also splits on \r, U+2028 and
    # friends, which would let one Go line hide a second value behind a "comment".
    for number, line in enumerate(text.split("\n"), 1):
        if VALE_LINE_BREAKS.search(line):
            return None, f"line {number} holds a carriage return or Unicode line separator"
        if not line.strip() or line[0] in "#;":
            continue
        if line[0].isspace():
            return None, f"line {number} is indented; Vale and this check would read it differently"
        if line.rstrip().endswith("\\"):
            return None, f"line {number} ends in a line continuation"
        heading = VALE_SECTION_RE.fullmatch(line.rstrip())
        if heading:
            section = heading.group(1).strip()
            if section.casefold() == "default":
                return None, f"line {number}: [{section}] is not allowed"
            continue
        setting = VALE_KEY_RE.fullmatch(line.rstrip())
        if not setting:
            return None, f"line {number} is not a [section] or key = value line"
        key, value = setting.group(1).casefold(), setting.group(2).strip()
        if value.startswith(('"""', "`")):
            return None, f"line {number}: a quoted or multi-line value is not allowed"
        if (section, key) in seen:
            return None, f"line {number}: {key} is set twice"
        seen.add((section, key))
        settings.append((section, key, value))
    return settings, None


def vale_ini_errors(text):
    """Why a .vale.ini falls outside the allowlist; empty when it is inside."""
    settings, refusal = vale_ini_lines(text)
    if refusal:
        return [f"{VALE_INI}: {refusal}"]
    errors = []
    for section, key, value in settings:
        if section is None:
            if key not in VALE_ROOT_KEYS:
                errors.append(f"{VALE_INI}: top-level key {key} is not allowed")
            elif key == "stylespath" and value != VALE_STYLES_PATH:
                errors.append(f"{VALE_INI}: StylesPath must be {VALE_STYLES_PATH}, got {value!r}")
            elif key == "minalertlevel" and value.casefold() not in VALE_LEVELS:
                errors.append(f"{VALE_INI}: MinAlertLevel {value!r} is not a level")
        elif not section.startswith("*"):
            errors.append(f"{VALE_INI}: section [{section}] is not a file glob")
        elif key == "basedonstyles":
            names = [name.strip() for name in value.split(",") if name.strip()]
            bad = [name for name in names
                   if not VALE_NAME_RE.fullmatch(name) or name.casefold() == VALE_BUILTIN_STYLE]
            if bad:
                errors.append(f"{VALE_INI}: [{section}] BasedOnStyles names a style outside "
                              f"{VALE_STYLES_PATH}: {', '.join(bad)}")
        elif key in VALE_UNCHECKED_KEYS:
            continue
        elif "." in key:
            style, _, rule = key.partition(".")
            if (style == VALE_BUILTIN_STYLE or not VALE_NAME_RE.fullmatch(style)
                    or not VALE_NAME_RE.fullmatch(rule)):
                errors.append(f"{VALE_INI}: [{section}] {key} is not a rule of a style in {VALE_STYLES_PATH}")
            elif value.casefold() not in VALE_RULE_SETTINGS:
                errors.append(f"{VALE_INI}: [{section}] {key} = {value!r} is not a level or YES/NO")
        else:
            errors.append(f"{VALE_INI}: [{section}] key {key} is not allowed")
    return errors


class _UniqueKeyLoader(yaml.SafeLoader):
    """safe_load that refuses a repeated mapping key, which PyYAML would silently resolve to
    the last value (so `extends: script` then `extends: existence` would read as existence)."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise yaml.constructor.ConstructorError(None, None, f"duplicate key {key!r}",
                                                        key_node.start_mark)
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def vale_rule_errors(rel, text):
    """Why a Vale rule file falls outside the allowlist; empty when it is inside."""
    try:
        data = yaml.load(text, Loader=_UniqueKeyLoader)  # noqa: S506  (a SafeLoader subclass)
    except yaml.YAMLError as error:
        if "duplicate key" in str(error):
            return [f"{rel}: a key is set twice; Vale and this check would read it differently"]
        return [f"{rel}: not valid YAML"]
    if not isinstance(data, dict):
        return [f"{rel}: a Vale rule must be a mapping"]
    kind = data.get("extends")
    if kind not in VALE_RULE_KINDS:
        return [f"{rel}: extends {kind!r} is not an allowed rule kind "
                f"({', '.join(sorted(VALE_RULE_KINDS))})"]
    return []


def vale_errors(base, rels):
    """Allowlist errors for the Vale config among rels (paths relative to base).

    Paths compare case-insensitively, because on a case-insensitive disk .Vale/Styles is
    the directory Vale reads as .vale/styles.
    """
    errors = []
    styles = tuple(part.casefold() for part in Path(VALE_STYLES_PATH).parts)
    for rel in rels:
        rel = Path(rel)
        folded = tuple(part.casefold() for part in rel.parts)
        is_config = rel.name.casefold() in VALE_CONFIG_NAMES
        under_vale = folded[:1] == styles[:1]
        if is_config and folded != (VALE_INI,):
            errors.append(f"{rel}: Vale reads this name as config; only the root {VALE_INI} is allowed")
            continue
        if not (is_config or under_vale):
            continue
        if (base / rel).is_symlink():
            errors.append(f"{rel}: a symlink in Vale config; Vale would load its target unchecked")
            continue
        is_rule = (len(rel.parts) == len(styles) + 2 and folded[:len(styles)] == styles
                   and VALE_NAME_RE.fullmatch(rel.parts[-2]) and rel.suffix == ".yml"
                   and VALE_NAME_RE.fullmatch(rel.stem))
        if under_vale and not is_rule:
            errors.append(f"{rel}: only rule files ({VALE_STYLES_PATH}/<style>/<rule>.yml, lowercase) "
                          "are allowed under .vale/")
            continue
        try:
            text = (base / rel).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"{rel}: not UTF-8 text")
            continue
        errors.extend(vale_ini_errors(text) if is_config else vale_rule_errors(rel, text))
    return errors


def check_initialized(root=None):
    """Return an error message when the vault is still a template, else None."""
    config = load(root)
    if config["template"]:
        return f"vault.toml: template = true and name unset; {INIT_HINT}"
    if not config["name"]:
        return f"vault.toml: name unset; {INIT_HINT}"
    return None


if __name__ == "__main__":
    if sys.argv[1:] == ["--check-initialized"]:
        message = check_initialized()
        if message:
            print(message, file=sys.stderr)
            raise SystemExit(1)
        print("PASS: vault is initialized.")
    elif sys.argv[1:] == ["--template"]:
        # CI steps that differ between the template and an instance branch on this.
        print("true" if load()["template"] else "false")
    else:
        raise SystemExit("usage: vaultconf.py --check-initialized | --template")
