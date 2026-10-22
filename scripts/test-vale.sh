#!/usr/bin/env bash
# Exercise scripts/vale and the shared verifier (scripts/pinnedbin.py). Every refusal case
# gets its own throwaway XDG_CACHE_HOME and a local file:// download base, so no network is
# used. The genuine resolve uses the normal cache and the real release; offline it prints
# SKIP, unless VAULT_KIT_REQUIRE_VALE=1 (CI), which makes it a failure.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
fail=0
archive=$(python3 -c 'import sys; sys.path.insert(0, "scripts")
import importlib.machinery as m, importlib.util as u
l = m.SourceFileLoader("vale", "scripts/vale"); mod = u.module_from_spec(u.spec_from_loader("vale", l)); l.exec_module(mod)
import pinnedbin; print(mod.ARCHIVES.get(pinnedbin.platform_key(), ""))')
[ -n "$archive" ] || { echo "SKIP: no pinned Vale build for this platform"; exit 0; }
case_dir() { local d="$tmp/$1"; mkdir -p "$d/cache" "$d/mirror"; chmod 755 "$d/cache"; echo "$d"; }
vale() { # case dir, args...
  local d=$1; shift
  env -u VALE_BIN XDG_CACHE_HOME="$d/cache" VALE_DOWNLOAD_BASE="file://$d/mirror" python3 scripts/vale "$@"
}
expect() { # label, wanted exit, got exit, stderr, wanted text
  [ "$2" = "$3" ] && grep -qF -- "$5" <<<"$4" || { echo "FAIL: $1: wanted exit $2 and '$5', got $3: $4"; fail=1; }
}

echo "--- a tampered archive exits 2 and caches nothing; the download is announced first"
d=$(case_dir tampered); printf 'not the release\n' > "$d/mirror/$archive"
err=$(vale "$d" --vault-resolve 2>&1 >/dev/null); rc=$?
expect "tampered archive" 2 "$rc" "$err" "checksum mismatch for downloaded $archive"
grep -qF 'downloading vale 3.24.0' <<<"$err" || { echo "FAIL: no download line: $err"; fail=1; }
[ ! -e "$d/cache/vault-kit/vale-3.24.0/vale" ] || { echo "FAIL: a tampered download was cached"; fail=1; }

echo "--- a planted cached binary exits 2 and never runs"
d=$(case_dir planted); mkdir -p "$d/cache/vault-kit/vale-3.24.0"
printf '#!/bin/sh\ntouch "%s/ran"\necho vale version 3.24.0\n' "$d" > "$d/cache/vault-kit/vale-3.24.0/vale"
chmod 755 "$d/cache/vault-kit/vale-3.24.0/vale"
err=$(vale "$d" --version 2>&1 >/dev/null); rc=$?
expect "planted cache" 2 "$rc" "$err" "checksum mismatch for cached"
[ ! -e "$d/ran" ] || { echo "FAIL: the planted binary ran"; fail=1; }

echo "--- a cache directory others can write exits 2"
d=$(case_dir shared); mkdir -p "$d/cache/vault-kit/vale-3.24.0" && chmod 777 "$d/cache/vault-kit/vale-3.24.0"
err=$(vale "$d" --vault-resolve 2>&1 >/dev/null); rc=$?
expect "shared cache dir" 2 "$rc" "$err" "writable by others"

echo "--- a cache made under umask 002 is created private and accepted"
d=$(case_dir umask); rm -rf "$d/cache"; mkdir -p "$d/cache" && cp -R "$tmp/tampered/mirror/." "$d/mirror/" 2>/dev/null
err=$( (umask 002; vale "$d" --vault-resolve) 2>&1 >/dev/null); rc=$?
case "$(stat -c '%a' "$d/cache/vault-kit" 2>/dev/null || stat -f '%Lp' "$d/cache/vault-kit")" in
  700) ;; *) echo "FAIL: umask 002 left $(ls -ld "$d/cache/vault-kit")"; fail=1 ;;
esac
grep -q 'writable by others' <<<"$err" && { echo "FAIL: refused a cache it created under umask 002: $err"; fail=1; }

echo "--- a cached binary others can write is refused, with the fix"
d=$(case_dir binmode); mkdir -p "$d/cache/vault-kit/vale-3.24.0" && chmod 700 "$d/cache/vault-kit" "$d/cache/vault-kit/vale-3.24.0"
printf 'x\n' > "$d/cache/vault-kit/vale-3.24.0/vale" && chmod 777 "$d/cache/vault-kit/vale-3.24.0/vale"
err=$(vale "$d" --version 2>&1 >/dev/null); rc=$?
expect "writable cached binary" 2 "$rc" "$err" "chmod go-w"

echo "--- an unusable cache (a crash, not a refusal) exits 2, never 1"
d=$(case_dir crash); printf 'not a directory\n' > "$d/cache-file"
err=$(env -u VALE_BIN XDG_CACHE_HOME="$d/cache-file" python3 scripts/vale --vault-resolve 2>&1 >/dev/null); rc=$?
expect "unusable cache" 2 "$rc" "$err" "could not resolve vale"

echo "--- an unreachable mirror exits 3 (unavailable), not 2"
d=$(case_dir unreachable); rmdir "$d/mirror"
err=$(vale "$d" --vault-resolve 2>&1 >/dev/null); rc=$?
expect "unreachable mirror" 3 "$rc" "$err" "could not download"

echo "--- a download base that is not a URL scheme exits 2"
d=$(case_dir scheme)
err=$(env -u VALE_BIN XDG_CACHE_HOME="$d/cache" VALE_DOWNLOAD_BASE="-K$d/curlrc" python3 scripts/vale --vault-resolve 2>&1 >/dev/null); rc=$?
expect "bad download base" 2 "$rc" "$err" "VALE_DOWNLOAD_BASE must start with"

echo "--- VALE_BIN must report exactly the pinned version; there is no unpinned escape"
d=$(case_dir override)
for reported in "vale version 3.24.0-evil" "vale version 3.24.01" "3.24.0"; do
  printf '#!/bin/sh\necho "%s"\n' "$reported" > "$d/fake-vale" && chmod 755 "$d/fake-vale"
  err=$(VALE_BIN="$d/fake-vale" VALE_ALLOW_UNPINNED=1 GITLEAKS_ALLOW_UNPINNED=1 python3 scripts/vale --vault-resolve 2>&1 >/dev/null); rc=$?
  expect "VALE_BIN reporting '$reported'" 2 "$rc" "$err" "not the pinned 3.24.0"
done
printf '#!/bin/sh\necho "vale version 3.24.0"\n' > "$d/fake-vale" && chmod 755 "$d/fake-vale"
out=$(VALE_BIN="$d/fake-vale" python3 scripts/vale --vault-resolve 2>"$d/err"); rc=$?
[ "$rc" -eq 0 ] && [ "$out" = "$d/fake-vale" ] && grep -qF 'not hash-verified' "$d/err" ||
  { echo "FAIL: a right-version VALE_BIN of another build (rc=$rc, out=$out): $(cat "$d/err")"; fail=1; }

echo "--- an archive with no vale member is refused as integrity"
python3 - "$tmp" <<'PY' || fail=1
import hashlib, io, os, sys, tarfile
sys.path.insert(0, "scripts")
import pinnedbin
tmp = sys.argv[1]
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz") as tar:
    info = tarfile.TarInfo("README.md"); data = b"no binary here\n"; info.size = len(data)
    tar.addfile(info, io.BytesIO(data))
os.makedirs(f"{tmp}/member/mirror"); os.makedirs(f"{tmp}/member/cache", mode=0o755)
open(f"{tmp}/member/mirror/a.tar.gz", "wb").write(buf.getvalue())
key = pinnedbin.platform_key()
spec = pinnedbin.ToolSpec(name="vale", version="0", release_url=f"file://{tmp}/member/mirror",
                          archives={key: "a.tar.gz"},
                          pins={key: {"archive": hashlib.sha256(buf.getvalue()).hexdigest(), "binary": "0"}},
                          env_prefix="TESTVALE", version_args=("--version",), version_output="x", install_hint="")
os.environ["XDG_CACHE_HOME"] = f"{tmp}/member/cache"
try:
    pinnedbin.resolve(spec)
except pinnedbin.Refusal as refusal:
    if refusal.kind != pinnedbin.INTEGRITY or "has no vale member" not in str(refusal):
        print(f"FAIL: missing member refused as {refusal.kind}: {refusal}"); raise SystemExit(1)
else:
    print("FAIL: an archive with no vale member was accepted"); raise SystemExit(1)
# A verified archive whose vale member has the wrong hash.
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz") as tar:
    info = tarfile.TarInfo("vale"); data = b"#!/bin/sh\necho impostor\n"; info.size = len(data); info.mode = 0o755
    tar.addfile(info, io.BytesIO(data))
open(f"{tmp}/member/mirror/b.tar.gz", "wb").write(buf.getvalue())
os.makedirs(f"{tmp}/inner/cache", mode=0o755)
os.environ["XDG_CACHE_HOME"] = f"{tmp}/inner/cache"
spec2 = pinnedbin.ToolSpec(name="vale", version="1", release_url=f"file://{tmp}/member/mirror",
                           archives={key: "b.tar.gz"},
                           pins={key: {"archive": hashlib.sha256(buf.getvalue()).hexdigest(), "binary": "0" * 64}},
                           env_prefix="TESTVALE", version_args=("--version",), version_output="x", install_hint="")
try:
    pinnedbin.resolve(spec2)
except pinnedbin.Refusal as refusal:
    if refusal.kind != pinnedbin.INTEGRITY or "checksum mismatch for vale inside" not in str(refusal):
        print(f"FAIL: wrong-hash member refused as {refusal.kind}: {refusal}"); raise SystemExit(1)
else:
    print("FAIL: a member with the wrong hash was accepted"); raise SystemExit(1)
if os.path.exists(f"{tmp}/inner/cache/vault-kit/vale-1/vale"):
    print("FAIL: a member with the wrong hash was cached"); raise SystemExit(1)
# No pin for this platform: unavailable, not integrity.
spec3 = pinnedbin.ToolSpec(name="vale", version="2", release_url="file:///nowhere", archives={}, pins={},
                           env_prefix="TESTVALE", version_args=("--version",), version_output="x", install_hint="")
try:
    pinnedbin.resolve(spec3)
except pinnedbin.Refusal as refusal:
    if refusal.kind != pinnedbin.UNAVAILABLE or "no pinned vale build" not in str(refusal):
        print(f"FAIL: no-pin platform refused as {refusal.kind}: {refusal}"); raise SystemExit(1)
else:
    print("FAIL: a platform with no pin resolved"); raise SystemExit(1)
PY

echo "--- the genuine release resolves and runs"
out=$(env -u VALE_BIN python3 scripts/vale --version 2>"$tmp/genuine.err"); rc=$?
if [ "$rc" -eq 0 ]; then
  [ "$out" = "vale version 3.24.0" ] || { echo "FAIL: genuine vale printed '$out'"; fail=1; }
elif [ "$rc" -eq 3 ] && [ "${VAULT_KIT_REQUIRE_VALE:-}" != "1" ]; then
  echo "SKIP: genuine Vale could not be downloaded (offline?): $(cat "$tmp/genuine.err")"
else
  echo "FAIL: genuine resolve exit $rc: $(cat "$tmp/genuine.err")"; fail=1
fi

[ "$fail" -eq 0 ] && echo "PASS: vale wrapper and shared verifier" || { echo "FAIL: vale wrapper"; exit 1; }
