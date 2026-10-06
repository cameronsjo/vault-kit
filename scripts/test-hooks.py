#!/usr/bin/env python3
"""Exercise actual commits with opposing staged and unstaged document states.

The fixture repo is built entirely inside a temp dir: the engine files are copied from this
checkout and every vault page is synthesized here, so the test never reads real vault content.
"""
import vaultconf  # noqa: F401  (toolchain preflight: Python and PyYAML, before anything else)
import os
from pathlib import Path
import platform
import random
import re
import shutil
import subprocess
import sys
import tempfile

# The machine's own git config (templates, merge settings, hooks) must not change the result.
ISOLATED = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
# CI sets PYTHON=python3 for its own make calls; the fixtures' make must pick its interpreter
# itself, so the .venv cases below test the Makefile's choice.
ISOLATED.pop("PYTHON", None)

ROOT = Path(__file__).resolve().parent.parent

# Every refusal the suite must see. Each is recorded when a case asserts it; the run fails
# if any is missing, so deleting a case (or a check that produced it) cannot pass silently.
EXPECTED = {
    "status must be draft|stable|deprecated, got 'invalid-fixture'",
    "Existing raw captures are immutable",
    "wiki/log.md is append-only",
    "require an appended wiki/log.md entry",
    "keeps that branch's log whole",
    "The staged log differs at line",
    "outside refs/remotes/origin/",
    "has no refs/remotes/origin/gone",
    "Nothing written",
    "symbolic link",
    "Resolve and `git add` these files first, then run this again: ",
    "after the merged log",
    "has changes that are not staged",
    "preserve the previous bytes",
    "the ordinary rule applies because the merged-in commit",
    "Nothing written: the log at the merged-in commit",
    "is not an earlier state of the log",
    "is not on refs/remotes/origin/main",
    "Nothing to resolve: this branch already contains",
    "the merge has more than one other parent",
    "refusing to merge unrelated histories",
    "Nothing written: `git merge-tree --write-tree` failed",
    "not full commit ids",
    "is not a commit Git can read",
    "Cannot read '",
    "more than one other parent",
    "No hook was installed or changed",
    "Re-anchored",
    "WARNING: global core.hooksPath is",
    "Chaining: global core.hooksPath is",
    "Passing through",
    "Removed the pass-through",
    "Not chaining: global core.hooksPath is",
    "this vault's own hook directory",
    "the chained pre-commit hook",
    "Active hooks path:",
    "the repository-local core.hooksPath is",
    "Unset the repository-local core.hooksPath",
    ".venv must not be tracked",
    "No index was written",
}
# Refusals that only the pinned gitleaks produces; reported as SKIP when it cannot be run.
GITLEAKS_EXPECTED = {"leaks found"}
EXPECTED |= GITLEAKS_EXPECTED | {
    "matches redaction deny pattern 2",
    "deny pattern 1 is not a valid regex",
    "checksum mismatch for cached",
    "checksum mismatch for downloaded",
    "The secret scan fails closed",
    "full lowercase commit id",
    "is not a commit in this repository",
    "not the pinned",
    "notes/scratch.txt: an added line matches redaction deny pattern 1",
    "notes/wide.txt: a line of its UTF-16 text matches redaction deny pattern 1",
    "path notes/[redaction deny pattern 1]-x/b.txt matches redaction deny pattern 1",
    "message matches redaction deny pattern 1",
    "path matches redaction deny pattern 1",
}
SEEN = set()
CASES = []
SKIPPED = []


def skip(name, why):
    SKIPPED.append(name)
    print(f"SKIP: {name} ({why})")


def fake_aws_key():
    """An AWS-access-key-shaped value built at run time, so no key-shaped literal sits in
    the repo for a scanner to flag. Seeded: the same synthetic value every run."""
    rng = random.Random(20260101)
    return "AK" + "IA" + "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567") for _ in range(16))


# The secret-scan cases need the pinned gitleaks. Resolve it once through the wrapper (the
# same verified copy make check uses). If that fails, offline say, the fixture runs against a
# stub that finds nothing, and every case that needs gitleaks prints SKIP instead of passing.
_resolved = subprocess.run(["python3", str(ROOT / "scripts/gitleaks"), "--vault-resolve"],
                           capture_output=True, text=True)
GITLEAKS = _resolved.stdout.strip() if _resolved.returncode == 0 else None
_stub_dir = tempfile.TemporaryDirectory(prefix="vault-gitleaks-stub-")
if not GITLEAKS and os.environ.get("VAULT_KIT_REQUIRE_GITLEAKS") == "1":
    # CI sets this: there a missing gitleaks is a broken setup, not a reason to skip.
    sys.exit("FAIL: pinned gitleaks unavailable and VAULT_KIT_REQUIRE_GITLEAKS=1:\n"
             + _resolved.stderr.strip())
if not GITLEAKS:
    print("SKIP: pinned gitleaks unavailable; secret-scan cases will be skipped:\n"
          + _resolved.stderr.strip())
    stub = Path(_stub_dir.name) / "gitleaks"
    stub.write_text("#!/bin/sh\nexit 0\n")
    stub.chmod(0o755)
    ISOLATED["GITLEAKS_ALLOW_UNPINNED"] = "1"  # the stub reports no version
ISOLATED["GITLEAKS_BIN"] = GITLEAKS or str(Path(_stub_dir.name) / "gitleaks")


def case_passed(name, *messages):
    SEEN.update(messages)
    CASES.append(name)
    print(f"ok: {name}")


def run(args, cwd, check=True, env=None):
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, env={**ISOLATED, **(env or {})})
    if check and result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result


def page_text(title, description, body):
    return (f"---\ntype: Fixture\ntitle: {title}\ndescription: {description}\nstatus: draft\n---\n"
            f"# {title}\n\nSynthetic fixture page.\n\n## Details\n\n{body}\n")


def build_fixture(root):
    """Copy only the engine, then synthesize a minimal valid vault around it."""
    for name in (ROOT / "engine.manifest").read_text().split():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    # Instance-owned, like vault.toml (engine-update must not revert an instance's allowlist),
    # so it is not in engine.manifest; the Makefile's secret scan needs it.
    shutil.copy2(ROOT / ".gitleaks.toml", root / ".gitleaks.toml")
    (root / "vault.toml").write_text(
        'template = false\nname = "fixture-vault"\ntitle = "Fixture Vault"\n'
        'scope = "hook test fixtures"\nroot_env = ""\n\n[redaction]\ndeny = []\n')
    (root / "README.md").write_text(page_text("Fixture Vault", "A synthetic vault for hook tests.", "Not a real vault."))
    (root / "AGENTS.md").write_text(page_text("Fixture agents", "Synthetic agent instructions.", "Synthetic instructions."))
    (root / "CLAUDE.md").symlink_to("AGENTS.md")
    (root / "wiki").mkdir()
    (root / "wiki/log.md").write_text(
        "# Log\n\n## [2026-01-01] maintenance | Seed fixture vault\n\nTest actor created the fixture.\n")
    (root / "wiki/capabilities").mkdir()
    for name in ("alpha", "beta", "gamma"):
        (root / f"wiki/capabilities/{name}.md").write_text(
            page_text(f"Fixture {name}", f"Synthetic capability {name}.", f"Capability {name} does nothing real."))
    capture = root / "raw/2026-01-01-fixture-capture/manifest.json"
    capture.parent.mkdir(parents=True)
    capture.write_text('{"captured_by": "fixture/capture-1"}\n')
    run(["python3", "scripts/init-vault", "--render-skills"], root)  # make check compares skills/ to a render
    run(["python3", "scripts/index-vault.py"], root)  # indexes must be fresh before the first commit


with tempfile.TemporaryDirectory(prefix="vault-hook-test-") as temp:
    root = Path(temp)
    build_fixture(root)
    run(["git", "init", "-q"], root)
    for key, value in (("user.name", "Vault hook fixture"), ("user.email", "fixture@example.invalid"),
                       ("commit.gpgsign", "false"), ("core.hooksPath", str(root / ".git/hooks"))):
        run(["git", "config", "--local", key, value], root)
    run(["python3", "scripts/install-hooks"], root)
    run(["git", "add", "--all"], root)
    run(["git", "commit", "-qm", "valid fixture"], root)
    case_passed("valid fixture commits through the installed hooks")
    initial = run(["git", "rev-parse", "HEAD"], root).stdout
    readme = root / "README.md"
    good = readme.read_text()
    bad = good.replace("status: draft", "status: invalid-fixture")
    assert bad != good, "fixture did not corrupt the lifecycle field"
    readme.write_text(bad)
    run(["git", "add", "README.md"], root)
    readme.write_text(good)
    rejected = run(["git", "commit", "-qm", "must reject invalid staged content"], root, check=False)
    assert rejected.returncode != 0 and "status must be draft|stable|deprecated, got 'invalid-fixture'" in rejected.stderr + rejected.stdout
    case_passed("refused: invalid staged lifecycle field", "status must be draft|stable|deprecated, got 'invalid-fixture'")
    assert run(["git", "rev-parse", "HEAD"], root).stdout == initial
    assert readme.read_text() == good, "hook changed the working tree"
    readme.write_text(good + "\nStaged fixture change.\n")
    run(["git", "add", "README.md"], root)
    readme.write_text(bad)
    run(["git", "commit", "-qm", "accept valid staged content despite unstaged errors"], root)
    assert readme.read_text() == bad, "hook overwrote unstaged work"
    assert "invalid-fixture" not in run(["git", "show", "HEAD:README.md"], root).stdout
    case_passed("staged content accepted; unstaged edits survive")

    log = root / "wiki/log.md"
    old_log = log.read_text()
    entry = "\n## [2026-09-07] lint | Hook fixture\n\nTest actor checked the proposed change.\n"

    def reject(message, case="history violation"):
        before = run(["git", "rev-parse", "HEAD"], root).stdout
        result = run(["git", "commit", "-qm", "must reject history violation"], root, check=False)
        printed = result.stdout + result.stderr
        assert result.returncode and message in printed, (
            f"{case}: expected a refusal containing {message!r}; commit rc={result.returncode}; hook printed:\n{printed}")
        assert run(["git", "rev-parse", "HEAD"], root).stdout == before
        case_passed(f"refused: {case}", message)
        return printed

    def parents():
        return len(run(["git", "rev-list", "--parents", "-n1", "HEAD"], root).stdout.split()) - 1

    # Redaction floor. The deny list and gitleaks both read the staged snapshot, so each
    # refusal below comes from staged content with a clean (unstaged) working copy.
    vault_toml = root / "vault.toml"
    clean_toml = vault_toml.read_text()
    vault_toml.write_text(clean_toml.replace(
        "deny = []", r"deny = ['\bcorp-only\b', 'internal\.example\.test']"))
    run(["git", "add", "vault.toml"], root)
    run(["git", "commit", "-qm", "configure a deny list"], root)
    case_passed("a deny list commits; vault.toml is exempt from its own patterns")
    settings = root / "config/fixture.toml"
    settings.parent.mkdir()
    # Split so this source line, which the fixture copies and scans, never matches the pattern.
    settings.write_text('[database]\nhost = "db.Internal' + '.Example.Test"\n')
    run(["git", "add", "config/fixture.toml"], root)
    settings.write_text('[database]\nhost = "db.example.invalid"\n')
    said = reject("config/fixture.toml:2: matches redaction deny pattern 2", "a denylisted host in a staged .toml")
    assert "matches redaction deny pattern 2" in said
    assert "internal" not in said.lower() and "example.test" not in said.lower(), \
        f"a deny refusal printed the pattern or the matched text:\n{said}"
    run(["git", "rm", "-q", "--cached", "--force", "config/fixture.toml"], root)
    vault_toml.write_text(clean_toml.replace("deny = []", "deny = ['(']"))
    run(["git", "add", "vault.toml"], root)
    reject("deny pattern 1 is not a valid regex", "an invalid deny regex in vault.toml")
    run(["git", "restore", "--source=HEAD", "--staged", "--worktree", "vault.toml"], root)
    # A commit cannot empty the deny list it is checked against: the hook uses HEAD's.
    vault_toml.write_text(clean_toml)
    settings.write_text('[database]\nhost = "db.Internal' + '.Example.Test"\n')
    run(["git", "add", "vault.toml", "config/fixture.toml"], root)
    said = reject("config/fixture.toml:2: matches redaction deny pattern 2", "deny list emptied in the same commit as a hit")
    assert "HEAD's vault.toml" in said, said
    run(["git", "restore", "--source=HEAD", "--staged", "--worktree", "vault.toml"], root)
    run(["git", "rm", "-q", "--cached", "--force", "config/fixture.toml"], root)
    settings.write_text('[database]\nhost = "db.example.invalid"\n')
    # Built at run time so this file, which the fixture copies and scans, never matches.
    codename = "corp" + "-only"
    # make check reads untracked files too, so a new page is caught before `git add`.
    draft = root / "wiki/capabilities/draft-page.md"
    draft.write_text(page_text("Draft", "An untracked page.", f"Mentions the {codename} roadmap."))
    checked = run(["make", "--no-print-directory", "check"], root, check=False)
    printed = checked.stdout + checked.stderr
    assert checked.returncode and "wiki/capabilities/draft-page.md:13: matches redaction deny pattern 1" in printed, printed
    assert codename not in printed, f"make check printed the matched text:\n{printed}"
    case_passed("refused: make check on an untracked page with a deny match", "matches redaction deny pattern 1")
    draft.unlink()
    # A path name is scanned too, and printed with the match replaced.
    named = root / f"notes/{codename}-plan/a.txt"
    named.parent.mkdir(parents=True)
    named.write_text("clean\n")
    run(["git", "add", str(named.relative_to(root))], root)
    said = reject("notes/[redaction deny pattern 1]-plan/a.txt: path matches redaction deny pattern 1",
                  "a deny match in a staged path name")
    assert codename not in said, f"a path refusal printed the matched text:\n{said}"
    run(["git", "rm", "-q", "--cached", "--force", str(named.relative_to(root))], root)
    shutil.rmtree(root / "notes")
    # CI's deny-range reads every commit in the range with the base's deny list: a message, a
    # path name, and a line a later commit removed, all made with --no-verify, all caught.
    range_base = run(["git", "rev-parse", "HEAD"], root).stdout.strip()
    run(["git", "checkout", "-q", "-b", "deny-range-fixture"], root)
    # A committed `* -diff` would turn every patch into "Binary files differ"; the range scan
    # reads patches with --text, so the removed line below is still found.
    (root / ".gitattributes").write_text("* -diff\n")
    run(["git", "add", ".gitattributes"], root)
    run(["git", "commit", "-q", "--no-verify", "-m", "mark everything binary for diff"], root)
    scratch = root / "notes/scratch.txt"
    scratch.parent.mkdir(parents=True)
    scratch.write_text(f"the {codename} roadmap\n")
    run(["git", "add", "notes/scratch.txt"], root)
    run(["git", "commit", "-q", "--no-verify", "-m", "add a note"], root)
    run(["git", "rm", "-q", "notes/scratch.txt"], root)
    run(["git", "commit", "-q", "--no-verify", "-m", "remove the note"], root)
    # UTF-16 text: each patch line holds a NUL between its ASCII characters, so the range
    # scan decodes the added file whole. Added, then removed.
    (root / "notes").mkdir(exist_ok=True)
    (root / "notes/wide.txt").write_bytes(f"first line\nthe {codename} roadmap\n".encode("utf-16"))
    run(["git", "add", "notes/wide.txt"], root)
    run(["git", "commit", "-q", "--no-verify", "-m", "add a wide note"], root)
    run(["git", "rm", "-q", "notes/wide.txt"], root)
    run(["git", "commit", "-q", "--no-verify", "-m", "remove the wide note"], root)
    (root / f"notes/{codename}-x").mkdir(parents=True)
    (root / f"notes/{codename}-x/b.txt").write_text("clean\n")
    run(["git", "add", "notes"], root)
    run(["git", "commit", "-q", "--no-verify", "-m", "add a clean file under a named directory"], root)
    run(["git", "rm", "-q", "-r", "notes"], root)
    run(["git", "commit", "-q", "--no-verify", "-m", f"drop the {codename} notes"], root)
    vault_toml.write_text(clean_toml)
    run(["git", "add", "vault.toml"], root)
    run(["git", "commit", "-q", "--no-verify", "-m", "empty the deny list"], root)
    assert run(["git", "grep", "-qiw", codename, "HEAD"], root, check=False).returncode == 1 and \
        codename not in run(["git", "ls-tree", "-r", "--name-only", "HEAD"], root).stdout, \
        "the final tree should be clean, so only the range scan can see these hits"
    ranged = run(["make", "--no-print-directory", "deny-range"], root, check=False, env={"SECRETS_BASE": range_base})
    printed = ranged.stdout + ranged.stderr
    for message in ("notes/scratch.txt: an added line matches redaction deny pattern 1",
                    "notes/wide.txt: a line of its UTF-16 text matches redaction deny pattern 1",
                    "path notes/[redaction deny pattern 1]-x/b.txt matches redaction deny pattern 1",
                    "message matches redaction deny pattern 1"):
        assert message in printed, f"deny-range missed {message!r}:\n{printed}"
        case_passed(f"refused: deny-range finds {message.split(':')[-1].strip()}", message)
    assert ranged.returncode and codename not in printed, f"deny-range printed the matched text:\n{printed}"
    clean_range = run(["make", "--no-print-directory", "deny-range"], root, check=False,
                      env={"SECRETS_BASE": run(["git", "rev-parse", "HEAD"], root).stdout.strip()})
    assert clean_range.returncode == 0, clean_range.stdout + clean_range.stderr
    run(["git", "checkout", "-q", "-"], root)
    run(["git", "branch", "-q", "-D", "deny-range-fixture"], root)

    tool = root / "tools/fixture-tool.py"
    tool.parent.mkdir()
    clean_tool = 'import os\n\nREGION = "example-region-1"\n'
    if GITLEAKS:
        key = fake_aws_key()
        tool.write_text(f'ACCESS_KEY_ID = "{key}"\n')
        run(["git", "add", "tools/fixture-tool.py"], root)
        tool.write_text(clean_tool)
        said = reject("leaks found", "a fake AWS key in a staged .py, caught by gitleaks")
        assert key not in said, "gitleaks printed the key unredacted"
        tool.write_text(f'ACCESS_KEY_ID = "{key}"  # gitleaks:allow\n')
        run(["git", "add", "tools/fixture-tool.py"], root)
        tool.write_text(clean_tool)
        reject("leaks found", "an inline gitleaks:allow comment does not exempt a key")
        staged = run(["make", "--no-print-directory", "secrets", "SECRETS_MODE=staged"], root, check=False)
        printed = staged.stdout + staged.stderr
        assert staged.returncode and "leaks found" in printed and key not in printed, printed
        case_passed("refused: make secrets SECRETS_MODE=staged on the same staged key", "leaks found")
        # The commit under scan cannot supply its own suppressions: .gitleaksignore and
        # .gitleaks.toml come from HEAD, so these two take effect only from the next commit.
        ignore, config = root / ".gitleaksignore", root / ".gitleaks.toml"
        dir_fingerprint = "tools/fixture-tool.py:aws-access-token:1\n"
        tool.write_text(f'ACCESS_KEY_ID = "{key}"\n')
        ignore.write_text(dir_fingerprint)
        run(["git", "add", "tools/fixture-tool.py", ".gitleaksignore"], root)
        reject("leaks found", "a staged .gitleaksignore naming the staged key's fingerprint")
        run(["git", "rm", "-q", "--cached", "--force", ".gitleaksignore"], root)
        ignore.unlink()
        clean_config = config.read_text()
        config.write_text(clean_config + "\n[[allowlists]]\ndescription = \"fixture\"\npaths = ['^tools/']\n")
        run(["git", "add", ".gitleaks.toml"], root)
        reject("leaks found", "a staged .gitleaks.toml allowlisting the key's path")
        run(["git", "restore", "--source=HEAD", "--staged", "--worktree", ".gitleaks.toml"], root)
        run(["git", "rm", "-q", "--cached", "--force", "tools/fixture-tool.py"], root)
        # Positive control, on a side branch: once HEAD carries the ignore entry, the same key
        # commits, so the refusals above came from where the policy is read, not a typo.
        trunk_tip = run(["git", "rev-parse", "HEAD"], root).stdout.strip()
        run(["git", "checkout", "-q", "-b", "policy-fixture"], root)
        tool.write_text(clean_tool)
        ignore.write_text(dir_fingerprint)
        run(["git", "add", ".gitleaksignore", "tools/fixture-tool.py"], root)
        run(["git", "commit", "-qm", "ignore one fixture finding"], root)
        tool.write_text(f'ACCESS_KEY_ID = "{key}"\n')
        run(["git", "add", "tools/fixture-tool.py"], root)
        run(["git", "commit", "-qm", "a finding HEAD's .gitleaksignore covers"], root)
        case_passed("a .gitleaksignore committed in HEAD covers the next commit")
        # CI range mode reads the policy from SECRETS_BASE: an ignore entry added inside the
        # range, naming that range's own commit, does not silence it.
        key_commit = run(["git", "rev-parse", "HEAD"], root).stdout.strip()
        ignore.write_text(dir_fingerprint + f"{key_commit}:tools/fixture-tool.py:aws-access-token:1\n")
        run(["git", "add", ".gitleaksignore"], root)
        run(["git", "commit", "-q", "--no-verify", "-m", "ignore the committed finding"], root)
        ranged = run([sys.executable, "scripts/scan-secrets.py", "range"], root, check=False,
                     env={"SECRETS_BASE": trunk_tip})
        printed = ranged.stdout + ranged.stderr
        assert ranged.returncode == 1 and "leaks found" in printed and key not in printed, printed
        case_passed("refused: range scan ignores a .gitleaksignore added inside the range", "leaks found")
        run(["git", "checkout", "-q", "-"], root)
        run(["git", "branch", "-q", "-D", "policy-fixture"], root)
        ignore.unlink(missing_ok=True)
        # A key only a merge commit adds (its own resolution), removed by the next commit, is
        # still found: the range scan reads merges against each parent (-m). On side branches,
        # so the trunk's history stays linear for the cases below.
        home_branch = run(["git", "branch", "--show-current"], root).stdout.strip()
        evil_base = run(["git", "rev-parse", "HEAD"], root).stdout.strip()
        for branch, name in (("evil-side", "side"), ("evil-main", "main")):
            run(["git", "checkout", "-q", "-b", branch, evil_base], root)
            (root / f"{name}.txt").write_text(f"{name}\n")
            run(["git", "add", f"{name}.txt"], root)
            run(["git", "commit", "-q", "--no-verify", "-m", f"{name} change"], root)
        run(["git", "merge", "-q", "--no-ff", "--no-commit", "evil-side"], root)
        (root / "evil.py").write_text(f'ACCESS_KEY_ID = "{key}"\n')
        run(["git", "add", "evil.py"], root)
        run(["git", "commit", "-q", "--no-verify", "-m", "merge evil-side"], root)
        run(["git", "rm", "-q", "evil.py"], root)
        run(["git", "commit", "-q", "--no-verify", "-m", "drop the merge's file"], root)
        ranged = run([sys.executable, "scripts/scan-secrets.py", "range"], root, check=False,
                     env={"SECRETS_BASE": evil_base})
        printed = ranged.stdout + ranged.stderr
        assert ranged.returncode == 1 and "leaks found" in printed and key not in printed, printed
        case_passed("refused: range scan finds a key only a merge commit added", "leaks found")
        run(["git", "checkout", "-q", home_branch], root)
        run(["git", "branch", "-q", "-D", "evil-side", "evil-main"], root)
        tool.parent.mkdir(exist_ok=True)  # the branch switch removed the directory it tracked
        # make secrets (and make check) default to the working tree: an untracked file is read.
        loose = root / "tools/untracked-key.py"
        loose.write_text(f'ACCESS_KEY_ID = "{key}"\n')
        worktree = run(["make", "--no-print-directory", "secrets"], root, check=False)
        printed = worktree.stdout + worktree.stderr
        assert worktree.returncode and "leaks found" in printed and key not in printed, printed
        case_passed("refused: make secrets (worktree mode) on an untracked file", "leaks found")
        loose.unlink()
    else:
        for name in ("a fake AWS key in a staged .py, caught by gitleaks",
                     "an inline gitleaks:allow comment does not exempt a key",
                     "make secrets (git --staged) on the same staged key"):
            skip(name, "pinned gitleaks unavailable")
    # A range base that is not a full commit id Git can read fails closed (exit 2).
    for base, message in (("abc", "full lowercase commit id"), ("1" * 40, "is not a commit in this repository")):
        bad = run([sys.executable, "scripts/scan-secrets.py", "range"], root, check=False, env={"SECRETS_BASE": base})
        assert bad.returncode == 2 and message in bad.stderr and "nothing was scanned" in bad.stderr, bad.stderr
        case_passed(f"refused: SECRETS_BASE={base[:8]}...", message)
    # GITLEAKS_BIN must report the pinned version unless the operator opts out loudly.
    true_bin = shutil.which("true")
    env = {"GITLEAKS_BIN": true_bin, "GITLEAKS_ALLOW_UNPINNED": ""}
    pinned = run([sys.executable, "scripts/gitleaks", "version"], root, check=False, env=env)
    assert pinned.returncode == 2 and "not the pinned" in pinned.stderr, pinned.stderr
    case_passed("refused: GITLEAKS_BIN that does not report the pinned version", "not the pinned")
    allowed = run([sys.executable, "scripts/gitleaks", "version"], root, check=False,
                  env={**env, "GITLEAKS_ALLOW_UNPINNED": "1"})
    assert allowed.returncode == 0 and "WARNING: GITLEAKS_ALLOW_UNPINNED=1" in allowed.stderr, allowed.stderr
    case_passed("GITLEAKS_ALLOW_UNPINNED=1 runs another binary with a warning")
    settings.write_text('[database]\nhost = "db.example.invalid"\n')
    tool.write_text(clean_tool)
    run(["git", "add", "config/fixture.toml", "tools/fixture-tool.py"], root)
    run(["git", "commit", "-qm", "clean config and code pass the redaction floor"], root)
    case_passed("clean .toml and .py commit through the deny scan and gitleaks")

    # The wrapper refuses any gitleaks it cannot verify, and fails closed without one.
    wrapper_version = re.search(r'^VERSION = "([^"]+)"', (root / "scripts/gitleaks").read_text(), re.M).group(1)
    pinned_targets = ("darwin_arm64", "darwin_x64", "linux_x64")
    machine = {"aarch64": "arm64", "x86_64": "x64", "amd64": "x64"}.get(platform.machine().lower(),
                                                                        platform.machine().lower())
    if f"{platform.system().lower()}_{machine}" not in pinned_targets:
        for name in ("cached gitleaks with the wrong checksum", "downloaded archive with the wrong checksum",
                     "no download possible"):
            skip(name, f"no pinned gitleaks build for {platform.system()} {platform.machine()}")
    else:
        with tempfile.TemporaryDirectory(prefix="vault-gitleaks-cache-") as cache_dir:
            env = {k: v for k, v in ISOLATED.items() if k != "GITLEAKS_BIN"}
            env["XDG_CACHE_HOME"] = cache_dir
            cached = Path(cache_dir) / "vault-kit" / f"gitleaks-{wrapper_version}" / "gitleaks"

            def wrapper(case, message, **extra):
                result = subprocess.run(["python3", "scripts/gitleaks", "version"], cwd=root, text=True,
                                        capture_output=True, env={**env, **extra})
                printed = result.stdout + result.stderr
                assert result.returncode == 2 and message in printed, f"{case}: rc={result.returncode}:\n{printed}"
                case_passed(f"refused: {case}", message)
                return printed

            cached.parent.mkdir(parents=True)
            cached.write_text("#!/bin/sh\necho planted\n")
            cached.chmod(0o755)
            assert "planted" not in wrapper("cached gitleaks with the wrong checksum", "checksum mismatch for cached")
            cached.unlink()
            mirror = Path(cache_dir) / "mirror"
            mirror.mkdir()
            for name in pinned_targets:
                (mirror / f"gitleaks_{wrapper_version}_{name}.tar.gz").write_bytes(b"not the pinned archive")
            wrapper("downloaded archive with the wrong checksum", "checksum mismatch for downloaded",
                    GITLEAKS_DOWNLOAD_BASE=mirror.as_uri())
            assert not cached.exists(), "a download that failed verification was cached"
            said = wrapper("no download possible", "The secret scan fails closed",
                           GITLEAKS_DOWNLOAD_BASE="http://127.0.0.1:9")
            assert "GITLEAKS_BIN" in said, f"the offline refusal does not say how to install:\n{said}"
            assert not cached.exists(), "a failed download left a cached binary"

    capture = "raw/2026-01-01-fixture-capture/manifest.json"
    source = root / capture
    source.write_text(source.read_text().replace("fixture/capture-1", "codex/modified-fixture"))
    log.write_text(old_log + entry)
    run(["git", "add", capture, "wiki/log.md"], root)
    reject("Existing raw captures are immutable")
    run(["git", "restore", "--source=HEAD", "--staged", "--worktree", capture], root)
    source.unlink()
    run(["git", "add", capture], root)
    reject("Existing raw captures are immutable")
    run(["git", "restore", "--source=HEAD", "--staged", "--worktree", capture], root)
    log.write_text("# Rewritten history\n" + entry)
    run(["git", "add", "wiki/log.md"], root)
    reject("wiki/log.md is append-only")
    run(["git", "restore", "--source=HEAD", "--staged", "--worktree", "wiki/log.md"], root)
    page = root / "wiki/capabilities/alpha.md"
    page.write_text(page.read_text() + "\nFixture refinement.\n")
    run(["git", "add", "wiki/capabilities/alpha.md"], root)
    reject("require an appended wiki/log.md entry")
    log.write_text(old_log + entry)
    run(["git", "add", "wiki/log.md"], root)
    run(["git", "commit", "-qm", "accept wiki change with appended operation"], root)

    # Merging the default branch into a branch, when each appended an entry and added a page.
    trunk = run(["git", "branch", "--show-current"], root).stdout.strip()
    shared_log = log.read_text()
    theirs = "\n## [2026-09-08] ingest | Default branch fixture\n\nTest actor imported a source.\n"
    ours = "\n## [2026-09-08] lint | This branch fixture\n\nTest actor checked the proposed change.\n"
    owes = "require an appended wiki/log.md entry"
    owes_own = "after the merged log"
    resolve = ["python3", "scripts/check-history.py", "--resolve-merge"]
    index = ["python3", "scripts/index-vault.py"]
    other_page = root / "wiki/capabilities/beta.md"
    third_page = root / "wiki/capabilities/gamma.md"
    new_capture = "raw/2026-09-08-hook-fixture/note.json"

    def new_page(name, like=None):
        body = re.sub(r"(?m)^title: .*$", f"title: Fixture page {name}", (like or other_page).read_text(), count=1)
        (root / f"wiki/capabilities/fixture-{name}.md").write_text(re.sub(r"(?m)^# .*$", f"# Fixture page {name}", body, count=1))

    def refuses(command, message, case):
        result = run(command, root, check=False)
        assert result.returncode and message in result.stderr, f"{case}: expected {message!r}; got:\n{result.stdout}{result.stderr}"
        case_passed(f"refused: {case}", message)

    new_page("shared", like=page)  # unlike the other fixture pages, so Git sees no rename
    shared_page = "wiki/capabilities/fixture-shared.md"
    log.write_text(shared_log + "\n## [2026-09-08] ingest | Shared page fixture\n\nTest actor imported a source.\n")
    run(index, root)
    run(["git", "add", "wiki"], root)
    run(["git", "commit", "-qm", "a page both branches start from"], root)
    shared_log = log.read_text()
    run(["git", "checkout", "-qb", "other"], root)
    other_page.write_text(other_page.read_text() + "\nDefault-branch refinement.\n")
    (root / shared_page).write_text((root / shared_page).read_text() + "\nDefault-branch refinement.\n")
    new_page("default")
    (root / new_capture).parent.mkdir()
    (root / new_capture).write_text('{"captured_by": "fixture"}\n')
    log.write_text(shared_log + theirs)
    run(index, root)
    run(["git", "add", "wiki", new_capture], root)
    run(["git", "commit", "-qm", "default branch appends an entry and adds a page"], root)
    # The fixture has no remote. This ref marks "other" as the published default branch;
    # origin/HEAD stays unset for now, so the origin/main fallback is what applies the rule.
    run(["git", "update-ref", "refs/remotes/origin/main", "other"], root)
    run(["git", "checkout", "-q", trunk], root)
    page.write_text(page.read_text() + "\nSecond fixture refinement.\n")
    before_edit = other_page.read_text()
    other_page.write_text(before_edit.replace("\n## ", "\nThis-branch refinement.\n\n## ", 1))
    assert other_page.read_text() != before_edit, "fixture page has no second-level heading to edit above"
    new_page("branch")
    (root / shared_page).unlink()
    log.write_text(shared_log + ours)
    run(index, root)
    run(["git", "add", "wiki"], root)
    run(["git", "commit", "-qm", "this branch appends an entry and adds a page"], root)
    own_tip = run(["git", "rev-parse", "HEAD"], root).stdout
    assert run(["git", "merge", "other"], root, check=False).returncode, "fixture merge did not conflict on the log"
    refuses(resolve, "Resolve and `git add` these files first, then run this again: " + repr(shared_page),
            "the resolver while a page is still in conflict")
    run(["git", "add", shared_page], root)
    run(resolve, root)
    assert log.read_text() == shared_log + theirs + ours, "the resolver wrote the wrong log while the log and an index were unmerged"
    # Both branches added a page to one directory, so its index is regenerated in the merge.
    log.write_text(shared_log + ours)
    run(index, root)
    run(["git", "add", "wiki/index.md", "wiki/capabilities/index.md"], root)
    for case, wrong in (("this branch's entry first, the order CI refuses", shared_log + ours + theirs),
                        ("the default branch's entry dropped", shared_log + ours),
                        ("this branch's entry dropped", shared_log + theirs),
                        ("a rewritten log", "# Rewritten history\n" + theirs + ours),
                        ("markers deleted by hand, losing the blank line", shared_log + theirs + ours.lstrip("\n"))):
        log.write_text(wrong)
        run(["git", "add", "wiki/log.md"], root)
        reject("keeps that branch's log whole", case)
    reject("The staged log differs at line", "a refusal that names where the log differs")
    # The default branch is read from origin/HEAD only when it points inside refs/remotes/origin/.
    log.write_text(shared_log + theirs + ours)
    run(["git", "add", "wiki/log.md"], root)
    for target, why in (("refs/heads/other", "outside refs/remotes/origin/"),
                        ("refs/remotes/origin/gone", "has no refs/remotes/origin/gone")):
        run(["git", "symbolic-ref", "refs/remotes/origin/HEAD", target], root)
        reject(why, f"the default branch's log first while origin/HEAD points at {target}")
        refuses(resolve, "Nothing written", f"the resolver while origin/HEAD points at {target}")
    run(["git", "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main"], root)
    log.unlink()
    log.symlink_to(root / "README.md")
    refuses(resolve, "symbolic link", "the log replaced by a symbolic link")
    log.unlink()
    run(resolve, root)
    assert log.read_text() == shared_log + theirs + ours, "the resolver wrote something other than the expected log"
    # Running the resolver again leaves an entry appended after the merged log alone.
    extra = "\n## [2026-09-08] maintenance | Merge fixture\n\nTest actor resolved a page by hand.\n"
    log.write_text(shared_log + theirs + ours + extra)
    assert "nothing written" in run(resolve, root).stdout, "the resolver did not report a no-op"
    case_passed("resolver is a no-op on an already merged log")
    assert log.read_text() == shared_log + theirs + ours + extra, "the resolver discarded an appended entry"
    log.write_text(shared_log + theirs + ours)
    run(["git", "add", "wiki/log.md"], root)
    # The page Git could not merge owes an entry even staged as one branch's version whole.
    # The page it merged unaided and the regenerated index do not.
    merged_page = other_page.read_text()
    assert "This-branch refinement." in merged_page and "Default-branch refinement." in merged_page
    named = reject(owes_own, "a page Git could not merge, kept as the default branch's version")
    assert repr(shared_page) in named, f"the refusal did not name the page, quoted:\n{named}"
    assert "wiki/log.md" not in named.split("than its merge: ")[-1], f"the log was named as owing an entry:\n{named}"
    assert "beta.md" not in named, f"a page Git merged unaided was named as owing an entry:\n{named}"
    assert "index.md" not in named, f"a generated index was named as owing an entry:\n{named}"
    # So does a new change made in the merge,
    untouched = third_page.read_text()
    third_page.write_text(untouched + "\nMerge-only refinement.\n")
    run(["git", "add", "wiki/capabilities/gamma.md"], root)
    assert "gamma.md" in reject(owes_own, "an unlogged change made inside a merge of the default branch")
    third_page.write_text(untouched)
    run(["git", "add", "wiki/capabilities/gamma.md"], root)
    # and one branch's version of a page Git merged, which drops the other branch's edit.
    run(["git", "checkout", "-q", "HEAD", "--", "wiki/capabilities/beta.md"], root)
    assert "beta.md" in reject(owes_own, "this branch's version of a page staged over Git's merge of it")
    other_page.write_text(merged_page)
    run(["git", "add", "wiki/capabilities/beta.md"], root)
    # An entry appended but not staged gets a hint.
    log.write_text(shared_log + theirs + ours + extra)
    reject("has changes that are not staged", "the extra entry appended and not staged")
    log.write_text(shared_log + theirs + ours)
    # The default branch's new capture is as immutable as this branch's own.
    (root / new_capture).write_text('{"captured_by": "modified-fixture"}\n')
    run(["git", "add", new_capture], root)
    reject("Existing raw captures are immutable", "the default branch's capture modified in a merge")
    run(["git", "rm", "-q", "--cached", new_capture], root)
    reject("Existing raw captures are immutable", "the default branch's capture removed in a merge")
    run(["git", "checkout", "-q", "other", "--", new_capture], root)
    # With one entry for the page resolved by hand, the merge is accepted.
    log.write_text(shared_log + theirs + ours + extra)
    run(["git", "add", "wiki/log.md"], root)
    run(["git", "commit", "-qm", "accept a merge of the default branch that keeps both entries"], root)
    assert parents() == 2, "merge of the default branch was not recorded"
    listed = (root / "wiki/capabilities/index.md").read_text()
    case_passed("merge of the default branch accepted with both entries")
    assert "fixture-default.md" in listed and "fixture-branch.md" in listed, "the merged index lost a page"

    # A merge of any other branch keeps the ordinary rule: this branch's log stays the prefix.
    shared_log = log.read_text()
    side = "\n## [2026-09-09] ingest | Side branch fixture\n\nTest actor imported a source.\n"
    ours = "\n## [2026-09-09] lint | This branch second fixture\n\nTest actor checked the proposed change.\n"
    before_side, side_ours = shared_log, ours
    run(["git", "checkout", "-qb", "side"], root)
    third_page.write_text(third_page.read_text() + "\nSide-branch refinement.\n")
    log.write_text(shared_log + side)
    run(["git", "add", "wiki/capabilities/gamma.md", "wiki/log.md"], root)
    run(["git", "commit", "-qm", "side branch appends an entry"], root)
    run(["git", "checkout", "-q", trunk], root)
    page.write_text(page.read_text() + "\nThird fixture refinement.\n")
    log.write_text(shared_log + ours)
    run(["git", "add", "wiki/capabilities/alpha.md", "wiki/log.md"], root)
    run(["git", "commit", "-qm", "this branch appends a second entry"], root)
    assert run(["git", "merge", "side"], root, check=False).returncode, "fixture merge did not conflict on the log"
    log.write_text(shared_log + side + ours)
    run(["git", "add", "wiki/log.md"], root)
    reject("preserve the previous bytes", "a side branch's entry first")
    reject("the ordinary rule applies because the merged-in commit", "the reason the merge rule did not apply")
    said = run(resolve, root).stdout
    assert "this branch's log, then the other branch's entries" in said, said
    assert log.read_text() == shared_log + ours + side, "the resolver wrote the wrong order for a merge of a side branch"
    run(["git", "add", "wiki/log.md"], root)
    run(["git", "commit", "-qm", "accept a merge of another branch with this branch's entries first"], root)
    assert parents() == 2, "merge of the side branch was not recorded"
    case_passed("merge of another branch accepted with this branch's entries first")

    # A commit of a branch the default branch merged is in that branch's history, but its log
    # was never the default branch's log, so the merge rule does not apply to it.
    shared_log = log.read_text()
    merged_side = "\n## [2026-09-10] ingest | Merged side branch fixture\n\nTest actor imported a source.\n"
    mainline = "\n## [2026-09-10] lint | Default branch second fixture\n\nTest actor checked the proposed change.\n"
    later = "\n## [2026-09-10] lint | This branch third fixture\n\nTest actor checked the proposed change.\n"
    run(["git", "checkout", "-qb", "sidepr"], root)
    third_page.write_text(third_page.read_text() + "\nMerged-side-branch refinement.\n")
    log.write_text(shared_log + merged_side)
    run(["git", "add", "wiki/capabilities/gamma.md", "wiki/log.md"], root)
    run(["git", "commit", "-qm", "a pull request branch appends an entry"], root)
    side_commit = run(["git", "rev-parse", "HEAD"], root).stdout.strip()
    run(["git", "checkout", "-qb", "mainline", trunk], root)
    page.write_text(page.read_text() + "\nDefault-branch second refinement.\n")
    log.write_text(shared_log + mainline)
    run(["git", "add", "wiki/capabilities/alpha.md", "wiki/log.md"], root)
    run(["git", "commit", "-qm", "the default branch appends an entry"], root)
    assert run(["git", "merge", "sidepr"], root, check=False).returncode, "fixture merge did not conflict on the log"
    log.write_text(shared_log + mainline + merged_side)
    run(["git", "add", "wiki/log.md"], root)
    run(["git", "commit", "-qm", "the default branch merges the pull request"], root)
    run(["git", "update-ref", "refs/remotes/origin/main", "mainline"], root)
    run(["git", "checkout", "-q", trunk], root)
    other_page.write_text(other_page.read_text() + "\nThird this-branch refinement.\n")
    log.write_text(shared_log + later)
    run(["git", "add", "wiki/capabilities/beta.md", "wiki/log.md"], root)
    run(["git", "commit", "-qm", "this branch appends a third entry"], root)
    assert run(["git", "merge", side_commit], root, check=False).returncode, "fixture merge did not conflict on the log"
    refuses(resolve, "Nothing written: the log at the merged-in commit", "the resolver merging a merged pull-request commit")
    log.write_text(shared_log + merged_side + later)
    run(["git", "add", "wiki/log.md"], root)
    reject("is not an earlier state of the log", "a merged pull-request commit's log first")
    run(["git", "merge", "--abort"], root)

    # A planted MERGE_HEAD relaxes nothing. Five things it could name:
    shared_log = log.read_text()
    run(["git", "checkout", "-qb", "ahead"], root)
    other_page.write_text(other_page.read_text() + "\nLater default-branch refinement.\n")
    log.write_text(shared_log + "\n## [2026-09-10] ingest | Later default branch fixture\n\nTest actor imported a source.\n")
    run(["git", "add", "wiki/capabilities/beta.md", "wiki/log.md"], root)
    run(["git", "commit", "-qm", "the default branch moves ahead"], root)
    ahead = run(["git", "rev-parse", "HEAD"], root).stdout
    run(["git", "checkout", "-q", trunk], root)
    untouched = third_page.read_text()
    third_page.write_text(untouched + "\nUnlogged refinement.\n")
    run(["git", "add", "wiki/capabilities/gamma.md"], root)
    planted = root / ".git/MERGE_HEAD"
    tree = run(["git", "write-tree"], root).stdout.strip()
    planted.write_text(run(["git", "commit-tree", tree, "-p", "HEAD", "-m", "holds the staged content"], root).stdout)
    reject(owes, "a planted commit that is not on the default branch")
    reject("is not on refs/remotes/origin/main", "the reason given for a planted commit off the default branch")
    # one on the default branch that HEAD already contains, whose log is not a prefix of HEAD's
    run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], root)
    planted.write_text(own_tip)
    refuses(resolve, "Nothing to resolve: this branch already contains", "the resolver with a planted commit HEAD already contains")
    reject(owes, "a planted default-branch commit that HEAD already contains")
    # two parents, the first a default-branch state HEAD lacks, with that branch's log first
    run(["git", "update-ref", "refs/remotes/origin/main", "mainline"], root)
    planted.write_text(run(["git", "rev-parse", "mainline"], root).stdout + own_tip)
    log.write_text(run(["git", "show", "mainline:wiki/log.md"], root).stdout + later)
    run(["git", "add", "wiki/log.md"], root)
    reject("the merge has more than one other parent", "two merge parents with the default branch's log first")
    run(["git", "restore", "--source=HEAD", "--staged", "--worktree", "wiki/log.md"], root)
    # one Git cannot merge with HEAD at all, so its own merge of the two is unknown
    orphan = run(["git", "commit-tree", "HEAD^{tree}", "-m", "unrelated history"], root).stdout.strip()
    run(["git", "update-ref", "refs/remotes/origin/main", orphan], root)
    planted.write_text(orphan + "\n")
    refuses(resolve, "refusing to merge unrelated histories", "the resolver when Git cannot merge the two branches")
    refuses(resolve, "Nothing written: `git merge-tree --write-tree` failed", "the resolver's own words when Git cannot merge")
    # one HEAD merged with its own entries first, so the merge rule would reorder HEAD's log around it
    run(["git", "update-ref", "refs/remotes/origin/main", "side"], root)
    planted.write_text(run(["git", "rev-parse", "side"], root).stdout)
    log.write_text(before_side + side + side_ours + later)
    run(["git", "add", "wiki/log.md"], root)
    reject("preserve the previous bytes", "a contained default-branch commit with the log reordered around it")
    run(["git", "restore", "--source=HEAD", "--staged", "--worktree", "wiki/log.md"], root)
    # one on the default branch that is ahead of HEAD, with the merged log staged
    run(["git", "update-ref", "refs/remotes/origin/main", ahead.strip()], root)
    planted.write_text(ahead)
    run(resolve, root)
    run(["git", "add", "wiki/log.md"], root)
    reject(owes_own, "a planted default-branch commit ahead of HEAD")
    run(["git", "restore", "--source=HEAD", "--staged", "--worktree", "wiki/log.md"], root)
    # and contents Git does not write there
    for content, message in (("not-a-commit\n", "not full commit ids"), ("other\n", "not full commit ids"),
                             (ahead.strip(), "not full commit ids"), (ahead.strip() + " " + own_tip, "not full commit ids"),
                             ("", "not full commit ids"), (ahead.upper(), "not full commit ids"),
                             ("1" * 40 + "\n", "is not a commit Git can read")):
        planted.write_text(content)
        reject(message, f"MERGE_HEAD holding {content!r}")
    planted.unlink()
    planted.mkdir()
    reject("Cannot read '", "a MERGE_HEAD that cannot be read, named in quotes")
    planted.rmdir()
    run(["git", "restore", "--source=HEAD", "--staged", "--worktree", "wiki/capabilities/gamma.md"], root)

    # A capture from any parent of an octopus merge (more than two parents) is immutable too,
    # and the merge rule never applies to one.
    shared_log = log.read_text()
    second_capture = "raw/2026-09-10-hook-fixture/note.json"
    run(["git", "checkout", "-qb", "with-capture"], root)
    (root / second_capture).parent.mkdir()
    (root / second_capture).write_text('{"captured_by": "fixture"}\n')
    log.write_text(shared_log + "\n## [2026-09-10] ingest | Capture fixture\n\nTest actor imported a source.\n")
    run(["git", "add", second_capture, "wiki/log.md"], root)
    run(["git", "commit", "-qm", "branch adds a capture"], root)
    run(["git", "checkout", "-qb", "no-wiki", trunk], root)
    makefile = root / "Makefile"
    makefile.write_text(makefile.read_text() + "# fixture\n")
    run(["git", "add", "Makefile"], root)
    run(["git", "commit", "-qm", "branch changes no wiki path"], root)
    run(["git", "checkout", "-q", trunk], root)
    run(["git", "update-ref", "refs/remotes/origin/main", "with-capture"], root)
    # The capture is on the second merge parent, so comparing with the first alone misses it.
    run(["git", "merge", "--no-commit", "no-wiki", "with-capture"], root)
    assert len((root / ".git/MERGE_HEAD").read_text().split()) == 2, "fixture did not start an octopus merge"
    refuses(resolve, "more than one other parent", "the resolver in an octopus merge")
    run(["git", "rm", "-q", "--cached", second_capture], root)
    reject("Existing raw captures are immutable", "a capture removed in an octopus merge")
    run(["git", "merge", "--abort"], root)

    # A merge Git completes on its own runs pre-merge-commit, which applies the ordinary rule:
    # it lets a clean merge through,
    shared_log = log.read_text()
    run(["git", "checkout", "-qb", "clean", trunk], root)
    third_page.write_text(third_page.read_text() + "\nClean-merge refinement.\n")
    log.write_text(shared_log + "\n## [2026-09-11] ingest | Clean merge fixture\n\nTest actor imported a source.\n")
    run(["git", "add", "wiki/capabilities/gamma.md", "wiki/log.md"], root)
    run(["git", "commit", "-qm", "a branch Git can merge on its own"], root)
    run(["git", "checkout", "-q", trunk], root)
    run(["git", "merge", "--no-ff", "--no-edit", "clean"], root)
    assert parents() == 2, "a clean merge was not recorded"
    # and refuses one that settles the log conflict by dropping this branch's entry.
    shared_log = log.read_text()
    run(["git", "checkout", "-qb", "theirs-wins", trunk], root)
    log.write_text(shared_log + "\n## [2026-09-12] ingest | Other side fixture\n\nTest actor imported a source.\n")
    run(["git", "add", "wiki/log.md"], root)
    run(["git", "commit", "-qm", "the other side appends an entry"], root)
    run(["git", "checkout", "-q", trunk], root)
    log.write_text(shared_log + "\n## [2026-09-12] lint | This side fixture\n\nTest actor checked the proposed change.\n")
    run(["git", "add", "wiki/log.md"], root)
    run(["git", "commit", "-qm", "this side appends an entry"], root)
    before = run(["git", "rev-parse", "HEAD"], root).stdout
    dropped = run(["git", "merge", "--no-edit", "-X", "theirs", "theirs-wins"], root, check=False)
    printed = dropped.stdout + dropped.stderr
    case_passed("pre-merge-commit refuses a merge that drops this branch's entry", "preserve the previous bytes")
    assert dropped.returncode and "preserve the previous bytes" in printed, (
        f"a merge that dropped this branch's entry was not refused by pre-merge-commit; rc={dropped.returncode}:\n{printed}")
    assert run(["git", "rev-parse", "HEAD"], root).stdout == before, "the refused merge was committed"
    run(["git", "merge", "--abort"], root, check=False)

    # The installer checks both hooks before linking either: a refusal changes nothing,
    hooks = root / ".git/hooks"
    (hooks / "pre-commit").unlink()
    (hooks / "pre-merge-commit").unlink()
    (hooks / "pre-merge-commit").write_text("#!/bin/sh\n")
    refused = run(["python3", "scripts/install-hooks"], root, check=False)
    assert refused.returncode and "No hook was installed or changed" in refused.stdout + refused.stderr, refused.stdout + refused.stderr
    case_passed("installer refusal changes nothing", "No hook was installed or changed")
    assert not (hooks / "pre-commit").exists() and not (hooks / "pre-commit").is_symlink(), "a refused install linked pre-commit anyway"
    (hooks / "pre-merge-commit").unlink()
    # and a link to this repo's hook under an older anchor is re-pointed, not refused.
    (hooks / "pre-commit").symlink_to("/nonexistent/worktree/.githooks/pre-commit")
    said = run(["python3", "scripts/install-hooks"], root).stdout
    assert "Re-anchored" in said, said
    case_passed("installer re-anchors an older link", "Re-anchored")
    for name in ("pre-commit", "pre-merge-commit"):
        assert (hooks / name).resolve() == (root / ".githooks" / name).resolve(), f"{name} is not linked to this repo's hook"

# A global core.hooksPath (a hook manager) makes Git ignore .git/hooks. install-hooks sets the
# repository-local core.hooksPath, which overrides it, and says so. The global config here is
# a temp file under a temp HOME; the real ~/.gitconfig is never read or written.
with tempfile.TemporaryDirectory(prefix="vault-hookspath-test-") as temp:
    temp = Path(temp).resolve()  # /var is /private/var on macOS; git prints the resolved path
    root = Path(temp) / "vault"
    root.mkdir()
    build_fixture(root)
    home, global_hooks = Path(temp) / "home", Path(temp) / "global-hooks"
    home.mkdir()
    global_hooks.mkdir()
    marker = Path(temp) / "global-hook-ran"
    (global_hooks / "pre-commit").write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 0\n")
    (global_hooks / "pre-commit").chmod(0o755)
    gitconfig = home / ".gitconfig"
    gitconfig.write_text(f"[core]\n\thooksPath = {global_hooks}\n")
    env = {"HOME": str(home), "GIT_CONFIG_GLOBAL": str(gitconfig)}
    run(["git", "init", "-q"], root, env=env)
    for key, value in (("user.name", "Vault hook fixture"), ("user.email", "fixture@example.invalid"),
                       ("commit.gpgsign", "false")):
        run(["git", "config", "--local", key, value], root, env=env)
    hooks_dir = Path(run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], root,
                         env=env).stdout.strip()) / "hooks"
    said = run(["python3", "scripts/install-hooks"], root, env=env).stdout
    assert f"Chaining: global core.hooksPath is {global_hooks}" in said and "overrides it" in said, said
    assert f"Active hooks path: {hooks_dir}" in said, said
    local = run(["git", "config", "--local", "--get", "core.hooksPath"], root, env=env).stdout.strip()
    assert Path(local) == hooks_dir, f"local core.hooksPath is {local!r}, want {hooks_dir}"
    chained = run(["git", "config", "--local", "--get", "vaultkit.chainHooksPath"], root, env=env).stdout.strip()
    assert Path(chained) == global_hooks, f"vaultkit.chainHooksPath is {chained!r}, want {global_hooks}"
    case_passed("install-hooks overrides a global core.hooksPath and chains it",
                "Chaining: global core.hooksPath is", "Active hooks path:")
    # Both run: the global hook first (it passes), then the vault's, which refuses an invalid page.
    good_readme = (root / "README.md").read_text()  # build_fixture's, which the indexes match
    (root / "README.md").write_text(good_readme.replace("status: draft", "status: invalid-fixture"))
    run(["git", "add", "--all"], root, env=env)
    refused = run(["git", "commit", "-qm", "invalid page under a global hooksPath"], root, check=False, env=env)
    assert refused.returncode and "invalid-fixture" in refused.stdout + refused.stderr, (
        f"the vault hook did not run under a global core.hooksPath:\n{refused.stdout}{refused.stderr}")
    assert marker.exists(), "the chained global pre-commit did not run"
    case_passed("the chained global hook runs, then the vault hook")
    # A failing global hook stops an otherwise valid commit.
    (root / "README.md").write_text(good_readme)
    run(["git", "add", "README.md"], root, env=env)
    (global_hooks / "pre-commit").write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 1\n")
    refused = run(["git", "commit", "-qm", "valid page, failing global hook"], root, check=False, env=env)
    assert refused.returncode and "the chained pre-commit hook" in refused.stderr, refused.stdout + refused.stderr
    assert run(["git", "rev-parse", "--verify", "--quiet", "HEAD"], root, check=False, env=env).returncode, \
        "a commit landed although the chained hook failed"
    case_passed("refused: a failing chained global hook stops the commit", "the chained pre-commit hook")
    (global_hooks / "pre-commit").write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 0\n")
    run(["git", "commit", "-qm", "valid page, passing global hook"], root, env=env)
    # --no-chain: the global hooks are not run, with a WARNING.
    said = run(["python3", "scripts/install-hooks", "--no-chain"], root, env=env).stdout
    assert f"WARNING: global core.hooksPath is {global_hooks}" in said and "--no-chain" in said, said
    assert run(["git", "config", "--local", "--get", "vaultkit.chainHooksPath"], root, check=False,
               env=env).returncode == 1, "--no-chain left vaultkit.chainHooksPath set"
    marker.unlink()
    (root / "README.md").write_text(good_readme.replace("status: draft", "status: invalid-fixture"))
    run(["git", "add", "README.md"], root, env=env)
    refused = run(["git", "commit", "-qm", "invalid page, no chain"], root, check=False, env=env)
    assert refused.returncode and "invalid-fixture" in refused.stdout + refused.stderr, refused.stdout + refused.stderr
    assert not marker.exists(), "the global pre-commit ran after --no-chain"
    (root / "README.md").write_text(good_readme)
    run(["git", "add", "README.md"], root, env=env)
    case_passed("install-hooks --no-chain warns and runs only the vault hook", "WARNING: global core.hooksPath is")
    run(["python3", "scripts/install-hooks"], root, env=env)  # chain again for --uninstall below
    # A local core.hooksPath naming another existing directory is refused, not replaced.
    run(["git", "config", "--local", "core.hooksPath", str(global_hooks)], root, env=env)
    refused = run(["python3", "scripts/install-hooks"], root, check=False, env=env)
    assert refused.returncode and "the repository-local core.hooksPath is" in refused.stdout + refused.stderr, (
        refused.stdout + refused.stderr)
    assert run(["git", "config", "--local", "--get", "core.hooksPath"], root, env=env).stdout.strip() == str(global_hooks)
    case_passed("install-hooks refuses another local core.hooksPath", "the repository-local core.hooksPath is")
    # --uninstall unsets only the value install-hooks set; the global path is active again.
    run(["git", "config", "--local", "core.hooksPath", str(hooks_dir)], root, env=env)
    said = run(["python3", "scripts/install-hooks", "--uninstall"], root, env=env).stdout
    assert "Unset the repository-local core.hooksPath" in said, said
    assert run(["git", "config", "--local", "--get", "core.hooksPath"], root, check=False, env=env).returncode == 1
    assert f"Active hooks path: {global_hooks}" in said, said
    assert "Unset vaultkit.chainHooksPath" in said and run(
        ["git", "config", "--local", "--get", "vaultkit.chainHooksPath"], root, check=False, env=env).returncode == 1, said
    case_passed("uninstall unsets the local core.hooksPath it set", "Unset the repository-local core.hooksPath")

# The chained directory's other hooks (pre-push, commit-msg, ...) keep running through
# pass-through links; a relative or self-naming global core.hooksPath is not chained; a chain
# that leads back into the vault's hooks stops after one round. Every planted hook writes only
# under this temp dir, and the loop cases count rounds and give up after three, so a missing
# guard fails the case instead of recursing.
with tempfile.TemporaryDirectory(prefix="vault-chain-test-") as temp:
    temp = Path(temp).resolve()
    root = temp / "vault"
    root.mkdir()
    build_fixture(root)
    home, global_hooks = temp / "home", temp / "global-hooks"
    home.mkdir()
    global_hooks.mkdir()
    gitconfig = home / ".gitconfig"
    env = {"HOME": str(home), "GIT_CONFIG_GLOBAL": str(gitconfig)}

    def global_hook(name, body):
        (global_hooks / name).write_text(f"#!/bin/sh\n{body}\n")
        (global_hooks / name).chmod(0o755)

    def set_global(value):
        gitconfig.write_text(f"[core]\n\thooksPath = {value}\n")

    global_hook("pre-commit", "exit 0")
    global_hook("commit-msg", f"printf '%s\\n' \"$1\" > '{temp}/commit-msg-ran'")
    global_hook("pre-push", f"printf '%s %s\\n' \"$1\" \"$2\" > '{temp}/pre-push-args'\n"
                            f"cat > '{temp}/pre-push-stdin'")
    global_hook("post-checkout", "exit 0")
    set_global(global_hooks)
    run(["git", "init", "-q"], root, env=env)
    for key, value in (("user.name", "Vault hook fixture"), ("user.email", "fixture@example.invalid"),
                       ("commit.gpgsign", "false")):
        run(["git", "config", "--local", key, value], root, env=env)
    hooks_dir = Path(run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], root,
                         env=env).stdout.strip()) / "hooks"
    hooks_dir.mkdir(exist_ok=True)
    (hooks_dir / "post-checkout").write_text("#!/bin/sh\nexit 0\n")  # someone else's hook
    (hooks_dir / "post-checkout").chmod(0o755)
    said = run(["python3", "scripts/install-hooks"], root, env=env).stdout
    for name in ("commit-msg", "pre-push"):
        assert f"Passing through {name}:" in said, said
        assert (hooks_dir / name).resolve() == (root / ".githooks/chain-passthrough").resolve(), name
    assert f"WARNING: {hooks_dir / 'post-checkout'} is not a vault-kit link" in said, said
    assert (hooks_dir / "post-checkout").read_text() == "#!/bin/sh\nexit 0\n", "install-hooks replaced a hook"
    # commit-msg runs through Git itself; pre-push is started as Git starts it, with the
    # remote's name and URL as arguments and the refs on standard input.
    run(["git", "add", "--all"], root, env=env)
    run(["git", "commit", "-qm", "chain fixture"], root, env=env)
    ran = (temp / "commit-msg-ran").read_text().strip() if (temp / "commit-msg-ran").exists() else ""
    assert ran.endswith("COMMIT_EDITMSG"), f"the chained commit-msg did not run: {ran!r}"
    refs = "refs/heads/main 1111 refs/heads/main 0000\n"
    pushed = subprocess.run([str(hooks_dir / "pre-push"), "origin", "file:///nowhere"], cwd=root, text=True,
                            input=refs, capture_output=True, env={**ISOLATED, **env})
    assert pushed.returncode == 0, pushed.stdout + pushed.stderr
    assert (temp / "pre-push-args").read_text() == "origin file:///nowhere\n"
    assert (temp / "pre-push-stdin").read_text() == refs
    global_hook("pre-push", "exit 7")
    failed = subprocess.run([str(hooks_dir / "pre-push"), "origin", "x"], cwd=root, text=True, input="",
                            capture_output=True, env={**ISOLATED, **env})
    assert failed.returncode == 7, f"the pass-through did not return the chained hook's status: {failed.returncode}"
    case_passed("a global commit-msg and pre-push keep running through pass-through links", "Passing through")
    said = run(["python3", "scripts/install-hooks", "--uninstall"], root, env=env).stdout
    assert "Removed the pass-through commit-msg hook" in said and not (hooks_dir / "pre-push").is_symlink(), said
    assert (hooks_dir / "post-checkout").is_file(), "--uninstall removed someone else's hook"
    case_passed("--uninstall removes the pass-through links", "Removed the pass-through")
    # A relative global core.hooksPath resolves inside each repository: not chained.
    set_global(".githooks")
    said = run(["python3", "scripts/install-hooks"], root, env=env).stdout
    assert "WARNING: Not chaining: global core.hooksPath is .githooks, a relative path" in said, said
    assert run(["git", "config", "--local", "--get", "vaultkit.chainHooksPath"], root, check=False,
               env=env).returncode == 1, "a relative global core.hooksPath was chained"
    case_passed("refused: chaining a relative global core.hooksPath", "Not chaining: global core.hooksPath is")
    # An absolute global core.hooksPath naming the vault's own .githooks: not chained.
    set_global(root / ".githooks")
    said = run(["python3", "scripts/install-hooks"], root, env=env).stdout
    assert "which is this vault's own hook directory" in said, said
    assert run(["git", "config", "--local", "--get", "vaultkit.chainHooksPath"], root, check=False,
               env=env).returncode == 1, "the vault's own .githooks was chained"
    case_passed("refused: chaining the vault's own hook directory", "this vault's own hook directory")
    # A chain recorded by hand (or by an older install) that leads back into the vault's own
    # hooks: one round, then the vault's checks, then the commit.
    loop = temp / "loop-hooks"
    loop.mkdir()
    counter = temp / "rounds"
    for name, back in (("pre-commit", root / ".githooks/pre-commit"), ("pre-push", hooks_dir / "pre-push")):
        (loop / name).write_text(
            f"#!/bin/sh\necho x >> '{counter}'\n"
            f"n=$(wc -l < '{counter}' | tr -d ' ')\n[ \"$n\" -le 3 ] || exit 1\nexec '{back}' \"$@\"\n")
        (loop / name).chmod(0o755)
    set_global(loop)
    run(["python3", "scripts/install-hooks"], root, env=env)
    assert (hooks_dir / "pre-push").is_symlink(), "no pass-through for the loop's pre-push"
    (root / "wiki/capabilities/alpha.md").write_text(
        (root / "wiki/capabilities/alpha.md").read_text() + "\nOne more line.\n")
    run(["git", "add", "wiki/capabilities/alpha.md"], root, env=env)
    with (root / "wiki/log.md").open("a") as log_file:
        log_file.write("\n## [2026-01-02] maintenance | Loop fixture\n\nTest actor edited alpha.\n")
    run(["git", "add", "wiki/log.md"], root, env=env)
    committed = run(["git", "commit", "-qm", "commit through a looping chain"], root, check=False, env=env)
    assert committed.returncode == 0, committed.stdout + committed.stderr
    assert counter.read_text().count("x") == 1, f"the chain ran {counter.read_text().count('x')} rounds"
    counter.unlink()
    pushed = subprocess.run([str(hooks_dir / "pre-push"), "origin", "x"], cwd=root, text=True, input="",
                            capture_output=True, env={**ISOLATED, **env})
    assert pushed.returncode == 0 and counter.read_text().count("x") == 1, (
        f"the pass-through looped: rc={pushed.returncode}, rounds={counter.read_text().count('x')}")
    case_passed("a chain that leads back into the vault's hooks runs one round")

# The interpreter the Makefile, the hooks and vaultconf run comes from scripts/venv-python.
# An untracked .venv is used, a worktree without one uses the primary checkout's, and a
# tracked .venv is refused and never run.
with tempfile.TemporaryDirectory(prefix="vault-venv-test-") as temp:
    temp = Path(temp).resolve()
    root = temp / "vault"
    root.mkdir()
    build_fixture(root)
    (root / ".gitignore").write_text("__pycache__/\n.venv/\n.worktrees/\n")
    run(["git", "init", "-q"], root)
    for key, value in (("user.name", "Vault hook fixture"), ("user.email", "fixture@example.invalid"),
                       ("commit.gpgsign", "false"), ("core.hooksPath", str(root / ".git/hooks"))):
        run(["git", "config", "--local", key, value], root)
    run(["python3", "scripts/install-hooks"], root)
    run(["git", "add", "--all"], root)
    run(["git", "commit", "-qm", "venv fixture"], root)
    # make check and make indexes read the pages make check lists: a .gitignore'd scratch
    # page without frontmatter is neither validated nor indexed.
    ignore_file = root / ".gitignore"
    committed_ignore = ignore_file.read_text()
    ignore_file.write_text(committed_ignore + "scratch/\n")
    (root / "scratch").mkdir()
    (root / "scratch/x.md").write_text("no frontmatter here\n")
    checked = run(["make", "--no-print-directory", "check"], root, check=False)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    indexed = run(["make", "--no-print-directory", "indexes"], root, check=False)
    assert indexed.returncode == 0 and not (root / "scratch/index.md").exists(), indexed.stdout + indexed.stderr
    shutil.rmtree(root / "scratch")
    ignore_file.write_text(committed_ignore)
    case_passed("a .gitignore'd page is neither validated nor indexed")
    # A bad name is reported once, not once per checker.
    bad_name = root / "tools/Bad_Name.txt"
    bad_name.parent.mkdir()
    bad_name.write_text("x\n")
    run(["git", "add", "tools/Bad_Name.txt"], root)
    checked = run(["make", "--no-print-directory", "check"], root, check=False)
    printed = checked.stdout + checked.stderr
    assert checked.returncode and printed.count("name must be lowercase kebab-case") == 1, printed
    case_passed("refused once: a tracked bad name", "name must be lowercase kebab-case")
    run(["git", "rm", "-q", "--cached", "tools/Bad_Name.txt"], root)
    shutil.rmtree(root / "tools")
    # Malformed frontmatter stops make indexes with a message, not a traceback, and before
    # any index is written.
    broken = root / "wiki/capabilities/broken.md"
    broken.write_text("---\ntitle: [unclosed\n---\n# Broken\n")
    indexed = run(["make", "--no-print-directory", "indexes"], root, check=False)
    printed = indexed.stdout + indexed.stderr
    assert indexed.returncode and "wiki/capabilities/broken.md: frontmatter is not valid YAML" in printed \
        and "No index was written" in printed and "Traceback" not in printed, printed
    assert run(["git", "status", "--porcelain"], root).stdout.strip() == "?? wiki/capabilities/broken.md", \
        "make indexes wrote an index before refusing"
    broken.unlink()
    case_passed("refused: make indexes on malformed frontmatter, cleanly", "No index was written")
    marker = temp / "venv-python-ran"

    def plant(where, body):
        python = where / ".venv/bin/python3"
        python.parent.mkdir(parents=True, exist_ok=True)
        python.write_text(f"#!/bin/sh\ntouch '{marker}'\n{body}\n")
        python.chmod(0o755)
        return python

    def commit_note(cwd, name, check=True):
        (cwd / "tools").mkdir(exist_ok=True)
        (cwd / f"tools/{name}.txt").write_text(f"{name}\n")
        run(["git", "add", f"tools/{name}.txt"], cwd)
        return run(["git", "commit", "-qm", f"add {name}"], cwd, check=check)

    def venv_python(cwd):
        return run(["sh", "scripts/venv-python"], cwd).stdout.strip()

    # Positive control: the untracked venv's python3 (a wrapper that marks, then runs the
    # real interpreter) is what the hook runs.
    wrapper = plant(root, f"exec '{sys.executable}' \"$@\"")
    assert venv_python(root) == str(wrapper), venv_python(root)
    commit_note(root, "primary-note")
    assert marker.exists(), "the hook did not run the untracked .venv's python3"
    case_passed("the hooks run an untracked .venv's python3")
    # A worktree has no .venv of its own; its hook uses the primary checkout's.
    worktree = root / ".worktrees/wt"
    run(["git", "worktree", "add", "-q", "-b", "wt", str(worktree)], root)
    assert not (worktree / ".venv").exists()
    assert venv_python(worktree) == str(wrapper), venv_python(worktree)
    marker.unlink()
    commit_note(worktree, "worktree-note")
    assert marker.exists(), "a worktree's hook did not fall back to the primary checkout's .venv"
    case_passed("a worktree's hooks use the primary checkout's .venv")
    # A .venv that is a symlink is not used.
    shutil.rmtree(root / ".venv")
    elsewhere = temp / "elsewhere"
    plant(elsewhere, f"exec '{sys.executable}' \"$@\"")
    (root / ".venv").symlink_to(elsewhere / ".venv")
    assert venv_python(root) == "", venv_python(root)
    (root / ".venv").unlink()
    case_passed("a symlinked .venv is not used")
    # A tracked .venv: its python3 claims success without checking anything. make check
    # refuses it, the hook does not run it, and neither does a worktree (it tracks it too).
    plant(root, "echo 'PASS: everything'\nexit 0")
    run(["git", "add", "-f", ".venv/bin/python3"], root)
    run(["git", "commit", "-q", "--no-verify", "-m", "add tooling"], root)
    marker.unlink()
    assert venv_python(root) == "", f"a tracked .venv was selected: {venv_python(root)}"
    checked = run(["make", "--no-print-directory", "check"], root, check=False)
    printed = checked.stdout + checked.stderr
    assert checked.returncode and ".venv must not be tracked" in printed, printed
    assert not marker.exists(), "make check ran the tracked .venv's python3"
    case_passed("refused: make check on a tracked .venv, without running it", ".venv must not be tracked")
    refused = commit_note(root, "after-tracked", check=False)
    printed = refused.stdout + refused.stderr
    assert refused.returncode and ".venv must not be tracked" in printed, printed
    assert not marker.exists(), "the hook ran the tracked .venv's python3"
    case_passed("refused: a commit while .venv is tracked; the hook does not run it", ".venv must not be tracked")

# A tracked .venv in another letter case, and a primary checkout that tracks .venv seen from a
# worktree's hook. The planted python3 only touches a marker file under this temp dir. These
# fixtures commit before any hook is installed, so the plants need no hook bypass.
with tempfile.TemporaryDirectory(prefix="vault-venv-case-test-") as temp:
    temp = Path(temp).resolve()
    marker = temp / "planted-python-ran"

    def venv_fixture(name):
        root = temp / name
        root.mkdir()
        build_fixture(root)
        (root / ".gitignore").write_text("__pycache__/\n.venv/\n.worktrees/\n")
        run(["git", "init", "-q"], root)
        for key, value in (("user.name", "Vault hook fixture"), ("user.email", "fixture@example.invalid"),
                           ("commit.gpgsign", "false")):
            run(["git", "config", "--local", key, value], root)
        run(["git", "add", "--all"], root)
        run(["git", "commit", "-qm", "venv case fixture"], root)
        return root

    def plant_python(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"#!/bin/sh\ntouch '{marker}'\necho 'PASS: everything'\nexit 1\n")
        path.chmod(0o755)

    # .VENV/bin/python3 is tracked. On a case-insensitive file system it is also
    # .venv/bin/python3; on a case-sensitive one an untracked .venv/bin/python3 sits beside
    # it. Either way venv-python names nothing, and make check refuses without running it.
    root = venv_fixture("case")
    plant_python(root / ".VENV/bin/python3")
    run(["git", "add", "-f", ".VENV/bin/python3"], root)
    run(["git", "commit", "-qm", "add tooling"], root)
    if not (root / ".venv/bin/python3").exists():
        plant_python(root / ".venv/bin/python3")
    selected = run(["sh", "scripts/venv-python"], root).stdout.strip()
    assert selected == "", f"a .venv tracked as .VENV was selected: {selected}"
    checked = run(["make", "--no-print-directory", "check"], root, check=False)
    printed = checked.stdout + checked.stderr
    assert checked.returncode and "Git index .VENV/bin/python3: .venv must not be tracked" in printed, printed
    assert not marker.exists(), "make check ran the python3 of a .venv tracked as .VENV"
    case_passed("refused: a .venv tracked as .VENV, without running it", ".venv must not be tracked")

    # The primary checkout tracks .venv/bin/python3; a worktree branched before that does not.
    # Git hands the worktree's hook GIT_DIR and GIT_INDEX_FILE; venv-python must still read
    # the primary's own index, see the tracked .venv, and fall back to python3.
    root = venv_fixture("primary")
    worktree = root / ".worktrees/clean"
    run(["git", "worktree", "add", "-q", "-b", "clean", str(worktree)], root)
    plant_python(root / ".venv/bin/python3")
    run(["git", "add", "-f", ".venv/bin/python3"], root)
    run(["git", "commit", "-qm", "contributor branch"], root)
    run(["git", "config", "--local", "core.hooksPath", str(root / ".git/hooks")], root)
    run(["python3", "scripts/install-hooks"], root)
    gitdir = run(["git", "rev-parse", "--path-format=absolute", "--absolute-git-dir"], worktree).stdout.strip()
    hook_env = {"GIT_DIR": gitdir, "GIT_INDEX_FILE": f"{gitdir}/index"}
    selected = run(["sh", "scripts/venv-python"], worktree, env=hook_env).stdout.strip()
    assert selected == "", f"a worktree's hook environment selected the primary's tracked .venv: {selected}"
    (worktree / "tools").mkdir()
    (worktree / "tools/note.txt").write_text("note\n")
    run(["git", "add", "tools/note.txt"], worktree)
    committed = run(["git", "commit", "-qm", "add note"], worktree, check=False)
    assert not marker.exists(), "a worktree's hook ran the primary checkout's tracked .venv python3"
    assert committed.returncode == 0, committed.stdout + committed.stderr
    case_passed("a worktree's hook skips the primary's tracked .venv and uses python3")

expected = EXPECTED - GITLEAKS_EXPECTED if not GITLEAKS else EXPECTED
if any("checksum" in name or "download" in name for name in SKIPPED):
    expected -= {"checksum mismatch for cached", "checksum mismatch for downloaded", "The secret scan fails closed"}
missing = {m for m in expected if not any(m in seen for seen in SEEN)}
assert not missing, f"expected refusals never asserted: {sorted(missing)}"
if SKIPPED:
    print(f"PASS: {len(CASES)} hook cases; SKIP: {len(SKIPPED)} cases not run: " + "; ".join(SKIPPED))
else:
    print(f"PASS: {len(CASES)} hook cases")
