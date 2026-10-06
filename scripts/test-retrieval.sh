#!/usr/bin/env bash
# Exercise per-vault retrieval (scripts/qmd, retrieval-setup, refresh-qmd) against scratch copies
# of this tree under a throwaway HOME, XDG dirs and index path. Needs npm QMD installed.
# Lexical by default; VAULT_KIT_TEST_SEMANTIC=1 adds embeddings and a vector search, which need
# the embedding model: it is linked read-only from the real model cache when present there
# (override the directory with VAULT_KIT_TEST_MODELS), otherwise downloaded into the throwaway one.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
repo=$(pwd)
command -v qmd >/dev/null 2>&1 || { echo "FAIL: qmd is not installed (npm install -g @tobilu/qmd)"; exit 2; }
real_models="${VAULT_KIT_TEST_MODELS:-${XDG_CACHE_HOME:-$HOME/.cache}/qmd/models}"
real_index="${XDG_CACHE_HOME:-$HOME/.cache}/qmd/index.sqlite"
real_before=$(shasum "$real_index" 2>/dev/null || echo absent)
tmp=$(cd "$(mktemp -d)" && pwd -P)
trap 'rm -rf "$tmp"' EXIT
fail=0
semantic=${VAULT_KIT_TEST_SEMANTIC:-0}

mkdir -p "$tmp/home/.cache/qmd/models" "$tmp/home/.config"
if [ "$semantic" = 1 ] && [ -d "$real_models" ]; then
  for f in "$real_models"/*.gguf; do [ -e "$f" ] && ln -s "$f" "$tmp/home/.cache/qmd/models/"; done
fi
export HOME="$tmp/home" XDG_CACHE_HOME="$tmp/home/.cache" XDG_CONFIG_HOME="$tmp/home/.config"
unset INDEX_PATH QMD_CONFIG_DIR
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
flags="--lexical-only"; [ "$semantic" = 1 ] && flags=""
note() { echo "FAIL: $*"; fail=1; }

copy() {  # <dir>: the working tree (minus ignored files), no .git
  mkdir -p "$1"
  (cd "$repo" && git ls-files -z --cached --others --exclude-standard | tar --null -T - -cf -) |
    tar -xf - -C "$1" || return 1
}
seed() {  # <dir> <slug> <token>: init a vault, add a page and a log line that both carry the token
  copy "$1" || return 1
  python3 "$1/scripts/init-vault" --name "$2" --title "Demo $2" --scope "test pages" >/dev/null || return 1
  mkdir -p "$1/wiki/runbooks"
  printf -- '---\ntype: Runbook\ntitle: Seeded page\ndescription: Seed.\nstatus: draft\n---\n# Seeded page\n\nThe %s lives here.\n' "$3" >"$1/wiki/runbooks/seeded-page.md"
  printf '\n%s in the log\n' "$3" >>"$1/wiki/log.md"
}
files() { python3 -c 'import json,sys; [print(r["file"]) for r in json.load(sys.stdin)]'; }

echo "--- template mode refuses"
t="$tmp/template"; copy "$t" || { echo "FAIL: could not copy the tree"; exit 1; }
if grep -q '^template = true' "$t/vault.toml"; then
  out=$(make --no-print-directory -C "$t" retrieval-setup 2>&1); rc=$?
  { [ "$rc" -ne 0 ] && grep -q 'template = true and name unset' <<<"$out"; } || note "template-mode setup exit $rc: $out"
  [ ! -e "$t/.qmd" ] || note "template-mode setup created .qmd"
else echo "SKIP: this tree is not in template mode"; fi

echo "--- two vaults: setup, search, isolation"
a="$tmp/a"; b="$tmp/b"
seed "$a" demo-vault quokkaalpha && seed "$b" other-vault quokkabeta || { echo "FAIL: could not seed"; exit 1; }
for v in "$a" "$b"; do
  out=$(make --no-print-directory -C "$v" retrieval-setup REFRESH_FLAGS=$flags 2>&1); rc=$?
  [ "$rc" -eq 0 ] || { note "setup exit $rc in $v: $out"; continue; }
  [ -f "$v/.qmd/index.sqlite" ] || note "no index at $v/.qmd/index.sqlite"
  make --no-print-directory -C "$v" retrieval-setup REFRESH_FLAGS=$flags >/dev/null 2>&1 || note "second setup is not idempotent in $v"
done
got=$("$a/scripts/qmd" search quokkaalpha -c demo-vault --json | files)
grep -qx 'qmd://demo-vault/wiki/runbooks/seeded-page.md' <<<"$got" || note "seeded page not found: $got"
! grep -q 'wiki/log.md' <<<"$got" || note "wiki/log.md was returned: $got"
[ "$("$a/scripts/qmd" search quokkaalpha-nothere -c demo-vault --json | files | wc -l)" -eq 0 ] || note "negative control matched"
# A search from another working directory still lands on this vault's index.
got=$(cd "$tmp" && "$b/scripts/qmd" search quokkabeta -c other-vault --json | files)
grep -qx 'qmd://other-vault/wiki/runbooks/seeded-page.md' <<<"$got" || note "search from another cwd missed: $got"
# Isolation: each token is invisible to the other vault.
[ "$("$a/scripts/qmd" search quokkabeta --json | files | wc -l)" -eq 0 ] || note "vault a sees vault b"
[ "$("$b/scripts/qmd" search quokkaalpha --json | files | wc -l)" -eq 0 ] || note "vault b sees vault a"
[ "$("$a/scripts/qmd" collection list 2>&1 | grep -c 'other-vault')" -eq 0 ] || note "vault a lists vault b's collection"
# Nothing leaked into the shared HOME locations.
leak=$(find "$tmp/home/.cache/qmd" "$tmp/home/.config" \( -name '*.sqlite' -o -name '*.yml' -o -name trusted.json \) 2>/dev/null)
[ -z "$leak" ] || note "state outside .qmd/: $leak"
make --no-print-directory -C "$a" retrieval >"$tmp/retrieval.log" 2>&1 || { note "make retrieval:"; cat "$tmp/retrieval.log"; }

if [ "$semantic" = 1 ]; then
  echo "--- semantic leg"
  got=$("$a/scripts/qmd" vsearch "where the quokkaalpha lives" -c demo-vault --json 2>"$tmp/vsearch.err" | files)
  grep -q 'seeded-page.md' <<<"$got" || { note "vsearch missed the seeded page: $got $(cat "$tmp/vsearch.err")"; }
else
  echo "SKIP: semantic leg (set VAULT_KIT_TEST_SEMANTIC=1; needs the embedding model)"
fi

echo "--- teardown leaves nothing"
for v in "$a" "$b"; do
  make --no-print-directory -C "$v" retrieval-teardown >/dev/null 2>&1 || note "teardown failed in $v"
  [ ! -e "$v/.qmd" ] || note "$v/.qmd remains"
  make --no-print-directory -C "$v" retrieval-teardown >/dev/null 2>&1 || note "second teardown is not idempotent in $v"
done
out=$("$a/scripts/qmd" search quokkaalpha --json 2>&1); rc=$?
{ [ "$rc" -ne 0 ] && grep -q 'make retrieval-setup' <<<"$out"; } || note "search after teardown: exit $rc: $out"
[ ! -e "$tmp/home/.cache/qmd/index.sqlite" ] && [ ! -e "$tmp/home/.config/qmd" ] || note "state appeared in the throwaway HOME"
[ "$(shasum "$real_index" 2>/dev/null || echo absent)" = "$real_before" ] || note "the real QMD index changed"

[ "$fail" -eq 0 ] && echo "PASS: per-vault retrieval" || { echo "FAIL: per-vault retrieval"; exit 1; }
