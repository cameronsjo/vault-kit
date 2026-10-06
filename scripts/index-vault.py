#!/usr/bin/env python3
"""Generate compact OKF directory indexes from frontmatter descriptions."""
import vaultconf
from pathlib import Path
from urllib.parse import quote
import importlib.util
import sys

ROOT = Path(__file__).resolve().parent.parent
# --title overrides vault.toml: init-vault regenerates indexes before it writes vault.toml.
TITLE = (sys.argv[sys.argv.index("--title") + 1] if "--title" in sys.argv[:-1]
         else vaultconf.load(ROOT)["title"] or "Vault")
spec = importlib.util.spec_from_file_location("check_vault", ROOT / "scripts/check-vault.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
# The pages make check covers (tracked, plus untracked and not .gitignore'd); a scratch file
# .gitignore excludes is not indexed. Every page is parsed before any index is written, so
# malformed frontmatter stops the run cleanly with nothing changed.
docs = module.documents(ROOT)
pages = {}
for doc in docs:
    if doc.name in ('index.md', 'log.md') or doc.is_symlink():
        continue
    try:
        pages[doc], _ = module.parse(doc)
    except ValueError as error:  # malformed or non-mapping YAML, unclosed block, bad bytes
        sys.stderr.write(f"{doc.relative_to(ROOT)}: {error}; fix it, then run make indexes again. "
                         "No index was written.\n")
        raise SystemExit(1)
dirs = {p.parent for p in docs}
for directory in list(dirs):
    dirs.update(p for p in directory.parents if p == ROOT or p.is_relative_to(ROOT))
dirs = sorted(dirs, key=lambda p: str(p))
changed = []
for directory in dirs:
    prefix = '---\nokf_version: "0.2"\n---\n' if directory == ROOT else ''
    body = prefix + f"# {directory.name if directory != ROOT else TITLE}\n\n"
    for child in sorted(directory.iterdir()):
        if child.is_dir() and child in dirs:
            body += f"- [{child.name}]({quote(child.name)}/index.md) — Browse {child.name.lower()}.\n"
        elif child in pages:
            data = pages[child]
            body += f"- [{data.get('title', child.stem)}]({quote(child.name)}) — {data.get('description', 'Read this document.')}\n"
    if (directory / 'log.md').exists():
        body += '- [Update history](log.md) — Changes to this knowledge bundle.\n'
    # A directory with nothing to list ends after its heading: a trailing blank line is
    # whitespace error `git diff --check` (and so the pre-commit hook) refuses in a new file.
    body = body.rstrip('\n') + '\n'
    dest = directory / 'index.md'
    # A committed symlink would send the write (or the comparison read) outside the vault.
    vaultconf.refuse_symlink(ROOT, dest)
    if not dest.exists() or dest.read_text() != body:
        changed.append(str(dest.relative_to(ROOT)))
        if '--check' not in sys.argv:
            vaultconf.safe_write(ROOT, dest, body)
if '--check' in sys.argv and changed:
    raise SystemExit('Stale indexes: ' + ', '.join(changed))
print(('Checked' if '--check' in sys.argv else 'Generated') + f' {len(dirs)} directory indexes.')
