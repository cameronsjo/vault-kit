#!/usr/bin/env bash
# Exercise scripts/init-vault against scratch template-mode vaults (see copy), under a
# throwaway HOME. Each gets its own fresh git repository, so the real repository is never
# touched. It passes in the template and in an initialized instance alike.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
repo=$(pwd)
tmp=$(cd "$(mktemp -d)" && pwd -P)  # resolved, so paths match what init-vault prints
trap 'rm -rf "$tmp"' EXIT
fail=0
name=acme-work
title="Acme Work Vault"
scope="platform and data teams' shared services"
root_env=ACME_WORK_ROOT

# Resolve the pinned gitleaks once with the real HOME (its verified cache lives there), then
# hand it to every run below. Offline, a stub that finds nothing stands in and says so.
if gitleaks_bin=$(python3 scripts/gitleaks --vault-resolve 2>/dev/null); then :
elif [ "${VAULT_KIT_REQUIRE_GITLEAKS:-}" = 1 ]; then
  # CI sets this: there a missing gitleaks is a broken setup, not a reason to skip.
  echo "FAIL: pinned gitleaks unavailable and VAULT_KIT_REQUIRE_GITLEAKS=1"; exit 1
else
  echo "SKIP: pinned gitleaks unavailable; make check runs the secret scan against a stub"
  gitleaks_bin="$tmp/gitleaks-stub"; printf '#!/bin/sh\nexit 0\n' > "$gitleaks_bin"; chmod +x "$gitleaks_bin"
  export GITLEAKS_ALLOW_UNPINNED=1  # the stub reports no version
fi
mkdir -p "$tmp/home"
export HOME="$tmp/home" XDG_CACHE_HOME="$tmp/home/.cache" GITLEAKS_BIN="$gitleaks_bin"
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
g() { git -c user.name=fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false -c core.hooksPath=/dev/null "$@"; }

# copy <dir>: a template-mode vault in a fresh repo, built from the engine files in
# engine.manifest plus a synthetic seed. It never copies vault.toml, skills/ or wiki pages,
# so the test runs the same in the template and in an initialized instance (whose own
# vault.toml says template = false and would make init exit 3), and never reads vault content.
copy() {
  mkdir -p "$1"
  (cd "$repo" && { grep -v -e '^#' -e '^[[:space:]]*$' engine.manifest; printf '%s\n' .gitignore .gitleaks.toml; } |
    tr '\n' '\0' | tar --null -T - -cf -) | tar -xf - -C "$1" || return 1
  cat > "$1/vault.toml" <<'TOML'
# Synthetic template-mode vault.toml for scripts/test-init.sh.
template = true
name = ""
title = ""
scope = ""
root_env = ""

[redaction]
deny = []
TOML
  page() { printf -- '---\ntype: Fixture\ntitle: %s\ndescription: %s\nstatus: draft\n---\n# %s\n\nSynthetic fixture page.\n' "$2" "$3" "$2" > "$1"; }
  page "$1/AGENTS.md" "Fixture agents" "Synthetic agent instructions."
  ln -s AGENTS.md "$1/CLAUDE.md"
  mkdir -p "$1/wiki/capabilities"
  printf '# Update history\n\n## [2026-01-01] maintenance | Seed fixture vault\n\nActor: fixture/seed. Synthetic seed.\n' > "$1/wiki/log.md"
  page "$1/wiki/capabilities/alpha.md" "Fixture alpha" "Synthetic capability alpha."
  (cd "$1" && python3 scripts/index-vault.py >/dev/null) || return 1
  (cd "$1" && g init -q -b main . && g config user.name fixture && g config user.email fixture@example.invalid &&
    g add -A && g commit -q -m "seed from the engine files") || return 1
}
check() { make --no-print-directory -C "$1" check >"$tmp/check.log" 2>&1; }
init() { python3 "$1/scripts/init-vault" --name "$name" --title "$title" --scope "$scope"; }

echo "--- init passes make check and make check-initialized"
v="$tmp/v1"; copy "$v" || { echo "FAIL: could not copy the tree"; exit 1; }
out=$(init "$v" 2>&1); rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL: init exit $rc: $out"; fail=1; }
[ "$(tail -n 1 <<<"$out")" = "PASS: initialized $name at $v" ] || { echo "FAIL: last line is not the PASS line: $(tail -n 1 <<<"$out")"; fail=1; }
grep -q '\[redaction\] deny' <<<"$out" || { echo "FAIL: no [redaction] deny reminder"; fail=1; }
grep -q 'CODEOWNERS' <<<"$out" || { echo "FAIL: no CODEOWNERS reminder"; fail=1; }
check "$v" || { echo "FAIL: make check after init:"; cat "$tmp/check.log"; fail=1; }
make --no-print-directory -C "$v" check-initialized >/dev/null 2>&1 || { echo "FAIL: make check-initialized after init"; fail=1; }
# Finder litters .DS_Store; .gitignore excludes it, so the name check never sees it.
touch "$v/.DS_Store" "$v/wiki/.DS_Store"
check "$v" || { echo "FAIL: make check fails on an ignored .DS_Store:"; cat "$tmp/check.log"; fail=1; }
rm -f "$v/.DS_Store" "$v/wiki/.DS_Store"

# This test ships to every instance through engine.manifest, and CI runs it there, so it must
# pass inside an initialized vault too. One level deep: the nested run skips this leg.
if [ -z "${VAULT_KIT_TEST_INIT_NESTED:-}" ]; then
  echo "--- this test passes inside the initialized vault"
  VAULT_KIT_TEST_INIT_NESTED=1 bash "$v/scripts/test-init.sh" >"$tmp/nested.log" 2>&1 ||
    { echo "FAIL: scripts/test-init.sh inside an initialized vault:"; cat "$tmp/nested.log"; fail=1; }
fi

echo "--- rendered skills: no placeholder, no tripwire term, limits, identity gate"
[ -f "$v/skills/$name-discover/SKILL.md" ] && [ -f "$v/skills/$name-maintain/SKILL.md" ] &&
  [ -f "$v/skills/$name-maintain/references/operation-checklist.md" ] || { echo "FAIL: a rendered skill file is missing"; fail=1; }
if grep -rn '{{' "$v/skills"; then echo "FAIL: placeholder left under skills/"; fail=1; fi
# The private-name list is never committed: scripts/tripwire reads it from VAULT_KIT_TRIPWIRE
# (an Actions secret in the template's CI) and prints only pattern numbers.
if [ -n "${VAULT_KIT_TRIPWIRE:-}" ]; then
  (cd "$v" && python3 scripts/tripwire --no-history) || { echo "FAIL: tripwire hit in the initialized tree"; fail=1; }
else
  echo "SKIP: tripwire over the rendered skills (VAULT_KIT_TRIPWIRE is not set)"
fi
python3 - "$v" <<'PY' || fail=1
import sys, yaml
from pathlib import Path
for path in sorted(Path(sys.argv[1], "skills").glob("*/SKILL.md")):
    front = yaml.safe_load(path.read_text().split("\n---\n", 1)[0][4:])
    size = len(front["description"])
    if not 0 < size <= 1024:
        print(f"FAIL: {path.parent.name} description is {size} characters")
        sys.exit(1)
    if front.get("license") != "Apache-2.0":
        print(f"FAIL: {path.parent.name} license is {front.get('license')!r}")
        sys.exit(1)
PY
discover="$v/skills/$name-discover/SKILL.md"
for needle in "root=\"\${$root_env}\"" "test -f \"\$root/skills/$name-discover/SKILL.md\"" \
    "reply exactly \`$title is not reachable at <root>\`" "page says: \"" \
    "Runs <root>/scripts/qmd, which is vault-owned code, from the tree $root_env names" \
    "Generated from templates/skills/discover/skill.md.tmpl by scripts/init-vault --render-skills; do not edit"; do
  grep -qF -- "$needle" "$discover" || { echo "FAIL: discover skill lacks: $needle"; fail=1; }
done
if grep -q 'HOME/' "$discover"; then echo "FAIL: discover skill guesses a default path under HOME"; fail=1; fi
grep -qF 'make check` runs the mechanical scan' "$v/skills/$name-maintain/SKILL.md" ||
  { echo "FAIL: maintain skill lacks the redaction checklist hand-off to make check"; fail=1; }

echo "--- a hand edit to a rendered skill fails make check; --render-skills repairs it"
printf '\nextra line\n' >> "$discover"
check "$v" && { echo "FAIL: make check passed with an edited skill"; fail=1; }
grep -qF "skills/$name-discover/SKILL.md differs from templates/; run scripts/init-vault --render-skills" "$tmp/check.log" ||
  { echo "FAIL: drift message missing:"; cat "$tmp/check.log"; fail=1; }
python3 "$v/scripts/init-vault" --render-skills >/dev/null || { echo "FAIL: --render-skills exit $?"; fail=1; }
check "$v" || { echo "FAIL: make check after --render-skills:"; cat "$tmp/check.log"; fail=1; }
out=$(python3 "$v/scripts/init-vault" --render-skills); grep -q '(0 change(s))' <<<"$out" || { echo "FAIL: --render-skills not idempotent: $out"; fail=1; }

echo "--- second run exits 3"
init "$v" >/dev/null 2>&1; rc=$?
[ "$rc" -eq 3 ] || { echo "FAIL: second init exit $rc, want 3"; fail=1; }

echo "--- a run stopped after rendering resumes and completes; the deny table survives"
v="$tmp/v2"; copy "$v" || exit 1
python3 - "$v/vault.toml" <<'PY'
import sys
path = sys.argv[1]
text = open(path).read()
open(path, "w").write(text.replace("deny = []", "deny = ['\\bzzqq-fixture\\b']"))
PY
before=$(sed -n '/^\[redaction\]/,$p' "$v/vault.toml")
VAULT_KIT_INIT_FAIL_AFTER=render init "$v" >/dev/null 2>&1; rc=$?
[ "$rc" -eq 1 ] || { echo "FAIL: interrupted init exit $rc, want 1"; fail=1; }
grep -q '^template = true' "$v/vault.toml" || { echo "FAIL: vault.toml was written before the run finished"; fail=1; }
[ -f "$v/skills/$name-discover/SKILL.md" ] || { echo "FAIL: the interrupted run did not render"; fail=1; }
out=$(init "$v" 2>&1); rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL: resumed init exit $rc: $out"; fail=1; }
grep -q 'resuming a partial init of acme-work; missing: log entry, indexes regenerated, vault.toml written' <<<"$out" ||
  { echo "FAIL: resume did not name the missing pieces: $out"; fail=1; }
check "$v" || { echo "FAIL: make check after resume:"; cat "$tmp/check.log"; fail=1; }
[ "$(sed -n '/^\[redaction\]/,$p' "$v/vault.toml")" = "$before" ] || { echo "FAIL: [redaction] table changed"; fail=1; }

echo "--- a run stopped after the log entry resumes without a second entry"
v="$tmp/v3"; copy "$v" || exit 1
VAULT_KIT_INIT_FAIL_AFTER=log init "$v" >/dev/null 2>&1
init "$v" >/dev/null 2>&1 || { echo "FAIL: resume after log exit $?"; fail=1; }
count=$(grep -c "Initialize $name from vault-kit" "$v/wiki/log.md")
[ "$count" -eq 1 ] || { echo "FAIL: $count Initialize log entries, want 1"; fail=1; }
check "$v" || { echo "FAIL: make check after resume:"; cat "$tmp/check.log"; fail=1; }

echo "--- writers refuse a committed symlink; make check rejects one under wiki/"
v="$tmp/v5"; copy "$v" || exit 1
printf 'outside the vault\n' > "$tmp/outside.txt"; cp "$tmp/outside.txt" "$tmp/outside.keep"
index="$v/wiki/capabilities/index.md"; cp "$index" "$tmp/index.keep"
rm "$index"; ln -s "$tmp/outside.txt" "$index"
out=$(python3 "$v/scripts/index-vault.py" 2>&1); rc=$?
[ "$rc" -ne 0 ] && grep -qF 'refusing to write through the symlink wiki/capabilities/index.md' <<<"$out" ||
  { echo "FAIL: index-vault through a symlinked index exit $rc: $out"; fail=1; }
cmp -s "$tmp/outside.txt" "$tmp/outside.keep" || { echo "FAIL: index-vault wrote through a symlinked index.md"; fail=1; }
check "$v" && { echo "FAIL: make check passed with a symlink under wiki/"; fail=1; }
grep -qF 'wiki/capabilities/index.md: symlinks are not allowed' "$tmp/check.log" ||
  { echo "FAIL: symlink under wiki/ not named:"; cat "$tmp/check.log"; fail=1; }
rm "$index"; cp "$tmp/index.keep" "$index"
log="$v/wiki/log.md"; mv "$log" "$tmp/outside-log.md"; cp "$tmp/outside-log.md" "$tmp/outside-log.keep"
ln -s "$tmp/outside-log.md" "$log"
out=$(init "$v" 2>&1); rc=$?
[ "$rc" -ne 0 ] && grep -qF 'refusing to write through the symlink wiki/log.md' <<<"$out" ||
  { echo "FAIL: init through a symlinked wiki/log.md exit $rc: $out"; fail=1; }
cmp -s "$tmp/outside-log.md" "$tmp/outside-log.keep" || { echo "FAIL: init appended through a symlinked wiki/log.md"; fail=1; }
[ ! -e "$v/skills" ] || { echo "FAIL: init rendered skills before refusing the symlinked log"; fail=1; }
rm "$log"; mv "$tmp/outside-log.md" "$log"
mkdir -p "$tmp/skills-outside/$name-discover"; printf 'keep\n' > "$tmp/skills-outside/$name-discover/keep.txt"
ln -s "$tmp/skills-outside" "$v/skills"
out=$(init "$v" 2>&1); rc=$?
[ "$rc" -ne 0 ] && grep -qF 'refusing to write through the symlink skills' <<<"$out" ||
  { echo "FAIL: init through a symlinked skills/ exit $rc: $out"; fail=1; }
[ -f "$tmp/skills-outside/$name-discover/keep.txt" ] || { echo "FAIL: init deleted a file through a symlinked skills/"; fail=1; }
[ ! -e "$tmp/skills-outside/$name-discover/SKILL.md" ] || { echo "FAIL: init wrote a skill through a symlinked skills/"; fail=1; }
grep -q '^template = true' "$v/vault.toml" || { echo "FAIL: a refused init wrote vault.toml"; fail=1; }

echo "--- bad values exit 2 and name the rule and the value"
v="$tmp/v4"; copy "$v" || exit 1
err=$(python3 "$v/scripts/init-vault" --name Bad_Slug --title "$title" --scope "$scope" 2>&1 >/dev/null); rc=$?
[ "$rc" -eq 2 ] || { echo "FAIL: bad slug exit $rc"; fail=1; }
grep -qF "'Bad_Slug'" <<<"$err" && grep -qF '^[a-z][a-z0-9]*(-[a-z0-9]+)*$' <<<"$err" || { echo "FAIL: bad slug message: $err"; fail=1; }
python3 "$v/scripts/init-vault" --name "a$(printf 'b%.0s' {1..31})" --title "$title" --scope "$scope" >/dev/null 2>&1
[ "$?" -eq 2 ] || { echo "FAIL: a 32-character slug was accepted"; fail=1; }
python3 "$v/scripts/init-vault" --name "$name" --title 'Bad "quoted" title' --scope "$scope" >/dev/null 2>&1
[ "$?" -eq 2 ] || { echo "FAIL: a title with a double quote was accepted"; fail=1; }
# Invisible fillers pass str.isprintable(); only printable ASCII and Latin-1 letters are allowed.
for filler in '\343\205\244' '\342\240\200' '\341\205\237'; do  # U+3164, U+2800, U+115F as UTF-8
  err=$(python3 "$v/scripts/init-vault" --name "$name" --title "Hidden$(printf "$filler")filler" --scope "$scope" 2>&1 >/dev/null); rc=$?
  [ "$rc" -eq 2 ] && grep -q 'contains U+' <<<"$err" || { echo "FAIL: an invisible filler in the title was accepted (rc=$rc): $err"; fail=1; }
done
python3 - "$v/scripts" <<'PY' || { echo "FAIL: a Latin-1 letter in the title was refused"; fail=1; }
import sys
sys.path.insert(0, sys.argv[1])
import vaultconf
errors = vaultconf.identity_errors({"name": "acme-work", "title": "Café Århus Vault",
                                    "scope": "shared services", "root_env": "ACME_WORK_ROOT"})
sys.exit(1 if errors else 0)
PY
python3 "$v/scripts/init-vault" --name "$name" --title "$title" >/dev/null 2>&1
[ "$?" -eq 2 ] || { echo "FAIL: missing --scope was accepted"; fail=1; }
python3 "$v/scripts/init-vault" --render-skills >/dev/null 2>&1
[ "$?" -eq 2 ] || { echo "FAIL: --render-skills ran on the uninitialized template"; fail=1; }
[ ! -e "$v/skills" ] || { echo "FAIL: a refused run wrote skills/"; fail=1; }
grep -q '^template = true' "$v/vault.toml" || { echo "FAIL: a refused run wrote vault.toml"; fail=1; }

echo "--- an index with nothing to list passes git diff --check (the hook's first step)"
v="$tmp/v-empty"; copy "$v" || { echo "FAIL: could not copy the tree"; exit 1; }
mkdir -p "$v/wiki/journeys"; printf '# journeys\n' > "$v/wiki/journeys/index.md"
(cd "$v" && python3 scripts/index-vault.py >/dev/null && g add -A && g diff --cached --check) >"$tmp/out" 2>&1 ||
  { echo "FAIL: a generated empty index fails git diff --check:"; cat "$tmp/out"; fail=1; }

if [ "$fail" -eq 0 ]; then echo "PASS: init-vault init/resume/re-render/refusals"; else echo "FAIL: init-vault"; fi
exit "$fail"
