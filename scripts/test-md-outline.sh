#!/usr/bin/env bash
# Exercise scripts/md-outline on synthetic Markdown fixtures.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
repo=$(pwd)
tmp=$(cd "$(mktemp -d)" && pwd -P)
trap 'rm -rf "$tmp"' EXIT
fail=0
export PYTHONDONTWRITEBYTECODE=1
# Output columns are padded; compare with runs of spaces squeezed and leading ones dropped.
mo() { python3 "$repo/scripts/md-outline" "$@" 2>&1 | sed 's/^ *//; s/  */ /g' >"$tmp/out"; return "${PIPESTATUS[0]}"; }
expect() { # description, exact line the output must contain
  grep -qxF -- "$2" "$tmp/out" || { echo "FAIL: $1: missing line: $2"; cat "$tmp/out"; fail=1; }
}
absent() { # description, text the output must not contain
  if grep -qF -- "$2" "$tmp/out"; then echo "FAIL: $1: unexpected: $2"; cat "$tmp/out"; fail=1; fi
}

f="$tmp/page.md"
cat > "$f" <<'MD'
---
title: '# not a heading'
---
# Top

intro

## First

```sh
# not a heading either
```

### C# notes ##

Setext two
----------

#hashtag is not a heading

~~~~
## fenced with tildes
~~~~

Closing hashes ##
MD

echo "--- frontmatter is skipped and reported; sections nest and span to the next peer"
mo "$f"; rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL: rc=$rc"; cat "$tmp/out"; fail=1; }
expect "summary" "$f: 25 lines, $(wc -c < "$f" | tr -d ' ') bytes; frontmatter lines 1-3 skipped"
expect "h1 spans to end" "4-25 $(sed -n '4,25p' "$f" | wc -c | tr -d ' ') # Top"
expect "h2 spans to the setext h2" "8-15 $(sed -n '8,15p' "$f" | wc -c | tr -d ' ') ## First"
expect "a closing sequence is dropped, an inner hash kept" "14-15 $(sed -n '14,15p' "$f" | wc -c | tr -d ' ') ### C# notes"
expect "setext h2" "16-25 $(sed -n '16,25p' "$f" | wc -c | tr -d ' ') ## Setext two"
absent "frontmatter title" "not a heading'"
absent "backtick fence" "not a heading either"
absent "tilde fence" "fenced with tildes"
absent "hashtag" "hashtag"

echo "--- --json carries the same sections"
python3 "$repo/scripts/md-outline" "$f" --json >"$tmp/out"
python3 - "$tmp/out" <<'PY' || fail=1
import json, sys
data = json.load(open(sys.argv[1]))
got = [(s["level"], s["title"], s["first"], s["last"]) for s in data["sections"]]
want = [(1, "Top", 4, 25), (2, "First", 8, 15), (3, "C# notes", 14, 15), (2, "Setext two", 16, 25)]
assert data["frontmatter"] == [1, 3], data["frontmatter"]
assert got == want, got
PY

echo "--- a thematic break after a blank line is not a heading"
printf 'para\n\n---\n\ntext\n' > "$tmp/hr.md"
mo "$tmp/hr.md"
expect "no headings" "no headings"

echo "--- no frontmatter, CRLF line endings"
printf '# A\r\nbody\r\n# B\r\n' > "$tmp/crlf.md"
mo "$tmp/crlf.md"
expect "crlf first" "1-2 11 # A"
expect "crlf second" "3-3 5 # B"
absent "crlf summary" "frontmatter"

echo "--- bad arguments and unreadable input exit 2"
mo; [ $? -eq 2 ] || { echo "FAIL: no argument"; fail=1; }
mo "$tmp/missing.md"; [ $? -eq 2 ] || { echo "FAIL: missing file"; fail=1; }
printf '\xff\xfe\x00bad' > "$tmp/bin.md"
mo "$tmp/bin.md"; [ $? -eq 2 ] || { echo "FAIL: non-UTF-8 file"; fail=1; }

[ "$fail" -eq 0 ] && echo "PASS: md-outline"
exit "$fail"
