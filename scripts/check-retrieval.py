#!/usr/bin/env python3
"""Exercise update and delete freshness in real QMD with a temporary probe page."""
import vaultconf
from pathlib import Path
import json
import subprocess
import uuid

ROOT = Path(__file__).resolve().parent.parent
QMD = str(ROOT / "scripts/qmd")
REFRESH = str(ROOT / "scripts/refresh-qmd")
COLLECTION = vaultconf.load(ROOT)["name"]
if not COLLECTION:
    raise SystemExit(vaultconf.check_initialized())


def run(*args):
    result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=180)
    if result.returncode:
        raise RuntimeError(f"{args[0]} exited {result.returncode}: {result.stderr} {result.stdout}")
    return result.stdout


def search(query, mode="search", limit=5):
    return json.loads(run(QMD, mode, query, "-c", COLLECTION, "--json", "-n", str(limit)))


# A unique, temporary Markdown document proves that refresh follows content
# updates AND removals. Never touch existing knowledge documents.
token = uuid.uuid4().hex[:12]
first, second = "vaultprobealpha" + token, "vaultprobebeta" + token
probe = ROOT / "wiki" / ("retrieval-probe-" + token + ".md")
assert not search(first), "negative control unexpectedly matched"
try:
    probe.write_text("---\ntype: Reference\ntitle: Retrieval probe\ndescription: Temporary freshness probe.\nstatus: draft\n---\n# Probe\n\n" + first + "\n")
    run(REFRESH, "--lexical-only")
    assert search(first), "new document was not indexed"
    probe.write_text(probe.read_text().replace(first, second))
    run(REFRESH, "--lexical-only")
    assert not search(first), "old contents survived an update"
    assert search(second), "new contents missing after update"
finally:
    probe.unlink(missing_ok=True)
    run(REFRESH, "--lexical-only")
assert not search(second), "deleted document remained searchable"
print("PASS: negative control, document update, and deletion.")
