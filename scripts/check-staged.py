#!/usr/bin/env python3
"""Validate the proposed commit without changing the index or working tree."""
import vaultconf  # noqa: F401  (toolchain preflight)
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
subprocess.run(["git", "diff", "--cached", "--check"], cwd=ROOT, check=True)
subprocess.run([sys.executable, "scripts/check-history.py", "--staged"], cwd=ROOT, check=True)
spec = importlib.util.spec_from_file_location("check_vault", ROOT / "scripts/check-vault.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
errors = validator.validate_git_paths(ROOT)
if errors:
    raise SystemExit("\n".join(errors))

with tempfile.TemporaryDirectory(prefix="vault-staged-") as temp:
    snapshot, policy = Path(temp) / "snapshot", Path(temp) / "policy"
    # The scan policy (.gitleaks.toml, .gitleaksignore) comes from HEAD, not from the
    # snapshot: a commit must not be able to silence its own findings. A first commit has no
    # HEAD, so the template defaults apply.
    subprocess.run([sys.executable, "scripts/scan-secrets.py", "export-policy", "HEAD", str(policy)],
                   cwd=ROOT, check=True)
    subprocess.run(["git", "checkout-index", "--all", f"--prefix={snapshot}/"], cwd=ROOT, check=True)
    print("Checking the staged snapshot (not unstaged files).", flush=True)
    # The snapshot is exactly the staged index, so check-vault.py's redaction scan and a
    # gitleaks scan of the directory both read what this commit would record. It has no
    # .git, so the secret scan runs in dir mode rather than git --staged.
    # HEAD's deny list too, so a commit that empties [redaction] deny is checked against the
    # list it removes. A first commit has none to compare with and uses its own.
    head_toml = policy / "vault.toml"
    deny_from = [f"DENY_FROM={head_toml}"] if head_toml.is_file() else []
    # The snapshot has no .venv, so pass this interpreter on: as PYTHON for the Makefile, and
    # first on PATH for the scripts and tools the check starts.
    env = {**os.environ, "PATH": os.pathsep.join([os.path.dirname(sys.executable), os.environ.get("PATH", "")])}
    result = subprocess.run(["make", "check", f"PYTHON={sys.executable}", "SECRETS_MODE=dir", f"SECRETS_POLICY={policy}", *deny_from],
                            cwd=snapshot, env=env)
    if result.returncode:
        raise SystemExit(result.returncode)
