#!/usr/bin/env python3
"""Match a numbered list of private patterns against text, paths and Git history.

Shared by check-vault.py (the [redaction] deny list) and scripts/tripwire. A hit is reported
by pattern number only. A path that itself matches is printed with each match replaced by
`[<label> N]`, so the report never carries the text the patterns exist to keep private.

Standard library only, with no toolchain preflight: scripts/tripwire imports it and runs
without PyYAML. check-vault.py imports vaultconf (the preflight) before this module.

Every patch is read with --text: a committed .gitattributes (`*.md -diff`, `binary`) would
otherwise turn a change into "Binary files differ" and hide its lines.
"""
import subprocess

UTF_BOMS = ((b"\xff\xfe\x00\x00", "utf-32-le"), (b"\x00\x00\xfe\xff", "utf-32-be"),
            (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be"))


def wide_encoding(data):
    """"UTF-16" or "UTF-32" when data starts with that byte-order mark, else None."""
    for bom, codec in UTF_BOMS:
        if data.startswith(bom):
            return codec[:6].upper()
    return None


def decode(data):
    """Text to scan, or None for a binary file.

    A UTF-16 or UTF-32 byte-order mark decodes as that encoding (such text is full of NUL
    bytes). Otherwise a NUL in the first 8 KiB means binary, and everything else decodes as
    UTF-8 with undecodable bytes kept as placeholders, so another encoding cannot hide an
    ASCII match.
    """
    for bom, codec in UTF_BOMS:
        if data.startswith(bom):
            return data[len(bom):].decode(codec, "replace")
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", "surrogateescape")


def line_hits(text, patterns):
    """Sorted {(line, number)} for every pattern match in text; numbers count from 1."""
    hits = set()
    for number, pattern in enumerate(patterns, 1):
        for match in pattern.finditer(text):
            hits.add((text.count("\n", 0, match.start()) + 1, number))
    return sorted(hits)


def path_hits(path, patterns):
    return sorted({number for number, pattern in enumerate(patterns, 1) if pattern.search(path)})


def shown(path, patterns, label):
    """path with every match replaced by [<label> N]."""
    for number, pattern in enumerate(patterns, 1):
        path = pattern.sub(f"[{label} {number}]", path)
    return path


def _git(root, *args):
    return subprocess.run(["git", "-c", "core.quotePath=false", *args], cwd=root,
                          capture_output=True, check=True).stdout


def _added_lines(patch):
    """Yield (path, text) for each added line of a `git diff-tree -p` patch."""
    path, in_header = None, False
    for raw in patch.split(b"\n"):
        if raw.startswith(b"diff --git "):
            path, in_header = None, True
        elif in_header and raw.startswith(b"+++ "):
            name = raw[4:].decode("utf-8", "surrogateescape")
            if name.startswith('"') and name.endswith('"'):
                name = name[1:-1]
            path = name[2:] if name.startswith("b/") else None
        elif raw.startswith(b"@@"):
            in_header = False
        elif not in_header and raw.startswith(b"+") and path is not None:
            yield path, raw[1:].decode("utf-8", "surrogateescape")


def parent_args(root, commit):
    """diff-tree arguments that compare commit with its first parent (or the empty tree)."""
    parents = _git(root, "rev-list", "--parents", "-n1", commit).decode().split()[1:]
    return [parents[0], commit] if parents else ["--root", commit]


def wide_texts(root, against):
    """Yield (path, encoding, text) for each UTF-16 or UTF-32 file (one with a byte-order
    mark) that a diff-tree comparison adds or changes.

    A patch is read as bytes split on newlines, and a UTF-16 or UTF-32 line holds a NUL
    between every ASCII character, so no pattern matches it there. The whole new blob is
    decoded instead. Deletions, submodules and symlinks (whose target text the patch
    carries as ASCII) are skipped.
    """
    raw = _git(root, "diff-tree", "-r", "-z", "--raw", "--no-abbrev", "--no-renames",
               "--no-commit-id", *against).split(b"\0")
    blobs = []
    for i in range(0, len(raw) - 1, 2):
        fields = raw[i].split()
        if len(fields) < 5 or not fields[0].startswith(b":"):
            continue
        mode, blob, status = fields[1], fields[3].decode(), fields[4]
        if status.startswith(b"D") or mode in (b"160000", b"120000") or set(blob) == {"0"}:
            continue
        blobs.append((raw[i + 1].decode("utf-8", "surrogateescape"), blob))
    if not blobs:
        return
    out = subprocess.run(["git", "cat-file", "--batch"], cwd=root, capture_output=True, check=True,
                         input=b"".join(blob.encode() + b"\n" for _, blob in blobs)).stdout
    offset = 0
    for path, blob in blobs:
        header_end = out.index(b"\n", offset)
        header = out[offset:header_end].split()
        if len(header) != 3:
            raise RuntimeError(f"git cat-file cannot read blob {blob}; the scan is incomplete")
        size = int(header[2])
        data = out[header_end + 1:header_end + 1 + size]
        offset = header_end + 1 + size + 1
        encoding = wide_encoding(data)
        if encoding:
            yield path, encoding, decode(data)


def range_hits(root, base, patterns, label, exempt=()):
    """Hits in every commit of base..HEAD (all of HEAD's history when base is empty).

    Each commit is read on its own: its message, the names of the paths it touches, and the
    lines it adds against its first parent. An intermediate commit whose text a later commit
    removed is still reported. Lines added to a path in `exempt` are skipped (vault.toml
    holds the deny patterns themselves); its name is still checked. A UTF-16 or UTF-32 file
    the commit adds or changes is decoded whole and every line of it is scanned, since its
    patch lines cannot match (wide_texts).
    """
    spec = [f"{base}..HEAD"] if base else ["HEAD"]
    commits = _git(root, "rev-list", "--reverse", *spec).decode().split()
    errors = []
    for commit in commits:
        short = commit[:12]
        message = _git(root, "log", "-1", "--format=%B", commit).decode("utf-8", "surrogateescape")
        for number in sorted({n for _, n in line_hits(message, patterns)}):
            errors.append(f"commit {short}: message matches {label} {number}")
        against = parent_args(root, commit)
        names = _git(root, "diff-tree", "-r", "--no-renames", "--name-only", "-z", "--no-commit-id",
                     *against).decode("utf-8", "surrogateescape").split("\0")
        for name in sorted(n for n in names if n):
            for number in path_hits(name, patterns):
                errors.append(f"commit {short}: path {shown(name, patterns, label)} matches {label} {number}")
        patch = _git(root, "diff-tree", "-r", "-p", "--text", "--no-textconv", "--no-renames",
                     "--no-color", "--no-ext-diff", "--no-commit-id", *against)
        seen = set()
        for path, text in _added_lines(patch):
            if path in exempt:
                continue
            for number, pattern in enumerate(patterns, 1):
                if (path, number) not in seen and pattern.search(text):
                    seen.add((path, number))
                    errors.append(f"commit {short}: {shown(path, patterns, label)}: an added line "
                                  f"matches {label} {number}")
        for path, encoding, text in wide_texts(root, against):
            if path in exempt:
                continue
            for number in sorted({n for _, n in line_hits(text, patterns)}):
                if (path, number) not in seen:
                    seen.add((path, number))
                    errors.append(f"commit {short}: {shown(path, patterns, label)}: a line of its "
                                  f"{encoding} text matches {label} {number}")
    return errors, len(commits)
