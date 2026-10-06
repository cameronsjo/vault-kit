#!/usr/bin/env python3
"""Run the pinned gitleaks (scripts/gitleaks) with a policy the scanned change cannot edit.

    scripts/scan-secrets.py staged | dir | range | worktree
    scripts/scan-secrets.py export-policy <ref> <dest-dir>

The policy is `.gitleaks.toml` (rules and allowlists) and `.gitleaksignore` (ignored
findings). A commit that adds a secret must not be able to silence it in the same commit,
so the policy always comes from the last reviewed commit, never from the files being
scanned:

  staged    the index, as the next commit would record it        policy from HEAD
  worktree  tracked and untracked files, minus .gitignore'd ones  policy from HEAD
  dir       the current directory (the hook's staged snapshot)   policy from $SECRETS_POLICY,
                                                                 else HEAD when cwd is a repo
  range     commits $SECRETS_BASE..HEAD (CI)                     policy from SECRETS_BASE

When the policy commit lacks a file (a first commit, or SECRETS_BASE empty, which scans all
history reachable from HEAD), the template defaults apply: gitleaks's default rules and no
ignored findings. A changed `.gitleaks.toml` or `.gitleaksignore` therefore takes effect
from the next commit.

gitleaks also reads a `.gitleaksignore` at the root of whatever it scans, so the dir modes
scan a copy with that file removed and range mode scans through a directory holding only a
pointer to the repository's Git data.

SECRETS_BASE must be empty or a full commit id Git can read; anything else exits 2.
Exit codes: 0 no leaks; 1 leaks found; 2 usage, a bad SECRETS_BASE, or no usable gitleaks.
"""
import vaultconf  # toolchain preflight; must precede everything else
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

SCRIPTS = Path(__file__).resolve().parent
DEFAULT_CONFIG = "# vault-kit default: gitleaks's own rules, nothing allowed extra.\n[extend]\nuseDefault = true\n"
FLAGS = ["--redact", "--no-banner", "--ignore-gitleaks-allow", "--exit-code", "1"]
POLICY_FILES = (".gitleaks.toml", ".gitleaksignore", "vault.toml")


def fail(message, code=2):
    print(f"scan-secrets: {message}", file=sys.stderr)
    raise SystemExit(code)


def git(cwd, *args, check=True):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    if check and result.returncode:
        fail(f"git {' '.join(args)} failed: {result.stderr.decode(errors='replace').strip()}")
    return result


def toplevel(cwd):
    result = git(cwd, "rev-parse", "--show-toplevel", check=False)
    return Path(result.stdout.decode().strip()) if result.returncode == 0 else None


def has_commit(root, ref):
    return git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False).returncode == 0


def export_policy(root, ref, dest):
    """Write ref's .gitleaks.toml (as config.toml), .gitleaksignore and vault.toml into dest.

    A file ref lacks is left out, except config.toml, which falls back to the default.
    Returns a short description of where the policy came from.
    """
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    found = []
    for name in POLICY_FILES:
        blob = None
        if ref and git(root, "cat-file", "-e", f"{ref}:{name}", check=False).returncode == 0:
            blob = git(root, "show", f"{ref}:{name}").stdout
            found.append(name)
        target = dest / ("config.toml" if name == ".gitleaks.toml" else name)
        if blob is not None:
            target.write_bytes(blob)
        elif name == ".gitleaks.toml":
            target.write_text(DEFAULT_CONFIG)
    return f"{ref} ({', '.join(found) or 'none of ' + ', '.join(POLICY_FILES)})" if ref else "template defaults"


def run_gitleaks(args, cwd, policy):
    command = [sys.executable, str(SCRIPTS / "gitleaks"), *args, "--config", str(policy / "config.toml"),
               "--gitleaks-ignore-path", str(policy), *FLAGS, "."]
    sys.stdout.flush()
    return subprocess.run(command, cwd=cwd).returncode


def copy_files(source, names, dest):
    """Copy regular, non-symlink files to dest, minus the root .gitleaksignore."""
    for name in names:
        if not name or name == ".gitleaksignore":
            continue
        path = Path(source) / name
        if path.is_symlink() or not path.is_file():
            continue
        target = Path(dest) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def scan_copy(names_source, names, policy):
    with tempfile.TemporaryDirectory(prefix="vault-scan-") as scan:
        copy_files(names_source, names, scan)
        return run_gitleaks(["dir"], scan, policy)


def head_policy(root, temp):
    ref = "HEAD" if root and has_commit(root, "HEAD") else None
    print(f"Secret-scan policy: {export_policy(root, ref, temp)}.")
    return Path(temp)


def mode_staged(root, temp):
    policy = head_policy(root, Path(temp) / "policy")
    with tempfile.TemporaryDirectory(prefix="vault-scan-") as scan:
        git(root, "checkout-index", "--all", f"--prefix={scan}/")
        ignore = Path(scan) / ".gitleaksignore"
        if ignore.exists() or ignore.is_symlink():
            ignore.unlink()
        return run_gitleaks(["dir"], scan, policy)


def mode_dir(cwd, temp):
    supplied = os.environ.get("SECRETS_POLICY", "")
    if supplied:
        policy = Path(supplied)
        if not (policy / "config.toml").is_file():
            fail(f"SECRETS_POLICY={supplied} has no config.toml; make it with "
                 "scripts/scan-secrets.py export-policy <ref> <dir>")
        print(f"Secret-scan policy: {supplied}.")
    else:
        policy = head_policy(toplevel(cwd), Path(temp) / "policy")
    names = [str(p.relative_to(cwd)) for p in sorted(Path(cwd).rglob("*"))
             if ".git" not in p.relative_to(cwd).parts]
    return scan_copy(cwd, names, policy)


def mode_range(root, temp):
    base = vaultconf.checked_base(root, os.environ.get("SECRETS_BASE", ""))
    head = git(root, "rev-parse", "HEAD").stdout.decode().strip()
    policy = Path(temp) / "policy"
    print(f"Secret-scan policy: {export_policy(root, base or None, policy)}.")
    gitdir = git(root, "rev-parse", "--absolute-git-dir").stdout.decode().strip()
    # gitleaks reads the scan root's .gitleaksignore; this root holds only a pointer to the
    # repository's Git data, so the commit under scan cannot supply one.
    source = Path(temp) / "source"
    source.mkdir()
    (source / ".git").write_text(f"gitdir: {gitdir}\n")
    # -m: a merge commit's patch against each parent, so a secret only a merge adds (an "evil
    # merge" resolution) is read; plain `git log -p` shows no diff for a merge at all.
    # --text: a committed .gitattributes (-diff, binary) cannot hide a file's lines.
    log_opts = "-m --text " + (f"{base}..{head}" if base else head)
    if not base:
        print("SECRETS_BASE is empty: scanning all history reachable from HEAD.")
    return run_gitleaks(["git", f"--log-opts={log_opts}"], source, policy)


def mode_worktree(root, temp):
    policy = head_policy(root, Path(temp) / "policy")
    names = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard").stdout.decode().split("\0")
    return scan_copy(root, names, policy)


def main(argv):
    if argv[:1] == ["export-policy"] and len(argv) == 3:
        root = toplevel(Path.cwd())
        print(export_policy(root, argv[1] if root and has_commit(root, argv[1]) else None, argv[2]))
        return 0
    modes = {"staged": mode_staged, "dir": mode_dir, "range": mode_range, "worktree": mode_worktree}
    if len(argv) != 1 or argv[0] not in modes:
        fail("usage: scan-secrets.py staged|dir|range|worktree | export-policy <ref> <dest-dir>")
    cwd = Path.cwd()
    root = cwd if argv[0] == "dir" else toplevel(cwd)
    if root is None:
        fail(f"{argv[0]} mode needs a Git work tree")
    with tempfile.TemporaryDirectory(prefix="vault-secrets-") as temp:
        return modes[argv[0]](root, temp)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
