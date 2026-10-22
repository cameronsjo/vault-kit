#!/usr/bin/env bash
# Exercise scripts/engine-update against a local fixture "vault-kit" source repo and a
# throwaway vault, both under a temp dir. No network. Tags in the source:
#   v0.0.1  changed engine file, new engine file, a vault-owned file left alone
#   v0.0.2  manifest line "../outside.txt" (traversal)
#   v0.0.3  manifest line "/tmp/..." (absolute)
#   v0.0.4  manifest path through a symlinked directory
#   v0.0.5  manifest lists vault.toml (vault-owned)
#   v0.0.6  WIKI/log.md, v0.0.7 Agents.md: vault-owned paths in another case
#   v0.0.8  .claude/settings.json: outside every engine location
#   v0.0.9  Scripts/engine-fixture.txt: an engine location spelled in another case
#   v0.0.10 Vale config inside the allowlist; v0.0.11-v0.0.20 and v0.0.26-v0.0.32 each break one
#           allowlist rule; v0.0.21-v0.0.25 and v0.0.33-v0.0.35 ship files the review would not see
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
repo=$(pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
src="$tmp/src"
vault="$tmp/work/vault"
fail=0
g() { git -c user.name=fixture -c user.email=fixture@example.invalid -c commit.gpgsign=false -c core.hooksPath=/dev/null "$@"; }

# --- fixture source repo
mkdir -p "$src/scripts" && cd "$src" || exit 1
g init -q -b main .
printf 'engine v1\n' > scripts/engine-fixture.txt
printf 'scripts/engine-fixture.txt\n' > engine.manifest
g add -A && g commit -q -m base
printf 'engine v2\n' > scripts/engine-fixture.txt
printf 'new engine file\n' > scripts/engine-added.txt
printf 'THIS MUST NOT LAND\n' > not-in-manifest.txt
printf 'name = "stolen"\n' > vault.toml
printf 'scripts/engine-fixture.txt\nscripts/engine-added.txt\n' > engine.manifest
g add -A && g commit -q -m v1 && g tag -a -m v0.0.1 v0.0.1
tag_manifest() { # tag, manifest text
  printf '%b' "$2" > engine.manifest; g commit -qam "$1" && g tag -a -m "$1" "$1"
}
tag_manifest v0.0.2 'scripts/engine-fixture.txt\n../outside.txt\n'
tag_manifest v0.0.3 "scripts/engine-fixture.txt\n$tmp/absolute.txt\n"
mkdir -p real && printf 'x\n' > real/file.txt && ln -s ../real scripts/linked
g add -A && tag_manifest v0.0.4 'scripts/engine-fixture.txt\nscripts/linked/file.txt\n'
tag_manifest v0.0.5 'scripts/engine-fixture.txt\nvault.toml\n'
# Each refused path exists in its tag, so only the location check stands between it and the vault.
mkdir -p WIKI .claude && printf 'REWRITTEN LOG\n' > WIKI/log.md && printf 'REWRITTEN AGENTS\n' > Agents.md
printf '{"hooks": "planted"}\n' > .claude/settings.json && g add -A
tag_manifest v0.0.6 'scripts/engine-fixture.txt\nWIKI/log.md\n'
tag_manifest v0.0.7 'scripts/engine-fixture.txt\nAgents.md\n'
tag_manifest v0.0.8 'scripts/engine-fixture.txt\n.claude/settings.json\n'
tag_manifest v0.0.9 'Scripts/engine-fixture.txt\n'
# Vale config: v0.0.10 is inside the allowlist; every later vale tag breaks one rule of it.
good_ini='StylesPath = .vale/styles\nMinAlertLevel = suggestion\n\n[*.md]\nBasedOnStyles = vaultkit\nvaultkit.filler = NO\n'
vale_manifest='.vale.ini\n.vale/styles/vaultkit/hedging.yml\n'
mkdir -p .vale/styles/vaultkit .vale/styles/config && printf '%b' "$good_ini" > .vale.ini
printf 'extends: existence\nmessage: hedge\nlevel: warning\ntokens: [probably]\n' > .vale/styles/vaultkit/hedging.yml
printf 'x\n' > .vale/other.yml && printf 'x\n' > .vale/styles/config/x.txt && cp .vale.ini scripts/.vale.ini
g add -A && tag_manifest v0.0.10 "$vale_manifest"
tag_manifest v0.0.11 '.vale/other.yml\n'
tag_manifest v0.0.12 '.vale/styles/config/x.txt\n'
tag_manifest v0.0.13 'scripts/.vale.ini\n'
tag_ini() { # tag, .vale.ini text
  printf '%b' "$2" > .vale.ini; tag_manifest "$1" "$vale_manifest"
}
tag_ini v0.0.14 "Packages = Google\n$good_ini"
tag_ini v0.0.15 "$good_ini\n[formats]\nmdx = md\n"
tag_ini v0.0.16 "Transform = x.xsl\n$good_ini"
tag_ini v0.0.17 'StylesPath = /etc\n\n[*.md]\nBasedOnStyles = vaultkit\n'
tag_ini v0.0.18 'StylesPath = ../styles\n\n[*.md]\nBasedOnStyles = vaultkit\n'
tag_ini v0.0.19 'StylesPath = .vale/styles\nStylesPath = .vale/styles\n'
printf '%b' "$good_ini" > .vale.ini
printf 'extends: script\nmessage: x\nscript: x\n' > .vale/styles/vaultkit/hedging.yml
tag_manifest v0.0.20 "$vale_manifest"
# Files the review would not see: bytecode, git ignore/attributes files, a path the vault ignores.
mkdir -p scripts/__pycache__ && printf 'bytecode\n' > scripts/__pycache__/vaultconf.cpython-312.pyc
printf 'bytecode\n' > scripts/loose.pyc && printf '*.txt\n' > scripts/.gitignore
printf '* -diff\n' > scripts/.gitattributes && printf 'hidden\n' > scripts/run.log && g add -Af
tag_manifest v0.0.21 'scripts/__pycache__/vaultconf.cpython-312.pyc\n'
tag_manifest v0.0.22 'scripts/loose.pyc\n'
tag_manifest v0.0.23 'scripts/.gitignore\n'
tag_manifest v0.0.24 'scripts/.gitattributes\n'
tag_manifest v0.0.25 'scripts/run.log\n'
# Shapes where Python and Vale's Go INI parser would read .vale.ini differently, and other ways
# around the Vale allowlist found in review.
tag_ini v0.0.26 "$good_ini""TokenIgnores = x\n  [DEFAULT]\n  NLPEndpoint = https://example.invalid/\n  [formats]\n  md = xml\n"
tag_ini v0.0.27 '[DEFAULT]\nStylesPath = scripts\n'
tag_ini v0.0.28 'StylesPath = .vale/styles\n\n[*.md]\nTokenIgnores = """\nx\n"""\n'
tag_ini v0.0.29 'StylesPath = .vale/styles\n\n[*.md]\nVale.Spelling = YES\n'
tag_ini v0.0.30 'StylesPath = .vale/styles \\\n'
printf '%b' "$good_ini" > .vale.ini && printf 'StylesPath = /etc\n' > scripts/_vale
printf '<xsl:stylesheet/>\n' > .vale/styles/vaultkit/x.xsl && printf 'ELF\0binary\n' > scripts/mod.cpython-312-darwin.so
printf '#!/bin/sh\necho ok\033[1A\033[2K\n' > scripts/redraw.sh && printf 'a\0b\n' > scripts/blob.txt && g add -Af
tag_manifest v0.0.31 'scripts/_vale\n'
tag_manifest v0.0.32 '.vale.ini\n.vale/styles/vaultkit/x.xsl\n'
tag_manifest v0.0.33 'scripts/mod.cpython-312-darwin.so\n'
tag_manifest v0.0.34 'scripts/redraw.sh\n'
tag_manifest v0.0.35 'scripts/blob.txt\n'
v1_commit=$(g rev-parse 'v0.0.1^{commit}')

# --- fixture vault: a git repo with the real script and a stub `make check`
mkdir -p "$vault/scripts" "$vault/wiki" && cd "$vault" || exit 1
cp "$repo/scripts/engine-update" "$repo/scripts/vaultconf.py" scripts/
printf 'template = false\nname = "fixture"\ntitle = "Fixture"\nscope = "tests"\nroot_env = ""\n\n[redaction]\ndeny = []\n' > vault.toml
printf 'check:\n\t@echo FIXTURE-MAKE-CHECK-RAN\n' > Makefile
printf 'engine v0\n' > scripts/engine-fixture.txt
printf 'my own page\n' > wiki/page.md
printf '# Log\n' > wiki/log.md
printf '# My agents\n' > AGENTS.md
printf '*.log\n' > .gitignore
g init -q -b main . && g add -A && g commit -q -m vault
run() { python3 scripts/engine-update "$@"; }
expect() { # label, wanted, got
  [ "$2" = "$3" ] || { echo "FAIL: $1: wanted $2, got $3"; fail=1; }
}

echo "--- missing --ref is a usage error"
run >/dev/null 2>&1; expect "no --ref exit" 2 $?

echo "--- dirty tree is refused and named"
printf 'scratch\n' > wiki/untracked.md
err=$(run --ref v0.0.1 --source "$src" 2>&1 >/dev/null); expect "dirty exit" 2 $?
grep -q 'wiki/untracked.md' <<<"$err" || { echo "FAIL: dirty refusal did not name wiki/untracked.md: $err"; fail=1; }
expect "engine file untouched when dirty" "engine v0" "$(cat scripts/engine-fixture.txt)"
rm wiki/untracked.md

echo "--- --commit must be a full id and must match what the ref resolves to"
err=$(run --ref v0.0.1 --commit abc123 --source "$src" 2>&1 >/dev/null); expect "short --commit exit" 2 $?
grep -q 'full lowercase commit id' <<<"$err" || { echo "FAIL: short --commit not explained: $err"; fail=1; }
other=$(g -C "$src" rev-parse 'v0.0.2^{commit}')
err=$(run --ref v0.0.1 --commit "$other" --source "$src" 2>&1 >/dev/null); expect "moved ref exit" 2 $?
grep -qF "resolves to $v1_commit, not --commit $other" <<<"$err" || { echo "FAIL: --commit mismatch not named: $err"; fail=1; }
expect "engine file untouched on a --commit mismatch" "engine v0" "$(cat scripts/engine-fixture.txt)"

echo "--- clean tree: manifest files copied, others untouched, nothing run from the ref"
out=$(run --ref v0.0.1 --commit "$v1_commit" --source "$src" 2>&1); expect "update exit" 0 $?
expect "changed engine file" "engine v2" "$(cat scripts/engine-fixture.txt)"
expect "added engine file" "new engine file" "$(cat scripts/engine-added.txt)"
grep -q 'updated scripts/engine-fixture.txt' <<<"$out" || { echo "FAIL: changed path not printed: $out"; fail=1; }
grep -q 'added scripts/engine-added.txt' <<<"$out" || { echo "FAIL: added path not printed: $out"; fail=1; }
if grep -q 'FIXTURE-MAKE-CHECK-RAN' <<<"$out"; then echo "FAIL: engine-update ran make check from the fetched ref"; fail=1; fi
grep -qF 'run `make render-skills && make check`' <<<"$out" || { echo "FAIL: no review instruction: $out"; fail=1; }
grep -qF 'runs the fetched hooks' <<<"$out" || { echo "FAIL: closing message does not warn that the hooks go live: $out"; fail=1; }
# An added file is untracked, so git diff never shows it; engine-update prints its content.
grep -qF '+new engine file' <<<"$out" || { echo "FAIL: added file content not shown: $out"; fail=1; }
grep -q 'scripts/engine-fixture.txt' <<<"$(sed -n '/engine files changed/,$p' <<<"$out")" || { echo "FAIL: diff stat not printed: $out"; fail=1; }
[ ! -e not-in-manifest.txt ] || { echo "FAIL: non-manifest file was copied"; fail=1; }
expect "vault.toml untouched" 'name = "fixture"' "$(grep '^name' vault.toml)"
expect "vault page untouched" "my own page" "$(cat wiki/page.md)"
g add -A && g commit -q -m updated

echo "--- unsafe manifests are refused before anything is copied"
printf 'engine v3-local\n' > scripts/engine-fixture.txt && g commit -qam local
for case in "v0.0.2:contains .\.\.." "v0.0.3:absolute or home path" "v0.0.4:symlink component in the source" "v0.0.5:vault-owned" \
    "v0.0.6:WIKI/log.md is vault-owned" "v0.0.7:Agents.md is vault-owned" "v0.0.8:not an engine location" "v0.0.9:differs in case"; do
  tag=${case%%:*}; word=${case#*:}
  err=$(run --ref "$tag" --source "$src" 2>&1 >/dev/null); expect "$tag exit" 2 $?
  grep -qE "$word" <<<"$err" || { echo "FAIL: $tag refusal does not mention '$word': $err"; fail=1; }
  expect "$tag copied nothing" "engine v3-local" "$(cat scripts/engine-fixture.txt)"
done
[ ! -e "$tmp/work/outside.txt" ] && [ ! -e "$tmp/absolute.txt" ] || { echo "FAIL: a refused path was written"; fail=1; }
expect "wiki/log.md untouched by a WIKI/log.md entry" "# Log" "$(cat wiki/log.md)"
expect "AGENTS.md untouched by an Agents.md entry" "# My agents" "$(cat AGENTS.md)"
[ ! -e .claude ] || { echo "FAIL: a manifest wrote .claude/"; fail=1; }

echo "--- Vale config inside the allowlist is copied"
run --ref v0.0.10 --source "$src" >/dev/null 2>&1; expect "v0.0.10 exit" 0 $?
grep -q 'BasedOnStyles = vaultkit' .vale.ini && [ -f .vale/styles/vaultkit/hedging.yml ] ||
  { echo "FAIL: allowed Vale config was not copied"; fail=1; }
g add -A && g commit -q -m vale
good=$(cat .vale.ini)

echo "--- Vale config outside the allowlist is refused before anything is copied"
for case in "v0.0.11:not an engine location" "v0.0.12:not an engine location" "v0.0.13:Vale reads this name" \
    "v0.0.14:top-level key packages" "v0.0.15:section \[formats\]" "v0.0.16:top-level key transform" \
    "v0.0.17:StylesPath must be" "v0.0.18:StylesPath must be" "v0.0.19:set twice" \
    "v0.0.20:extends 'script'" "v0.0.26:is indented" "v0.0.27:\\[DEFAULT\\] is not allowed" \
    "v0.0.28:quoted or multi-line value" "v0.0.29:vale.spelling is not a rule" "v0.0.30:line continuation" \
    "v0.0.31:Vale reads this name" "v0.0.32:only rule files"; do
  tag=${case%%:*}; word=${case#*:}
  err=$(run --ref "$tag" --source "$src" 2>&1 >/dev/null); expect "$tag exit" 2 $?
  grep -qE "$word" <<<"$err" || { echo "FAIL: $tag refusal does not mention '$word': $err"; fail=1; }
  expect "$tag left .vale.ini alone" "$good" "$(cat .vale.ini)"
  grep -q 'extends: existence' .vale/styles/vaultkit/hedging.yml || { echo "FAIL: $tag rewrote the rule"; fail=1; }
done
[ ! -e scripts/.vale.ini ] && [ ! -e .vale/other.yml ] && [ ! -e .vale/styles/config ] ||
  { echo "FAIL: a refused Vale path was written"; fail=1; }

echo "--- files the review would not see are refused before anything is copied"
for case in "v0.0.21:hidden from the review" "v0.0.22:hidden from the review" "v0.0.23:hidden from the review" \
    "v0.0.24:hidden from the review" "v0.0.25:hidden from the review" "v0.0.33:hidden from the review" \
    "v0.0.34:control bytes" "v0.0.35:control bytes"; do
  tag=${case%%:*}; word=${case#*:}
  err=$(run --ref "$tag" --source "$src" 2>&1 >/dev/null); expect "$tag exit" 2 $?
  grep -q "$word" <<<"$err" || { echo "FAIL: $tag refusal does not mention '$word': $err"; fail=1; }
done
[ ! -e scripts/__pycache__ ] && [ ! -e scripts/loose.pyc ] && [ ! -e scripts/.gitignore ] \
  && [ ! -e scripts/.gitattributes ] && [ ! -e scripts/run.log ] && [ ! -e scripts/mod.cpython-312-darwin.so ] \
  && [ ! -e scripts/redraw.sh ] && [ ! -e scripts/blob.txt ] && [ ! -e scripts/_vale ] \
  && [ ! -e .vale/styles/vaultkit/x.xsl ] || { echo "FAIL: a hidden file was written"; fail=1; }

echo "--- this repository's own engine.manifest stays inside the engine locations"
python3 - "$repo" <<'PY' || { echo "FAIL: engine.manifest lists a path engine-update would refuse"; fail=1; }
import importlib.machinery, importlib.util, sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root / "scripts"))
loader = importlib.machinery.SourceFileLoader("engine_update", str(root / "scripts/engine-update"))
module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(module)
for number, line in enumerate((root / "engine.manifest").read_text().splitlines(), 1):
    if line.strip() and not line.startswith("#"):
        module.check_location(line.strip(), f"engine.manifest line {number}")
PY

echo "--- unknown ref exits 3"
run --ref v9.9.9 --source "$src" >/dev/null 2>&1; expect "bad ref exit" 3 $?

[ "$fail" -eq 0 ] && echo "PASS: engine-update cases" || { echo "FAIL: engine-update"; exit 1; }
