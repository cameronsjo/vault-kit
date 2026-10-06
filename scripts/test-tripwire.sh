#!/usr/bin/env bash
# Exercise scripts/tripwire in a scratch repository with synthetic patterns. It never reads
# the real VAULT_KIT_TRIPWIRE: every run below sets its own patterns.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
repo=$(pwd)
tmp=$(cd "$(mktemp -d)" && pwd -P)
trap 'rm -rf "$tmp"' EXIT
fail=0
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null PYTHONDONTWRITEBYTECODE=1
unset VAULT_KIT_TRIPWIRE
g() { git -C "$v" -c user.name=fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false -c core.hooksPath=/dev/null "$@"; }

v="$tmp/v"; mkdir -p "$v/scripts" "$v/notes"
cp "$repo/scripts/tripwire" "$v/scripts/tripwire"
cp "$repo/scripts/patternscan.py" "$v/scripts/patternscan.py"
printf 'a clean page\n' > "$v/notes/a.md"
g init -q -b main && g add -A && g commit -q -m "seed"
seed=$(g rev-parse HEAD)
pats="$tmp/patterns"; printf 'nomatch-qqq\nzorblax-[0-9]+\n' > "$pats"
tw() { python3 "$v/scripts/tripwire" "$@" >"$tmp/out" 2>&1; }
# The output must never carry the synthetic term, whatever the case.
leak() { if grep -qi 'zorblax' "$tmp/out"; then echo "FAIL: $1: output echoes the matched text:"; cat "$tmp/out"; fail=1; fi; }

echo "--- a clean tree and history pass"
tw --patterns "$pats"; rc=$?
[ "$rc" -eq 0 ] && grep -q 'PASS: tripwire: 2 pattern(s), no hit' "$tmp/out" || { echo "FAIL: clean run rc=$rc"; cat "$tmp/out"; fail=1; }

echo "--- a tracked line hit names file:line and pattern number only, case-insensitively"
printf 'line one\nsee ZORBLAX-42 here\n' > "$v/notes/b.md"; g add notes/b.md; g commit -q -m "add b"
tw --patterns "$pats" --no-history; rc=$?
[ "$rc" -eq 1 ] && grep -qx 'notes/b.md:2: tripwire pattern 2' "$tmp/out" || { echo "FAIL: tree hit rc=$rc"; cat "$tmp/out"; fail=1; }
leak "tree hit"

echo "--- an untracked file is scanned too"
printf 'zorblax-9\n' > "$v/notes/new.md"
tw --patterns "$pats" --no-history
grep -qx 'notes/new.md:1: tripwire pattern 2' "$tmp/out" || { echo "FAIL: untracked file not scanned"; cat "$tmp/out"; fail=1; }
rm "$v/notes/new.md"

echo "--- a path-name hit withholds the path"
mkdir -p "$v/zorblax-7"; printf 'clean\n' > "$v/zorblax-7/x.txt"
tw --patterns "$pats" --no-history; rc=$?
[ "$rc" -eq 1 ] && grep -qx 'a path name in the tree (withheld): tripwire pattern 2' "$tmp/out" || { echo "FAIL: path hit rc=$rc"; cat "$tmp/out"; fail=1; }
leak "path hit"
rm -r "$v/zorblax-7"

echo "--- history: a line added then removed is found in the patch; a message hit too"
g rm -q notes/b.md; g commit -q -m "remove b"
g commit -q --allow-empty -m "mention Zorblax-3 in a message"
tw --patterns "$pats"; rc=$?
add_b=$(g rev-parse HEAD~2); msg=$(g rev-parse HEAD)
[ "$rc" -eq 1 ] || { echo "FAIL: history hits rc=$rc"; cat "$tmp/out"; fail=1; }
grep -qx "$add_b: tripwire pattern 2 in the patch" "$tmp/out" || { echo "FAIL: removed line not found in history"; cat "$tmp/out"; fail=1; }
grep -qx "$msg: tripwire pattern 2 in the message" "$tmp/out" || { echo "FAIL: message hit not found"; cat "$tmp/out"; fail=1; }
leak "history hit"
tw --patterns "$pats" --base "$msg"; rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL: --base at the tip still reported hits rc=$rc"; cat "$tmp/out"; fail=1; }
tw --patterns "$pats" --base "$seed"; rc=$?
[ "$rc" -eq 1 ] || { echo "FAIL: --base before the hits found nothing rc=$rc"; cat "$tmp/out"; fail=1; }

echo "--- patterns from the environment"
VAULT_KIT_TRIPWIRE=$'nomatch-qqq\nzorblax-[0-9]+' tw --base "$seed"; rc=$?
[ "$rc" -eq 1 ] && grep -q 'tripwire pattern 2 in the message' "$tmp/out" || { echo "FAIL: env patterns rc=$rc"; cat "$tmp/out"; fail=1; }

echo "--- a bad regex, no patterns, or a bad base fail closed"
printf 'nomatch-qqq\n(?P<zorblaxgrp>a)(?P<zorblaxgrp>b)\n' > "$tmp/bad"
tw --patterns "$tmp/bad"; rc=$?
[ "$rc" -eq 2 ] && grep -q 'pattern 2 is not a valid regex' "$tmp/out" || { echo "FAIL: bad regex rc=$rc"; cat "$tmp/out"; fail=1; }
leak "bad regex"
: > "$tmp/empty"
tw --patterns "$tmp/empty"; rc=$?
[ "$rc" -eq 2 ] || { echo "FAIL: empty patterns rc=$rc"; fail=1; }
VAULT_KIT_TRIPWIRE='' tw; rc=$?
[ "$rc" -eq 2 ] || { echo "FAIL: empty env rc=$rc"; fail=1; }
tw --patterns "$pats" --base abc; rc=$?
[ "$rc" -eq 2 ] || { echo "FAIL: short base rc=$rc"; fail=1; }
tw --patterns "$pats" --base "$(printf '%040d' 0)"; rc=$?
[ "$rc" -eq 2 ] || { echo "FAIL: unknown base rc=$rc"; fail=1; }

echo "--- a committed '* -diff' hides nothing: history patches and the tree are still read"
attr_base=$(g rev-parse HEAD)
printf '* -diff\n' > "$v/.gitattributes"; g add .gitattributes; g commit -q -m "attributes"
printf 'zorblax-11\n' > "$v/notes/hidden.md"; g add notes/hidden.md; g commit -q -m "add hidden"
add_hidden=$(g rev-parse HEAD)
g rm -q notes/hidden.md; g commit -q -m "remove hidden"
tw --patterns "$pats" --base "$attr_base"; rc=$?
[ "$rc" -eq 1 ] && grep -qx "$add_hidden: tripwire pattern 2 in the patch" "$tmp/out" ||
  { echo "FAIL: a -diff patch hid a removed line rc=$rc"; cat "$tmp/out"; fail=1; }
printf 'kept zorblax-12\n' > "$v/notes/kept.md"
tw --patterns "$pats" --no-history; rc=$?
[ "$rc" -eq 1 ] && grep -qx 'notes/kept.md:1: tripwire pattern 2' "$tmp/out" ||
  { echo "FAIL: a -diff file was skipped in the tree rc=$rc"; cat "$tmp/out"; fail=1; }
leak "-diff tree hit"
rm "$v/notes/kept.md"

echo "--- UTF-16 text with a byte-order mark is scanned, not skipped as binary"
python3 -c 'import sys; open(sys.argv[1], "wb").write("one\nzorblax-13\n".encode("utf-16"))' "$v/notes/wide.txt"
tw --patterns "$pats" --no-history; rc=$?
[ "$rc" -eq 1 ] && grep -qx 'notes/wide.txt:2: tripwire pattern 2' "$tmp/out" ||
  { echo "FAIL: UTF-16 text not scanned rc=$rc"; cat "$tmp/out"; fail=1; }
rm "$v/notes/wide.txt"

echo "--- history: UTF-16 and UTF-32 text added then removed is found (commit and number only)"
wide_base=$(g rev-parse HEAD)
python3 -c 'import sys; open(sys.argv[1], "wb").write("one\nzorblax-16\n".encode("utf-16"))' "$v/notes/wide16.txt"
g add notes/wide16.txt; g commit -q -m "add wide16"; add_wide16=$(g rev-parse HEAD)
g rm -q notes/wide16.txt; g commit -q -m "remove wide16"
python3 -c 'import sys; open(sys.argv[1], "wb").write("one\nzorblax-17\n".encode("utf-32"))' "$v/notes/wide32.txt"
g add notes/wide32.txt; g commit -q -m "add wide32"; add_wide32=$(g rev-parse HEAD)
g rm -q notes/wide32.txt; g commit -q -m "remove wide32"
tw --patterns "$pats" --base "$wide_base"; rc=$?
[ "$rc" -eq 1 ] && grep -qx "$add_wide16: tripwire pattern 2 in a UTF-16 or UTF-32 file" "$tmp/out" &&
  grep -qx "$add_wide32: tripwire pattern 2 in a UTF-16 or UTF-32 file" "$tmp/out" ||
  { echo "FAIL: removed UTF-16/UTF-32 text not found in history rc=$rc"; cat "$tmp/out"; fail=1; }
if grep -q 'wide' "$tmp/out"; then echo "FAIL: a history hit printed a path"; cat "$tmp/out"; fail=1; fi
leak "UTF-16 history hit"

echo "--- a symlink's target text is scanned; the link is not followed"
ln -s "../zorblax-14/elsewhere" "$v/notes/pointer"
tw --patterns "$pats" --no-history; rc=$?
[ "$rc" -eq 1 ] && grep -qx 'notes/pointer:1: tripwire pattern 2' "$tmp/out" ||
  { echo "FAIL: symlink target not scanned rc=$rc"; cat "$tmp/out"; fail=1; }
leak "symlink target"
rm "$v/notes/pointer"

echo "--- an unreadable file fails closed (exit 2) and withholds a matching path"
if [ "$(id -u)" -eq 0 ]; then echo "SKIP: unreadable file (root reads any file)"; else
printf 'clean\n' > "$v/notes/zorblax-15.md"; chmod 000 "$v/notes/zorblax-15.md"
tw --patterns "$pats" --no-history; rc=$?
chmod 600 "$v/notes/zorblax-15.md"; rm "$v/notes/zorblax-15.md"
[ "$rc" -eq 2 ] && grep -q '(withheld path): unreadable' "$tmp/out" && ! grep -q Traceback "$tmp/out" ||
  { echo "FAIL: unreadable file rc=$rc"; cat "$tmp/out"; fail=1; }
leak "unreadable file"
fi

if [ "$fail" -eq 0 ]; then echo "PASS: tripwire"; else echo "FAIL: tripwire"; fi
exit "$fail"
