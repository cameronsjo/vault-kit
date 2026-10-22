#!/usr/bin/env bash
# Exercise make prose (scripts/prose) over a throwaway fixture vault: a git repo holding the
# real scripts, Makefile, .vale.ini and vaultkit style, and pages that each trip one rule.
# Every case goes through `make prose`, the entry point the maintain skill and CI use. The
# genuine-Vale cases use the normal cache; offline they print SKIP, unless
# VAULT_KIT_REQUIRE_VALE=1 (CI), which makes them failures.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
repo=$(pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
fail=0
vault="$tmp/vault"
mkdir -p "$vault/scripts" "$vault/wiki/a/b" "$vault/raw" "$vault/.vale/styles"
cp scripts/prose scripts/vale scripts/pinnedbin.py scripts/vaultconf.py scripts/venv-python "$vault/scripts/"
cp -R .vale/styles/vaultkit "$vault/.vale/styles/" && cp .vale.ini Makefile "$vault/"
long="This sentence keeps going and going with one clause after another clause after yet another clause"
long="$long so that by the time the reader reaches the end of it they have lost the start of it entirely."
printf -- '---\ntitle: Deep\n---\n# Deep\n\nThe sync should work after a restart.\n' > "$vault/wiki/a/b/deep.md"
printf -- '# Filler\n\nIt is basically done.\n' > "$vault/wiki/filler.md"
printf -- '# Long\n\n%s\n' "$long" > "$vault/wiki/long.md"
printf -- '---\ntitle: Clean\ndescription: A plain page.\n---\n# Clean\n\nSee [[in order to basically]]. Do not store credentials.\n' > "$vault/wiki/clean.md"
printf -- '# Raw\n\nIt is basically a capture that should work.\n' > "$vault/raw/capture.md"
printf -- '# Log\n\nBasically, this should work.\n' > "$vault/wiki/log.md"
git -C "$vault" init -q -b main && git -C "$vault" add -A
prose() { (cd "$vault" && env -u VALE_BIN make --no-print-directory -s prose PYTHON=python3 "$@"); }

out=$(prose 2>"$tmp/err"); rc=$?
if grep -q 'skipped, Vale is unavailable' "$tmp/err" && [ "${VAULT_KIT_REQUIRE_VALE:-}" != "1" ]; then
  echo "SKIP: Vale could not be downloaded (offline?); the genuine-Vale cases did not run"
else
  echo "--- the default list lints wiki/ at any depth and leaves raw/ and wiki/log.md alone"
  [ "$rc" -eq 0 ] || { echo "FAIL: make prose exit $rc: $(cat "$tmp/err")"; fail=1; }
  records=$(grep -c ':vaultkit\.' <<<"$out")
  [ "$records" -eq 3 ] || { echo "FAIL: wanted 3 records, got $records: $out"; fail=1; }
  grep -q '^wiki/a/b/deep.md:6:[0-9]*:vaultkit.unproven:' <<<"$out" || { echo "FAIL: deep page not linted: $out"; fail=1; }
  grep -q '^wiki/filler.md:3:[0-9]*:vaultkit.filler:' <<<"$out" || { echo "FAIL: filler not reported: $out"; fail=1; }
  grep -q '^wiki/long.md:3:[0-9]*:vaultkit.sentence-length:' <<<"$out" || { echo "FAIL: long sentence not reported: $out"; fail=1; }
  if grep -qE '^(raw/|wiki/log.md|wiki/clean.md)' <<<"$out"; then echo "FAIL: linted a page it must leave alone: $out"; fail=1; fi
  grep -qx '3 alerts in 4 files' <<<"$out" || { echo "FAIL: no count line: $out"; fail=1; }

  echo "--- FILES= narrows the run, with the same exclusions"
  out=$(prose FILES="wiki/filler.md wiki/clean.md" 2>/dev/null)
  grep -qx '1 alerts in 2 files' <<<"$out" || { echo "FAIL: FILES= did not narrow: $out"; fail=1; }
  for never in raw/capture.md wiki/log.md; do
    out=$(prose FILES="$never" 2>/dev/null)
    grep -qx '0 alerts in 0 files' <<<"$out" || { echo "FAIL: FILES=$never was linted: $out"; fail=1; }
  done
  out=$(prose FILES=wiki/missing.md 2>&1)
  grep -q 'wiki/missing.md does not exist' <<<"$out" && grep -qx '0 alerts in 0 files' <<<"$out" ||
    { echo "FAIL: a missing file was not dropped with a note: $out"; fail=1; }

  echo "--- every vaultkit rule fires in its own test cases (vale test --coverage)"
  vale_bin=$(env -u VALE_BIN python3 scripts/vale --vault-resolve 2>/dev/null)
  (cd "$vault" && "$vale_bin" test --coverage .vale/styles/vaultkit) > "$tmp/test.out" 2>&1 ||
    { echo "FAIL: vale test --coverage: $(cat "$tmp/test.out")"; fail=1; }
fi

echo "--- an unavailable Vale is skipped, unless VAULT_KIT_REQUIRE_VALE=1; tampering always fails"
mkdir -p "$tmp/cache" "$tmp/mirror" && chmod 755 "$tmp/cache"
offline() { XDG_CACHE_HOME="$tmp/cache" VALE_DOWNLOAD_BASE="file://$tmp/$1" prose "${@:2}"; }
err=$(offline nowhere 2>&1 >/dev/null); rc=$?
[ "$rc" -eq 0 ] && grep -q 'skipped, Vale is unavailable' <<<"$err" || { echo "FAIL: unavailable Vale (rc=$rc): $err"; fail=1; }
err=$(VAULT_KIT_REQUIRE_VALE=1 offline nowhere 2>&1 >/dev/null); rc=$?
[ "$rc" -ne 0 ] || { echo "FAIL: unavailable Vale passed under VAULT_KIT_REQUIRE_VALE=1"; fail=1; }
archive=$(cd "$repo" && python3 -c 'import sys; sys.path.insert(0, "scripts")
import importlib.machinery as m, importlib.util as u
l = m.SourceFileLoader("vale", "scripts/vale"); mod = u.module_from_spec(u.spec_from_loader("vale", l)); l.exec_module(mod)
import pinnedbin; print(mod.ARCHIVES.get(pinnedbin.platform_key(), ""))')
if [ -n "$archive" ]; then
  printf 'not the release\n' > "$tmp/mirror/$archive"
  err=$(offline mirror 2>&1 >/dev/null); rc=$?
  [ "$rc" -ne 0 ] && grep -q 'checksum mismatch for downloaded' <<<"$err" ||
    { echo "FAIL: a tampered Vale download did not fail make prose (rc=$rc): $err"; fail=1; }
fi

[ "$fail" -eq 0 ] && echo "PASS: make prose" || { echo "FAIL: make prose"; exit 1; }
