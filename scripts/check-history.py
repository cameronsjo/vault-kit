#!/usr/bin/env python3
"""Enforce immutable raw captures and append-only wiki operation records."""
import vaultconf  # noqa: F401  (toolchain preflight)
import argparse
from collections import Counter
from pathlib import Path
import re
import subprocess

ROOT = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
LOG = "wiki/log.md"
HEADING = r"^## \[\d{4}-\d{2}-\d{2}\] (ingest|query|lint|maintenance) \| .+"
ENTRY_START = b"\n## ["
OBJECT_ID = r"[0-9a-f]{40}|[0-9a-f]{64}"
RAW_IMMUTABLE = "Existing raw captures are immutable; add a new dated capture instead."
OWES_ENTRY = "Source, wiki, or agent-schema changes require an appended wiki/log.md entry"
NEEDS_HEADING = "Append a dated ingest, query, lint, or maintenance heading to wiki/log.md."


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def status(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def blob(ref, path):
    # Inspect the tree/index first, so absent paths are distinct from Git failures.
    paths = git("ls-files", "-z") if ref == ":" else git("ls-tree", "-rz", "--name-only", ref)
    if path.encode() not in paths.split(b"\0"):
        return b""
    return git("show", (":" if ref == ":" else ref + ":") + path)


def names(*args):
    found = git("diff", "--no-renames", "--ignore-submodules=none", "--name-only", "-z", *args)
    return [p for p in found.decode().split("\0") if p]


def needs_log(changed):
    return any(p.startswith(("raw/", "wiki/")) or p in ("AGENTS.md", "CLAUDE.md")
               for p in changed if p != LOG)


def validate(changed, modified_raw, previous_log, proposed_log):
    errors = []
    if modified_raw:
        errors.append(RAW_IMMUTABLE)
    if previous_log and not proposed_log.startswith(previous_log):
        errors.append("wiki/log.md is append-only; preserve the previous bytes.")
    if needs_log(changed) and proposed_log == previous_log:
        errors.append(OWES_ENTRY + ".")
    if proposed_log != previous_log and proposed_log.startswith(previous_log):
        appended = proposed_log[len(previous_log):].decode("utf-8")
        if not re.search(HEADING, appended, re.M):
            errors.append(NEEDS_HEADING)
    return errors


def entries(log):
    # The text before the first entry, then each entry with the newline that starts it.
    cuts = [m.start() for m in re.finditer(re.escape(ENTRY_START), log)] + [len(log)]
    return log[:cuts[0]], [log[a:b] for a, b in zip(cuts, cuts[1:])]


def merged_log(ours, theirs):
    # The one log a merge of the default branch into this branch may produce: the default
    # branch's log whole, then this branch's entries the default branch lacks, in order.
    # None when the logs do not line up entry for entry: they open differently, or the two
    # branches hold different text under one heading.
    ours_top, ours_entries = entries(ours)
    theirs_top, theirs_entries = entries(theirs)
    if ours_top != theirs_top:
        return None
    held = Counter(theirs_entries)
    kept = []
    for entry in ours_entries:
        if held[entry]:
            held[entry] -= 1
        else:
            kept.append(entry)
    heading = lambda entry: entry.split(b"\n", 2)[1]
    under = {}
    for entry in theirs_entries:
        under.setdefault(heading(entry), set()).add(entry)
    if any(under.get(heading(entry), {entry}) != {entry} for entry in kept):
        return None
    return theirs + b"".join(kept)


def first_difference(expected, proposed):
    # Where proposed stops matching expected, which ends with a newline. Only called when
    # proposed does not start with expected. Log paragraphs are single long lines, so the
    # text is shown from a little before the first character that differs. Undecodable
    # bytes stay distinct (surrogateescape), so they cannot hide a difference.
    want = expected.decode("utf-8", "surrogateescape").split("\n")[:-1]
    have = proposed.decode("utf-8", "surrogateescape").split("\n")
    ended = have[-1] == ""
    have = have[:-1] if ended else have
    for number, line in enumerate(want, 1):
        if number > len(have):
            return f"line {number}: expected {show_line(line)}, found nothing (the file ends)"
        found = have[number - 1]
        if found != line:
            column = next((i for i, (a, b) in enumerate(zip(line, found)) if a != b), min(len(line), len(found)))
            start = max(column - 20, 0)
            where = f"line {number}" if start == 0 else f"line {number}, character {column + 1}"
            return f"{where}: expected {show_line(line, start)}, found {show_line(found, start)}"
    return f"line {len(want)}: the file must end with a newline" if not ended else "the end of the expected log"


def show_line(line, start=0):
    if not line:
        return "a blank line"
    shown = repr(line[start:start + 80])
    return shown if start == 0 else "..." + shown


def validate_merge(changed, own, modified_raw, ours, theirs, proposed_log):
    # The ordinary rules with one difference: HEAD's log need not be a prefix. The merged-in
    # commit is a state of the default branch, and CI accepts only that branch's entries
    # first, so the staged log must open with merged_log() byte for byte. own holds the
    # paths Git could not merge unaided or whose staged content differs from its merge.
    expected = merged_log(ours, theirs)
    if expected is None:
        # No automatic log. Both rules then hold at once, which only a branch whose log
        # already extends the default branch's can satisfy.
        errors = validate(changed, modified_raw, ours, proposed_log)
        if not proposed_log.startswith(theirs):
            errors.append("wiki/log.md must open with the default branch's log, which CI requires.")
        return errors and errors + ["The two logs do not line up entry for entry, so the merge has no automatic "
                                    "log; run `git merge --abort` and rebuild this branch on the default branch."]
    errors = []
    if modified_raw:
        errors.append(RAW_IMMUTABLE)
    if not proposed_log.startswith(expected):
        errors.append("wiki/log.md is append-only; a merge of the default branch keeps that branch's log whole, "
                      "then this branch's own entries. The staged log differs at "
                      f"{first_difference(expected, proposed_log)}. Run `make merge-log` to write the expected log; "
                      "each entry keeps the blank line before its heading.")
        return errors
    added = proposed_log[len(expected):].decode("utf-8", "replace")
    if needs_log(changed) and proposed_log == ours:
        errors.append(OWES_ENTRY + ".")
    elif needs_log(own) and not added:
        errors.append(OWES_ENTRY + " after the merged log. Git could not merge these paths unaided, or they are "
                      f"staged as something other than its merge: {', '.join(repr(p) for p in own if needs_log([p]))}.")
    if added and not re.search(HEADING, added, re.M):
        errors.append(NEEDS_HEADING)
    return errors


def merge_parents():
    # The commits MERGE_HEAD names. Git writes one full object id per line; anything else
    # is refused, so the parents checked here are the parents Git will record.
    path = Path(git("rev-parse", "--git-path", "MERGE_HEAD").decode().strip())
    path = path if path.is_absolute() else ROOT / path
    try:
        content = path.read_bytes()
    except FileNotFoundError:
        return []
    except OSError as error:
        raise SystemExit(f"Cannot read {str(path)!r}: {error}. A merge is in progress and its parents must be checked.")
    if not re.fullmatch(rb"(?:(?:" + OBJECT_ID.encode() + rb")\n)+", content):
        shown = content[:80].decode("utf-8", "replace")
        raise SystemExit(f"MERGE_HEAD holds {shown!r}, which is not full commit ids one per line as Git writes "
                         "them; run `git merge --abort`.")
    parents = content.decode().split()
    for parent in parents:
        if status("rev-parse", "--verify", "--quiet", parent + "^{commit}").returncode:
            raise SystemExit(f"MERGE_HEAD names {parent}, which is not a commit Git can read; run `git merge --abort`.")
    return parents


def default_ref():
    # (the remote default branch as this clone last fetched it or None, why there is none).
    head = status("symbolic-ref", "--quiet", "refs/remotes/origin/HEAD")
    ref = head.stdout.strip() if head.returncode == 0 else "refs/remotes/origin/main"
    if not ref.startswith("refs/remotes/origin/"):
        return None, f"refs/remotes/origin/HEAD points at {ref}, outside refs/remotes/origin/"
    if status("rev-parse", "--verify", "--quiet", ref + "^{commit}").returncode:
        return None, f"this clone has no {ref} (try `git fetch origin` or `git remote set-head origin -a`)"
    return ref, ""


def is_ancestor(commit, of):
    found = status("merge-base", "--is-ancestor", commit, of)
    if found.returncode not in (0, 1):
        raise SystemExit(f"Git could not compare {commit} with {of}: {found.stderr.strip()}")
    return found.returncode == 0


def automatic_merge(parent):
    # (the tree Git's own merge of HEAD and parent produces, the paths it could not merge
    # unaided, "") or (None, [], why it could not be computed).
    found = status("merge-tree", "--write-tree", "--name-only", "--no-messages", "-z", "HEAD", parent)
    tree, *conflicted = found.stdout.split("\0") if found.returncode in (0, 1) else [""]
    if not re.fullmatch(OBJECT_ID, tree):
        return None, [], (found.stderr.strip() or f"exit status {found.returncode}")
    return tree, [p for p in conflicted if p], ""


def merge_rule(parents):
    # (parent, automatic merge, "", False) when the merge rule applies, else (None, None,
    # why not, whether the merged-in commit is known to be off the default branch). The
    # rule applies only to a merge that brings in default-branch history HEAD does not
    # hold yet and whose log is a leading part of the default branch's log.
    if len(parents) != 1:
        return None, None, "no merge is in progress" if not parents else "the merge has more than one other parent", False
    parent = parents[0]
    ref, why_not = default_ref()
    if ref is None:
        return None, None, why_not, False
    if not is_ancestor(parent, ref):
        return None, None, f"the merged-in commit {parent[:12]} is not on {ref}", True
    if is_ancestor(parent, "HEAD"):
        return None, None, f"this branch already contains the merged-in commit {parent[:12]}", False
    if not blob(ref, LOG).startswith(blob(parent, LOG)):
        # Putting such a log first would reorder the default branch's own entries. A commit
        # of a branch the default branch merged after adding entries of its own is one case.
        return None, None, (f"the log at the merged-in commit {parent[:12]} is not an earlier state of the log "
                            f"at {ref}; merge {ref} itself"), False
    tree, conflicted, failure = automatic_merge(parent)
    if tree is None:
        return None, None, ("`git merge-tree --write-tree` failed, so Git's own merge of the two branches is "
                            f"unknown (it needs Git 2.38 or later): {failure}"), False
    return parent, (tree, conflicted), "", False


def generated_index(path):
    # An index.md the index generator owns and `make check` verifies; it skips dot-directories.
    parts = Path(path).parts
    return parts[0] == "wiki" and parts[-1] == "index.md" and not any(part.startswith(".") for part in parts)


def self_test():
    old = b"# History\n"
    good = old + b"\n## [2026-09-07] ingest | Example\n\nImported source.\n"
    assert not validate(["raw/new.json", "wiki/page.md", "wiki/log.md"], [], old, good)
    assert validate(["raw/old.json"], ["raw/old.json"], old, good)
    assert validate(["wiki/page.md"], [], old, old)
    assert validate(["wiki/log.md"], [], old, good.replace(old, b"# Rewritten\n"))
    assert validate(["wiki/log.md"], [], old, old + b"Unstructured addition\n")
    mine = b"\n## [2026-09-08] lint | Mine\n\nChecked.\n"
    theirs = b"\n## [2026-09-08] ingest | Theirs\n\nImported.\n"
    third = b"\n## [2026-09-09] maintenance | Merge\n\nResolved a page by hand.\n"
    both = b"\n## [2026-09-07] ingest | Shared\n\nOn both branches.\n"
    page = ["wiki/page.md", "wiki/log.md"]
    assert merged_log(old + mine, old + theirs) == old + theirs + mine, "default branch's entries come first"
    assert merged_log(old + mine, old) == old + mine, "nothing new on the default branch leaves this log as it is"
    assert merged_log(old, old + theirs) == old + theirs, "nothing new on this branch gives the default branch's log"
    assert merged_log(old + mine + both, old + both + theirs) == old + both + theirs + mine, "a shared entry is kept once"
    assert merged_log(old + both + both, old + both) == old + both + both, "a repeated entry is not collapsed"
    assert merged_log(b"# Other\n" + mine, old + theirs) is None, "differing openings have no automatic log"
    assert merged_log(old + both + mine, old + both + b"More on the shared entry.\n" + theirs) is None, "a grown entry was doubled"
    assert merged_log(old + both + b"Mine.\n" + mine, old + both + b"Theirs.\n" + theirs) is None, "an entry grown on both sides was doubled"
    ok = lambda *args: not validate_merge(*args)
    assert ok(page, [], [], old + mine, old + theirs, old + theirs + mine), "the expected merge was refused"
    assert ok(page, ["wiki/page.md"], [], old + mine, old + theirs, old + theirs + mine + third), "a logged own change was refused"
    assert ok(page, ["README.md"], [], old + mine, old + theirs, old + theirs + mine), "a change outside the wiki owed an entry"
    assert validate_merge(page, ["wiki/page.md"], [], old + mine, old + theirs, old + theirs + mine), "an unlogged own change passed"
    assert validate_merge(page, [], [], old + mine, old + theirs, old + mine + theirs), "this branch's entries came first"
    assert validate_merge(page, [], [], old + mine, old + theirs, old + theirs), "a merge dropped this branch's entry"
    assert validate_merge(page, [], [], old + mine, old + theirs, old + mine), "a merge dropped the default branch's entry"
    assert validate_merge(page, [], [], old + mine, old + theirs, b"# Rewritten\n" + theirs + mine), "a rewritten log passed"
    assert validate_merge(page, [], [], old + mine, old + theirs, old + theirs + mine.lstrip(b"\n")), "a lost blank line passed"
    assert validate_merge(page, [], ["raw/old.json"], old + mine, old + theirs, old + theirs + mine), "a changed capture passed"
    assert validate_merge(page, [], [], old + mine, old + theirs, old + theirs + mine + b"Unstructured addition\n"), "unheaded text passed"
    assert validate_merge(page, [], [], old, old, old), "an unlogged change passed in a merge"
    assert validate_merge(page, [], [], b"# Other\n" + mine, old + theirs, old + theirs + mine), "differing openings passed"
    grown = old + both + b"More on the shared entry.\n"
    assert validate_merge(page, [], [], old + both + mine, grown, old + both + mine + third), "this branch's log first passed with no automatic log"
    assert validate_merge(page, [], [], old + both + mine, grown, grown + mine), "the default branch's log first passed with no automatic log"
    assert not validate_merge(page, [], [], grown + mine, grown, grown + mine + third), "a log that already extends the default branch's was refused"
    assert merged_log(grown + mine, old + both) is None
    assert not validate_merge(page, [], [], grown + mine, old + both, grown + mine + third), "a log that starts with both logs was refused with no automatic log"
    assert first_difference(b"a\nb\n", b"a\nx\n") == "line 2: expected 'b', found 'x'"
    long_line = b"A" * 30 + b"B" * 70
    assert first_difference(long_line + b"\n", long_line[:60] + b"C" + long_line[61:] + b"\n") == (
        "line 1, character 61: expected ..." + repr("B" * 60) + ", found ..." + repr("B" * 20 + "C" + "B" * 39)), "the position of a late difference was not shown"
    assert first_difference(b"x" * 40 + b"\xff\n", b"x" * 40 + b"\xfe\n").startswith("line 1, character 41"), "undecodable bytes hid a difference"
    assert first_difference(b"y" * 156 + b"\n", b"y" * 120 + b"\n").startswith("line 1, character 121"), "the end of a shorter line was not located"
    accented = "é" * 60
    assert first_difference((accented + "\n").encode(), (accented[:30] + "X" + accented[31:] + "\n").encode()) == (
        "line 1, character 31: expected ..." + repr("é" * 50) + ", found ..." + repr("é" * 20 + "X" + "é" * 29)), "a position on a non-ASCII line counted bytes"
    assert first_difference(b"a\n\nb\n", b"a\nb\n") == "line 2: expected a blank line, found 'b'"
    assert first_difference(b"a\nb\n", b"a") == "line 2: expected 'b', found nothing (the file ends)"
    assert first_difference(b"a\nb\nc\n", b"a\n") == "line 2: expected 'b', found nothing (the file ends)"
    assert first_difference(b"a\n", b"") == "line 1: expected 'a', found nothing (the file ends)"
    assert first_difference(b"a\nb\n", b"a\nb") == "line 2: the file must end with a newline"
    assert generated_index("wiki/runbooks/index.md") and generated_index("wiki/index.md"), "a generated index owed an entry"
    assert not generated_index("wiki/.scratch/index.md") and not generated_index("docs/index.md"), "an index outside the generator's wiki set was exempt"
    assert not generated_index("wiki/runbooks/notes-index.md"), "a file merely ending in index.md was exempt"


def resolve_merge():
    # Write the log the staged check will accept for the merge in progress: the default
    # branch's log first under the merge rule, this branch's log first in any other merge.
    parents = merge_parents()
    parent, _, why_not, elsewhere = merge_rule(parents)
    if len(parents) != 1:
        raise SystemExit(f"Nothing to resolve: {why_not}.")
    if is_ancestor(parents[0], "HEAD"):
        raise SystemExit(f"Nothing to resolve: this branch already contains the merged-in commit {parents[0][:12]}.")
    if parent is None and not elsewhere:
        # The merged-in commit may be the default branch, whose log must come first, and
        # that cannot be confirmed here. Writing this branch's log first would fail CI.
        raise SystemExit(f"Nothing written: {why_not}.")
    waiting = [p for p in names("--diff-filter=U") if p != LOG and Path(p).name != "index.md"]
    if waiting:
        raise SystemExit("Resolve and `git add` these files first, then run this again: "
                         + ", ".join(repr(p) for p in waiting))
    if parent:
        expected = merged_log(blob("HEAD", LOG), blob(parent, LOG))
        order = "the default branch's log, then this branch's own entries"
    else:
        expected = merged_log(blob(parents[0], LOG), blob("HEAD", LOG))
        order = f"this branch's log, then the other branch's entries, because {why_not}"
    if expected is None:
        raise SystemExit("The two logs do not line up entry for entry, so there is no automatic result. "
                         "Run `git merge --abort` and rebuild this branch on the default branch.")
    target = ROOT / LOG
    if target.is_symlink() or target.parent.is_symlink():
        raise SystemExit(f"{LOG} is reached through a symbolic link; refusing to write through it.")
    try:
        if target.is_file() and target.read_bytes().startswith(expected):
            print(f"{LOG} already holds the merged log; nothing written. Next: git add {LOG}")
            return
        target.write_bytes(expected)
    except OSError as error:
        raise SystemExit(f"Cannot read or write {LOG}: {error}")
    print(f"Wrote {LOG}, replacing what was there: {order}. Next: git add {LOG}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--resolve-merge", action="store_true")
    parser.add_argument("--base")
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()
    self_test()
    if args.resolve_merge:
        resolve_merge()
        raise SystemExit(0)
    if args.staged:
        has_head = status("rev-parse", "--verify", "--quiet", "HEAD").returncode == 0
        base = "HEAD" if has_head else git("hash-object", "-t", "tree", "/dev/null").decode().strip()
        target = ":"
        diff = ["--cached", base]
        parents = merge_parents() if has_head else []
    else:
        if not args.base:
            parser.error("--base is required when checking committed history")
        base = args.base
        if re.fullmatch(r"0+", base):
            base = git("hash-object", "-t", "tree", "/dev/null").decode().strip()
        target = args.head
        diff = [base, target]
        parents = []
    changed = names(*diff)
    # A capture any parent of a merge holds is as immutable as HEAD's own.
    raw = sorted({p for against in [diff, *(["--cached", parent] for parent in parents)]
                  for p in names("--diff-filter=MDT", *against, "--", "raw/")})
    parent, automatic, why_not, _ = merge_rule(parents)
    if parent:
        tree, conflicted = automatic
        own = sorted(p for p in {*names("--cached", tree), *conflicted} if not generated_index(p))
        errors = validate_merge(changed, own, raw, blob(base, LOG), blob(parent, LOG), blob(target, LOG))
    else:
        errors = validate(changed, raw, blob(base, LOG), blob(target, LOG))
        if errors and parents:
            errors.append(f"A merge is in progress, and the ordinary rule applies because {why_not}: "
                          "this branch's log stays first.")
    if errors and args.staged:
        try:
            unstaged = (ROOT / LOG).is_file() and (ROOT / LOG).read_bytes() != blob(":", LOG)
        except OSError:
            unstaged = False
        if unstaged:
            errors.append(f"{LOG} has changes that are not staged; if you already edited it, run `git add {LOG}`.")
    if errors:
        raise SystemExit("\n".join(errors))
    print("PASS: raw captures unchanged; wiki history append-only; required operation entry present.")
