#!/usr/bin/env python3
"""Check the vault authoring profile, not all optional OKF features."""
import vaultconf  # toolchain preflight; must precede yaml
from datetime import datetime
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

import yaml

import patternscan

ROOT = Path(__file__).resolve().parent.parent
CONVENTIONAL_FILENAMES = {
    "AGENTS.md", "CLAUDE.md", "README.md", "CHANGELOG.md", "CONTRIBUTING.md",
    "SECURITY.md", "CODE_OF_CONDUCT.md", "LICENSE", "LICENSE.md", "NOTICE",
    "AUTHORS", "COPYING", "CODEOWNERS", "Makefile", "GNUmakefile", "Dockerfile",
    "Containerfile", "CMakeLists.txt", "Cargo.toml", "Cargo.lock", "Gemfile",
    "Gemfile.lock", "Rakefile", "Brewfile", "Procfile", "Vagrantfile", "Justfile",
}


def conventional(path):
    """SKILL.md is the Agent Skills spec filename, conventional only under skills/."""
    if path.name == "SKILL.md":
        return "skills" in path.parts[:-1]
    return path.name in CONVENTIONAL_FILENAMES


def valid_name(path, is_directory=False):
    parts = path.parts if is_directory or not conventional(path) else path.parts[:-1]
    return all(
        re.fullmatch(r"\.?[a-z0-9]+(?:[-.][a-z0-9]+)*", part)
        for part in parts)


IGNORED_PARTS = {".git", "__pycache__", ".venv", ".claude", ".worktrees"}


def ignored(parts):
    return any(part in IGNORED_PARTS for part in parts) or parts[:2] in (
        (".obsidian", "themes"), (".obsidian", "plugins"))


def validate_git_paths(root):
    if not (root / ".git").exists():
        return []
    result = subprocess.run(["git", "ls-files", "-z"], cwd=root,
                            check=True, capture_output=True, text=True)
    errors = []
    seen = set()
    for name in result.stdout.split("\0"):
        # The Makefile, the hooks and the scripts run .venv/bin/python3; a tracked .venv (or a
        # tracked .venv symlink) would let a commit replace the interpreter every check runs on.
        # In any letter case: on a case-insensitive file system .VENV/bin/python3 is .venv's.
        folded = name.casefold()
        if folded == ".venv" or folded.startswith(".venv/"):
            errors.append(f"Git index {name}: .venv must not be tracked; it is the local "
                          "virtualenv from make setup (git rm -r --cached .venv)")
            continue
        if not name or ignored(Path(name).parts):
            continue
        # Names are checked once, by validate() over the same files (make check reads the
        # index's files in the hook's snapshot); only what needs the index itself is here.
        if name.casefold() in seen:
            errors.append(f"Git index {name}: case-insensitive path collision")
        seen.add(name.casefold())
    return errors


# Top-level directories outside the concept-metadata and index rules: raw/ holds
# immutable captures; skills/, apps/ and templates/ hold vault-owned code. They stay inside
# the validate() listed-paths loop, so kebab-case names and the credential-URL scan
# still cover them.
CODE_DIRECTORIES = {"raw", "skills", "apps", "templates"}


def documents(root):
    """Markdown pages under the metadata and index rules, from the same list make check
    covers (listed_paths): a .gitignore'd scratch file is neither validated nor indexed."""
    return sorted(p for p in listed_paths(root)
                  if p.suffix == ".md"
                  and p.relative_to(root).parts[0] not in CODE_DIRECTORIES
                  and not any(part.startswith(".") for part in p.relative_to(root).parts))


def parse(path):
    return vaultconf.split_frontmatter(path.read_text(encoding="utf-8"))


def timestamp(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps require an explicit UTC offset")


# Any scheme (https, ftp, postgres, redis, ...) with user:password before the host.
CREDENTIAL_URL = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s/@]+:[^\s/@]+@", re.IGNORECASE)
# Parts never scanned when walking a tree without Git (the staged snapshot, self-tests).
UNTRACKED_PARTS = {".git", "__pycache__", ".venv"}
DENY_LABEL = "redaction deny pattern"


def listed_paths(root):
    """Every path make check covers: with Git, tracked files plus untracked files that
    .gitignore does not exclude (so a new page is checked before `git add`); without Git
    (check-staged.py's snapshot, which holds exactly the staged index), every file."""
    if (root / ".git").exists():
        names = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                               cwd=root, check=True, capture_output=True, text=True).stdout.split("\0")
        paths = {root / name for name in names if name}
        return sorted(p for p in paths if p.exists() or p.is_symlink())
    return sorted(p for p in root.rglob("*")
                  if not UNTRACKED_PARTS.intersection(p.relative_to(root).parts)
                  and (p.is_symlink() or not p.is_dir()))


def scanned_files(root):
    """Regular files and symlinks. A symlink is never followed (that could read outside the
    vault); redaction_errors scans its target text instead."""
    return [p for p in listed_paths(root) if p.is_symlink() or p.is_file()]


def redaction_errors(root, deny, deny_source="vault.toml"):
    """Credential-bearing URLs, and [redaction] deny matches in every non-binary file and
    in every listed path name.

    A hit names the path, line and deny pattern number, never the pattern or matched text:
    the deny list says what must stay private. A path that matches is shown with the match
    replaced by `[redaction deny pattern N]`. vault.toml's content is exempt from the deny
    scan only, because it holds the patterns themselves.
    """
    patterns = vaultconf.compile_deny(deny)
    errors = []
    for path in scanned_files(root):
        rel = str(path.relative_to(root))
        name = patternscan.shown(rel, patterns, DENY_LABEL)
        for number in patternscan.path_hits(rel, patterns):
            errors.append(f"{name}: path matches {DENY_LABEL} {number}")
        # A symlink's target is text Git stores and a reader sees, so it is scanned too.
        text = os.readlink(path) if path.is_symlink() else patternscan.decode(path.read_bytes())
        if text is None:
            continue  # binary
        for line, _ in patternscan.line_hits(text, [CREDENTIAL_URL]):
            errors.append(f"{name}:{line}: credential-bearing URL is forbidden")
        if path == root / "vault.toml":
            continue
        for line, number in patternscan.line_hits(text, patterns):
            errors.append(f"{name}:{line}: matches {DENY_LABEL} {number}")
    if any(DENY_LABEL in e for e in errors):
        errors.append(f"Deny patterns are numbered from 1 in {deny_source} [redaction] deny; "
                      "remove the text or, if the pattern is wrong, fix the pattern.")
    return errors


def deny_range(root):
    """Deny hits in every commit of SECRETS_BASE..HEAD: messages, path names, added lines.

    The deny list is the base commit's, so a range cannot empty it to pass; with no base
    (a first push), HEAD's.
    """
    base = vaultconf.checked_base(root, os.environ.get("SECRETS_BASE", ""))
    ref = base or "HEAD"
    shown_ref = base[:12] if base else "HEAD"
    found = subprocess.run(["git", "show", f"{ref}:vault.toml"], cwd=root, capture_output=True)
    if found.returncode:
        found = subprocess.run(["git", "show", "HEAD:vault.toml"], cwd=root, capture_output=True)
        shown_ref = "HEAD"
    if found.returncode:
        raise SystemExit("deny-range: no vault.toml at the base commit or HEAD")
    import tempfile
    with tempfile.TemporaryDirectory(prefix="vault-deny-") as temp:
        (Path(temp) / "vault.toml").write_bytes(found.stdout)
        deny = vaultconf.load_deny(Path(temp) / "vault.toml")
    patterns = vaultconf.compile_deny(deny, f"{shown_ref}:vault.toml")
    errors, count = patternscan.range_hits(root, base, patterns, DENY_LABEL, exempt={"vault.toml"})
    if errors:
        errors.append(f"Deny patterns are numbered from 1 in {shown_ref}:vault.toml [redaction] deny. "
                      "A hit in a commit that is already pushed stays in history even if a later "
                      "commit removes the text; rewrite the branch before it merges.")
        print("\n".join(errors), file=sys.stderr)
        raise SystemExit(1)
    print(f"PASS: {count} commit(s) since {base[:12] if base else 'the root'}: no {DENY_LABEL} "
          f"match in a message, path name or added line ({len(patterns)} pattern(s) from {shown_ref}:vault.toml).")


# Scripts write under these (indexes, the log, rendered skills), and pages here are read as
# vault content; a symlink could point either outside the vault. CLAUDE.md -> AGENTS.md at
# the root is the one sanctioned link.
SYMLINK_FREE = {"wiki", "raw", "skills"}

# Agent harnesses load these files as instructions from any directory they work in. CODEOWNERS
# frees content directories (wiki/, raw/) for ordinary edits, so one nested there would steer
# agents without an owner's review. Allowed only at the root and under skills/ (owner-reviewed).
# Compared case-insensitively: a case-insensitive file system opens AGENTS.md as agents.md.
AGENT_INSTRUCTION_NAMES = {"agents.md", "agents.override.md", "claude.md", "claude.local.md", "gemini.md"}


def misplaced_instructions(parts):
    # .claude/CLAUDE.md is Claude Code's root-level alternative, owned through the root dot-path.
    return (parts[-1].casefold() in AGENT_INSTRUCTION_NAMES and len(parts) > 1
            and parts[0] != "skills" and tuple(p.casefold() for p in parts) != (".claude", "claude.md"))


def validate(root, deny=(), deny_source="vault.toml"):
    errors = []
    if (root / "AGENTS.md").exists():
        claude = root / "CLAUDE.md"
        if not claude.is_symlink() or claude.readlink() != Path("AGENTS.md"):
            errors.append("CLAUDE.md must be a relative symlink to AGENTS.md")
    listed = listed_paths(root)
    directories = {parent for p in listed for parent in p.relative_to(root).parents if parent != Path(".")}
    for rel in sorted(directories):
        if not ignored(rel.parts) and not valid_name(rel, True):
            errors.append(f"{rel}: name must be lowercase kebab-case")
    for path in listed:
        parts = path.relative_to(root).parts
        # Before the ignore skip: an instruction file under __pycache__ or .worktrees still loads.
        if misplaced_instructions(parts):
            errors.append(f"{path.relative_to(root)}: agent harnesses load this file as instructions; "
                          "it is allowed only at the repository root or under skills/")
        if ignored(parts):
            continue
        if not valid_name(path.relative_to(root)):
            errors.append(f"{path.relative_to(root)}: name must be lowercase kebab-case")
        if parts[0] in SYMLINK_FREE and path.is_symlink():
            errors.append(f"{path.relative_to(root)}: symlinks are not allowed under "
                          f"{', '.join(sorted(d + '/' for d in SYMLINK_FREE))}; commit a regular "
                          "file or directory")
    errors.extend(redaction_errors(root, deny, deny_source))
    # The same allowlist engine-update applies before copying, as the CI backstop. Every listed
    # path, ignored ones included: Vale finds a config under .claude/ or .worktrees/ too.
    errors.extend(vaultconf.vale_errors(root, [p.relative_to(root) for p in listed
                                               if p.is_file() or p.is_symlink()]))
    docs = documents(root)
    if not docs:
        return ["No Markdown documents found"], 0
    for path in docs:
        name = str(path.relative_to(root))
        try:
            data, body = parse(path)
            if path.name == "index.md":
                allowed = {"okf_version"} if path.parent == root else set()
                if set(data) - allowed:
                    raise ValueError("index has non-index frontmatter")
                if path.parent == root and data.get("okf_version") != "0.2":
                    raise ValueError("root index must declare okf_version 0.2")
            elif path.name == "log.md":
                if data:
                    raise ValueError("log must not have frontmatter")
            else:
                for key in ("type", "title", "description"):
                    if not isinstance(data.get(key), str) or not data[key].strip():
                        raise ValueError(f"missing/non-string {key}")
                if data.get("status") not in ("draft", "stable", "deprecated"):
                    raise ValueError(f"status must be draft|stable|deprecated, got {data.get('status')!r}")
                if "tags" in data and (not isinstance(data["tags"], list)
                    or any(not isinstance(t, str) for t in data["tags"])):
                    raise ValueError("tags must be a list of strings")
                actors = []
                if "generated" in data:
                    actors.append(data["generated"])
                if "verified" in data:
                    v = data["verified"]
                    actors.extend(v if isinstance(v, list) else [v])
                for actor in actors:
                    if not isinstance(actor, dict) or not re.fullmatch(
                        r"(?:human:[^\s]+|process:[^\s]+|[^\s/]+/[^\s]+)", str(actor.get("by", ""))):
                        by = actor.get("by") if isinstance(actor, dict) else actor
                        raise ValueError(f"invalid generated/verified actor: {by!r}")
                    if "at" in actor:
                        timestamp(actor["at"])
                    elif actor in (data.get("verified") if isinstance(data.get("verified"), list) else [data.get("verified")]):
                        raise ValueError("verification requires a timestamp")
                if "stale_after" in data:
                    timestamp(data["stale_after"])
                if "sources" in data:
                    if not isinstance(data["sources"], list):
                        raise ValueError("sources must be a list")
                    for source in data["sources"]:
                        if not isinstance(source, dict) or not isinstance(source.get("resource"), str):
                            raise ValueError("source requires a resource string")
            # Code examples are not navigational links.
            prose = re.sub(r"```.*?```", "", body, flags=re.S)
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", prose):
                uri = urlsplit(target.strip("<>"))
                if uri.scheme or not uri.path:
                    continue
                rel = unquote(uri.path)
                dest = (root / rel.lstrip("/")) if rel.startswith("/") else path.parent / rel
                dest = dest.resolve()
                if not dest.is_relative_to(root.resolve()):
                    raise ValueError(f"local link escapes bundle: {target}")
                if not dest.exists():
                    raise ValueError(f"broken local link: {target}")
        except (ValueError, TypeError, yaml.YAMLError) as error:
            errors.append(f"{name}: {error}")
    for directory in {p.parent for p in docs}:
        if not (directory / "index.md").is_file():
            errors.append(f"{directory.relative_to(root)}: missing index.md")
    return errors, len(docs)


def self_test():
    import tempfile
    # Built at run time: the scan covers this file too, so the literal must not appear whole.
    global CREDENTIAL_FIXTURE
    CREDENTIAL_FIXTURE = "https://user:" + "example@example.invalid"
    assert all(valid_name(Path(name)) for name in CONVENTIONAL_FILENAMES)
    assert valid_name(Path("nested/AGENTS.md"))
    assert not valid_name(Path("Makefile"), is_directory=True)
    assert not valid_name(Path("Nested/README.md"))
    assert not valid_name(Path("AGENTS.md.md"))
    assert valid_name(Path("skills/x/SKILL.md"))
    assert not valid_name(Path("skills/x/Skill.md"))
    assert not valid_name(Path("wiki/x/SKILL.md"))
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        (root / "index.md").write_text('---\nokf_version: "0.2"\n---\n# Index\n')
        doc = root / "example.md"
        good = '---\ntype: Future Custom Type\ntitle: Example\ndescription: A fixture.\nstatus: draft\nunknown_key: preserved\n---\n# Example\n'
        doc.write_text(good)
        assert not validate(root)[0], "valid unknown type/field rejected"
        doc.write_text(good.replace("type: Future Custom Type", "type: 123"))
        assert validate(root)[0], "non-string type was accepted"
        doc.write_text(good + "[Missing](missing.md)\n")
        assert validate(root)[0], "broken link was accepted"
        doc.write_text(good.replace("status: draft", "status: imagined"))
        assert validate(root)[0], "invalid status was accepted"
        doc.write_text(good)
        doc.write_text(good + CREDENTIAL_FIXTURE + "/path\n")
        assert validate(root)[0], "credential-bearing URL was accepted"
        doc.write_text(good)
        bad_name = root / "Wrong_Name.md"
        bad_name.write_text(good)
        assert validate(root)[0], "bad filename was accepted"
        bad_name.unlink()
        skill = root / "skills" / "x" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("# no frontmatter: code dirs are outside the concept-metadata rule\n")
        assert not validate(root)[0], "skills/ SKILL.md without OKF frontmatter was rejected"
        skill.write_text(CREDENTIAL_FIXTURE + "/path\n")
        assert any("credential-bearing URL" in e for e in validate(root)[0]), \
            "credential-bearing URL under skills/ was accepted"
        skill.unlink()
        # Every non-binary file is scanned, whatever its suffix; binary files are skipped.
        deny = [r"internal\.example\.test"]
        config = root / "settings.toml"
        # Split so this source line itself never matches the pattern it tests.
        config.write_text('host = "db.INTERNAL' + '.example.test"\n')
        found = validate(root, deny)[0]
        assert "settings.toml:1: matches redaction deny pattern 1" in found, "deny match in .toml was accepted"
        assert not any("example" in e for e in found), "a deny refusal printed the pattern or matched text"
        config.write_text(f'url = "{CREDENTIAL_FIXTURE}/"\n')
        assert any("settings.toml:1: credential-bearing URL" in e for e in validate(root)[0]), \
            "credential-bearing URL in .toml was accepted"
        config.write_bytes(b"\0binary db.internal" + b".example.test")
        assert not validate(root, deny)[0], "a binary file was scanned"
        # UTF-16 and UTF-32 text is full of NUL bytes; its byte-order mark marks it as text.
        for codec in ("utf-16", "utf-32"):
            config.write_bytes(('host = "db.internal' + '.example.test"\n').encode(codec))
            assert "settings.toml:1: matches redaction deny pattern 1" in validate(root, deny)[0], \
                f"a deny match in {codec} text was skipped as binary"
        config.unlink()
        # A symlink is not followed, but its target text is scanned.
        pointer = root / "pointer"
        pointer.symlink_to("db.internal" + ".example.test/x")
        assert "pointer:1: matches redaction deny pattern 1" in validate(root, deny)[0], \
            "a deny match in a symlink's target was skipped"
        pointer.unlink()
        # A path name is scanned too, and printed with the match replaced.
        hidden = root / "notes" / ("db-internal." + "example.test-plan") / "a.txt"
        hidden.parent.mkdir(parents=True)
        hidden.write_text("clean\n")
        found = validate(root, [r"internal\.example"])[0]
        assert "notes/db-[redaction deny pattern 1].test-plan/a.txt: path matches redaction deny pattern 1" \
            in found, found
        assert not any("example" in e for e in found), "a path hit printed the matched text"
        hidden.unlink()
        hidden.parent.rmdir()
        hidden.parent.parent.rmdir()
        # Credential URLs in any scheme, not only http(s).
        for scheme in ("ftp", "postgres", "redis+tls"):
            config.write_text(f'url = "{CREDENTIAL_FIXTURE.replace("https", scheme, 1)}/"\n')
            assert any("settings.toml:1: credential-bearing URL" in e for e in validate(root)[0]), \
                f"a {scheme} credential URL was accepted"
        config.unlink()
        (root / "vault.toml").write_text('[redaction]\ndeny = ["internal\\\\.example\\\\.test"]\n')
        assert not validate(root, ["redaction"])[0], "vault.toml was deny-scanned for its own patterns"
        (root / "vault.toml").unlink()
        try:
            vaultconf.compile_deny(["ok", "("])
        except SystemExit as error:
            assert "deny pattern 2 is not a valid regex" in str(error), str(error)
        else:
            raise AssertionError("an invalid deny regex was accepted")
        # A compile error can quote the pattern (a repeated group name); only the number shows.
        try:
            vaultconf.compile_deny(["(?P<" + "falcon>a)(?P<" + "falcon>b)"])
        except SystemExit as error:
            assert "pattern 1" in str(error) and "falcon" not in str(error), str(error)
        else:
            raise AssertionError("a pattern with a repeated group name was accepted")
        (root / "wiki").mkdir()
        (root / "wiki" / "linked.md").symlink_to(doc)
        assert any("wiki/linked.md: symlinks are not allowed" in e for e in validate(root)[0]), \
            "a symlink under wiki/ was accepted"
        (root / "wiki" / "linked.md").unlink()
        (root / "wiki").rmdir()
        stray = root / "wiki-skill" / "SKILL.md"
        stray.parent.mkdir()
        stray.write_text(good)
        assert any("SKILL.md: name must be lowercase" in e for e in validate(root)[0]), \
            "SKILL.md outside skills/ was accepted"
        assert valid_name(Path("apps/tool/skills/x/SKILL.md"))
        # A nested agent instruction file, in any letter case, is refused outside skills/.
        for name in ("raw/notes/CLAUDE.md", "wiki/notes/agents.md", "docs/plans/Gemini.md",
                     "wiki/notes/CLAUDE.local.md", "raw/AGENTS.override.md",
                     ".worktrees/x/Agents.md"):
            nested = root / name
            nested.parent.mkdir(parents=True, exist_ok=True)
            nested.write_text(good)
            assert any(e.startswith(f"{name}: agent harnesses load this file") for e in validate(root)[0]), \
                f"a nested agent instruction file was accepted: {name}"
            nested.unlink()
        allowed = root / "skills" / "x" / "AGENTS.md"
        allowed.write_text("# skill notes\n")
        assert not any("agent harnesses load" in e for e in validate(root)[0]), \
            "an agent instruction file under skills/ was refused"
        allowed.unlink()
        assert not misplaced_instructions((".claude", "CLAUDE.md")), ".claude/CLAUDE.md was refused"
        # One frontmatter parser (vaultconf.split_frontmatter) for every caller: empty,
        # non-mapping and unclosed blocks are refused, not crashed on or read as empty.
        stray.unlink()
        for bad, why in (("---\n---\n# Empty\n", "non-empty mapping"),
                         ("---\n- a list\n---\n# List\n", "non-empty mapping"),
                         ("---\ntitle: x\n# never closed\n", "no closing ---")):
            doc.write_text(bad)
            assert any(f"example.md: frontmatter" in e and why in e for e in validate(root)[0]), \
                f"malformed frontmatter accepted: {bad!r}"
        doc.write_text(good)
        # Vale config: the allowlist engine-update applies before copying holds over the tree too.
        ini, rule = root / ".vale.ini", root / ".vale" / "styles" / "vaultkit" / "filler.yml"
        rule.parent.mkdir(parents=True)
        rule_text = "extends: existence\nmessage: filler\nlevel: warning\ntokens: [basically]\n"
        ini.write_text("StylesPath = .vale/styles\n\n[*.md]\nBasedOnStyles = vaultkit\n")
        rule.write_text(rule_text)
        assert not validate(root)[0], "allowed Vale config was rejected"
        ini.write_text("Packages = Google\nStylesPath = .vale/styles\n")
        assert any(".vale.ini: top-level key packages" in e for e in validate(root)[0]), \
            "a .vale.ini with Packages was accepted"
        ini.write_text("StylesPath = .vale/styles\n")
        rule.write_text("extends: script\nmessage: x\nscript: x\n")
        assert any("extends 'script'" in e for e in validate(root)[0]), "a script rule was accepted"
        rule.write_text(rule_text)
        nested = root / "scripts" / "vale.ini"
        nested.parent.mkdir()
        nested.write_text("StylesPath = /etc\n")
        assert any("only the root .vale.ini" in e for e in validate(root)[0]), \
            "a nested Vale config name was accepted"
        nested.unlink()
        # Under a directory the other checks skip: Vale still finds it there.
        hidden_config = root / ".claude" / "vale.ini"
        hidden_config.parent.mkdir()
        hidden_config.write_text("StylesPath = /etc\n")
        assert any(".claude/vale.ini: Vale reads this name" in e for e in validate(root)[0]), \
            "a Vale config under .claude/ was accepted"
        hidden_config.unlink()
        ini.write_text("StylesPath = .vale/styles\n\n[*.md]\nTokenIgnores = x\n  [formats]\n  md = xml\n")
        assert any("is indented" in e for e in validate(root)[0]), \
            "an indented line that Vale reads as a new section was accepted"
        ini.write_bytes("StylesPath = .vale/styles\n".encode("utf-16"))
        assert any(".vale.ini: not UTF-8 text" in e for e in validate(root)[0]), "non-UTF-8 .vale.ini crashed or passed"
        ini.unlink()
        ini.symlink_to("docs.ini")
        (root / "docs.ini").write_text("Packages = Google\n")
        assert any("a symlink in Vale config" in e for e in validate(root)[0]), "a symlinked .vale.ini was accepted"
        ini.unlink()
        (root / "docs.ini").unlink()
        shouting = rule.with_name("FILLER.YML")
        rule.rename(shouting)
        assert any("only rule files" in e for e in validate(root)[0]), \
            "a rule file Vale would not load under that name was accepted"
        shouting.rename(rule)
    print("Validator controls passed: unknown fields accepted; bad type, link, lifecycle, and filename rejected; "
          "skills/ exempt from metadata but not from name or credential checks; "
          "deny patterns and credential URLs caught in any non-binary file; "
          "Vale config held to its allowlist.")


if __name__ == "__main__":
    if sys.argv[1:] == ["--deny-range"]:
        deny_range(ROOT)
        raise SystemExit(0)
    self_test()
    config = vaultconf.load(ROOT)  # also refuses an invalid vault.toml in this tree
    deny, deny_source = config["deny"], "vault.toml"
    if sys.argv[1:2] == ["--deny-from"] and len(sys.argv) == 3:
        # check-staged.py passes HEAD's vault.toml: a commit cannot empty the deny list it
        # is checked against.
        deny, deny_source = vaultconf.load_deny(sys.argv[2]), "HEAD's vault.toml"
    elif sys.argv[1:]:
        raise SystemExit("usage: check-vault.py [--deny-from <vault.toml>] | --deny-range")
    errors, count = validate(ROOT, deny, deny_source)
    errors.extend(validate_git_paths(ROOT))
    # The unconfigured template has no rendered skills; an instance's skills/ must match a
    # fresh render of templates/, so a hand edit to a skill cannot slip past review.
    if config["template"]:
        print("Template mode: skipping the rendered-skill check (no skills are rendered).")
    elif not config["name"]:
        errors.append(f"vault.toml: name unset; {vaultconf.INIT_HINT}")
    else:
        errors.extend(vaultconf.rendered_skill_errors(ROOT, config))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        raise SystemExit(1)
    print(f"PASS: {count} Markdown paths satisfy the vault profile and local links.")
