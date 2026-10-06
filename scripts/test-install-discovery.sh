#!/usr/bin/env bash
# Exercise install-discovery against a throwaway HOME and a throwaway vault root
# (a non-git directory, so the worktree guard is bypassed) holding two fixture
# skills: six links expected. A third skill dir, extra-tool, is linked only with --include. The fixture root is nested one level so --pointer
# writes into the fixture's parent, never into a real project directory.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
fake_home=$(cd "$(mktemp -d)" && pwd -P)
fake_parent=$(cd "$(mktemp -d)" && pwd -P)
fake_root="$fake_parent/fixture-vault"
vault_name=fixture-vault
root_env=FIXTURE_VAULT_ROOT
a="$vault_name-discover"
b="$vault_name-maintain"
trap 'rm -rf "$fake_home" "$fake_parent"' EXIT
mkdir -p "$fake_home/.claude/skills" "$fake_home/.codex/skills" "$fake_home/.pi/agent/skills"
mkdir -p "$fake_root/scripts" "$fake_root/skills/$a" "$fake_root/skills/$b" "$fake_root/skills/extra-tool"
printf -- '---\nname: extra-tool\ndescription: a contributor-added skill\n---\n' > "$fake_root/skills/extra-tool/SKILL.md"
cp scripts/install-discovery scripts/vaultconf.py "$fake_root/scripts/"
write_conf() { printf 'template = false\nname = "%s"\ntitle = "Fixture Vault"\nscope = "install tests"\nroot_env = ""\n\n[redaction]\ndeny = []\n' "$vault_name" > "$1/vault.toml"; }
# A rendered skill: its own name, the generated notice, and the root env var it reads.
write_skill() {
  printf -- '---\nname: %s\ndescription: fixture\n---\n<!-- Generated from templates/skills/x/skill.md.tmpl by scripts/init-vault --render-skills; do not edit. -->\nroot="${%s}"\n' \
    "$2" "$3" > "$1/skills/$2/SKILL.md"
}
write_conf "$fake_root"
write_skill "$fake_root" "$a" "$root_env"
write_skill "$fake_root" "$b" "$root_env"
fail=0
run() { env -u "$root_env" HOME="$fake_home" python3 "$fake_root/scripts/install-discovery" "$@"; }
# Every regular file and symlink under the throwaway HOME and the fixture parent, outside the
# fixture vault itself: what a run wrote.
snapshot() { find "$fake_home" "$fake_parent" -path "$fake_root" -prune -o \( -type f -o -type l \) -print | sort; }

echo "--- no flags prints the targets and writes nothing"
before=$(snapshot)
out=$(run); rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL: no-flag run exit $rc"; fail=1; }
[ "$(snapshot)" = "$before" ] || { echo "FAIL: no-flag run wrote files"; fail=1; }
grep -qF -- "--pointer: $fake_parent/AGENTS.md (would be created)" <<<"$out" || { echo "FAIL: parent AGENTS.md target not printed: $out"; fail=1; }
grep -qF -- "--pointer-codex: $fake_home/.codex/AGENTS.md" <<<"$out" || { echo "FAIL: codex target not printed"; fail=1; }
grep -qF -- "--skills: claude: $fake_home/.claude/skills: $a, $b" <<<"$out" || { echo "FAIL: skill links not printed: $out"; fail=1; }
grep -q 'Nothing written' <<<"$out" || { echo "FAIL: no 'Nothing written' line"; fail=1; }

echo "--- the template refuses every write flag and writes nothing"
tmpl_root="$fake_parent/template-vault"; mkdir -p "$tmpl_root/scripts" && cp scripts/install-discovery scripts/vaultconf.py "$tmpl_root/scripts/"
printf 'template = true\nname = ""\ntitle = ""\nscope = ""\nroot_env = ""\n\n[redaction]\ndeny = []\n' > "$tmpl_root/vault.toml"
before=$(snapshot)
for flag in --skills --pointer --pointer-codex; do
  # No bytecode: the fixture's own __pycache__ would read as a write.
  err=$(PYTHONDONTWRITEBYTECODE=1 HOME="$fake_home" python3 "$tmpl_root/scripts/install-discovery" "$flag" 2>&1 >/dev/null); rc=$?
  [ "$rc" -eq 2 ] && grep -q "REFUSED $flag: vault.toml: template = true" <<<"$err" || { echo "FAIL: template $flag exit $rc: $err"; fail=1; }
done
[ "$(snapshot)" = "$before" ] || { echo "FAIL: a refused template run wrote files"; fail=1; }
HOME="$fake_home" python3 "$tmpl_root/scripts/install-discovery" >/dev/null || { echo "FAIL: template dry run exit $?"; fail=1; }
rm -rf "$tmpl_root"

echo "--- fresh install links only the vault's two skills"
out=$(run --skills); rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL: --skills exit $rc"; fail=1; }
count=$(find "$fake_home" -type l | wc -l | tr -d ' ')
[ "$count" -eq 6 ] || { echo "FAIL: expected 6 links, found $count"; fail=1; }
[ ! -e "$fake_home/.claude/skills/extra-tool" ] || { echo "FAIL: --skills linked a skill nobody named"; fail=1; }
grep -q 'not linked (name them with --include to install): extra-tool' <<<"$out" || { echo "FAIL: unlinked skill not reported: $out"; fail=1; }
if grep -qi 'hostname\|\.local:' <<<"$out"; then echo "FAIL: install printed the hostname"; fi

echo "--- --include links a named extra skill; uninstall removes it"
run --skills --include extra-tool >/dev/null || { echo "FAIL: --include exit $?"; fail=1; }
count=$(find "$fake_home" -type l | wc -l | tr -d ' ')
[ "$count" -eq 9 ] || { echo "FAIL: expected 9 links with --include, found $count"; fail=1; }
run --check --include extra-tool >/dev/null 2>&1 || { echo "FAIL: --check --include exit $?"; fail=1; }
# A plain --check must not call the --include link stray: its skill still exists.
out=$(run --check 2>&1); rc=$?
[ "$rc" -eq 0 ] && ! grep -q 'stray link' <<<"$out" || { echo "FAIL: --check called an --include link stray (rc=$rc): $out"; fail=1; }
err=$(run --skills --include no-such-skill 2>&1); [ $? -ne 0 ] && grep -q 'no skills/no-such-skill/SKILL.md' <<<"$err" || { echo "FAIL: unknown --include accepted: $err"; fail=1; }
run --uninstall >/dev/null || { echo "FAIL: uninstall after --include exit $?"; fail=1; }
count=$(find "$fake_home" -type l | wc -l | tr -d ' ')
[ "$count" -eq 0 ] || { echo "FAIL: $count links survived uninstall after --include"; fail=1; }
run --skills >/dev/null

echo "--- check after install"
run --check; rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL: --check exit $rc"; fail=1; }
FIXTURE_VAULT_ROOT="$fake_root" HOME="$fake_home" python3 "$fake_root/scripts/install-discovery" --check >/dev/null; rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL: --check with the root env var naming this checkout exit $rc"; fail=1; }

echo "--- check fails when the root env var names another checkout"
err=$(FIXTURE_VAULT_ROOT="$fake_parent" HOME="$fake_home" python3 "$fake_root/scripts/install-discovery" --check 2>&1 >/dev/null); rc=$?
[ "$rc" -eq 1 ] || { echo "FAIL: --check with a mismatched root exit $rc, want 1"; fail=1; }
grep -qF "\$$root_env is $fake_parent, not this checkout" <<<"$err" || { echo "FAIL: root mismatch not named: $err"; fail=1; }

echo "--- check fails when a linked skill was rendered for another vault"
cp "$fake_root/skills/$a/SKILL.md" "$fake_parent/skill.keep"
write_skill "$fake_root" "$a" OTHER_VAULT_ROOT
err=$(run --check 2>&1 >/dev/null); rc=$?
[ "$rc" -eq 1 ] || { echo "FAIL: --check with a foreign root env var exit $rc, want 1"; fail=1; }
grep -qF "does not read \$$root_env" <<<"$err" || { echo "FAIL: foreign root env var not named: $err"; fail=1; }
sed -i.tmp "s/^name: $a\$/name: other-vault-discover/" "$fake_root/skills/$a/SKILL.md" && rm -f "$fake_root/skills/$a/SKILL.md.tmp"
err=$(run --check 2>&1 >/dev/null); rc=$?
[ "$rc" -eq 1 ] || { echo "FAIL: --check with a mismatched skill name exit $rc, want 1"; fail=1; }
grep -qF "frontmatter name 'other-vault-discover' is not '$a'" <<<"$err" || { echo "FAIL: name mismatch not named: $err"; fail=1; }
mv "$fake_parent/skill.keep" "$fake_root/skills/$a/SKILL.md"
run --check >/dev/null 2>&1 || { echo "FAIL: --check did not recover after restoring the skill"; fail=1; }

echo "--- idempotent second run"
run --skills >/dev/null; rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL: second --skills exit $rc"; fail=1; }

echo "--- refusal when a target is a real directory"
rm "$fake_home/.codex/skills/$a"
mkdir "$fake_home/.codex/skills/$a"
run --skills >/dev/null; rc=$?
[ "$rc" -eq 1 ] || { echo "FAIL: expected exit 1 on refusal, got $rc"; fail=1; }
run --check >/dev/null 2>&1; rc=$?
[ "$rc" -eq 1 ] || { echo "FAIL: --check should fail with a foreign dir, got $rc"; fail=1; }
rmdir "$fake_home/.codex/skills/$a"
run --skills >/dev/null

echo "--- stray link for a removed skill is reported and removed"
ln -s "$fake_root/skills/gone" "$fake_home/.claude/skills/gone"
out=$(run --check 2>&1); grep -q 'stray link' <<<"$out" || { echo "FAIL: --check did not report the stray link"; fail=1; }
out=$(run --uninstall); grep -q 'removed stray' <<<"$out" || { echo "FAIL: --uninstall did not remove the stray link"; fail=1; }
[ ! -L "$fake_home/.claude/skills/gone" ] || { echo "FAIL: stray link survived uninstall"; fail=1; }
run --skills >/dev/null

echo "--- uninstall leaves a foreign link that occupies an expected name, and exits 1 naming it"
rm "$fake_home/.claude/skills/$a"
ln -s /nonexistent "$fake_home/.claude/skills/$a"
out=$(run --uninstall 2>&1); rc=$?
[ "$rc" -eq 1 ] || { echo "FAIL: uninstall with a link left exit $rc, want 1"; fail=1; }
grep -q "left .*\.claude/skills/$a" <<<"$out" || { echo "FAIL: foreign link not reported as left"; fail=1; }
grep -q "FAIL: 1 expected link(s) left in place: .*\.claude/skills/$a" <<<"$out" || { echo "FAIL: left link not named in the failure: $out"; fail=1; }
[ -L "$fake_home/.claude/skills/$a" ] || { echo "FAIL: foreign link removed"; fail=1; }
rm "$fake_home/.claude/skills/$a"
remaining=$(find "$fake_home" -type l | wc -l | tr -d ' ')
[ "$remaining" -eq 0 ] || { echo "FAIL: $remaining vault links survived uninstall"; fail=1; }

echo "--- skipped harness dir is reported, not created"
mv "$fake_home/.pi" "$fake_parent/pi.keep"
out=$(run --skills); rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL: missing harness dir should skip, got $rc"; fail=1; }
grep -q '^skip pi: ' <<<"$out" || { echo "FAIL: no skip line for the absent pi dir"; fail=1; }
grep -q '4 linked, 1 harness dir(s) skipped, 0 refused' <<<"$out" || { echo "FAIL: wrong skip accounting: $out"; fail=1; }
[ ! -d "$fake_home/.pi" ] || { echo "FAIL: install recreated the absent harness dir"; fail=1; }
mv "$fake_parent/pi.keep" "$fake_home/.pi"
run --uninstall >/dev/null || { echo "FAIL: uninstall after skip test exit $?"; fail=1; }

echo "--- unknown flag names itself on stderr, exit 2"
err=$(run --skil 2>&1 >/dev/null); rc=$?
[ "$rc" -eq 2 ] || { echo "FAIL: unknown flag exit $rc"; fail=1; }
grep -q 'unknown flag(s): --skil' <<<"$err" || { echo "FAIL: unknown flag not named"; fail=1; }

echo "--- empty skills dir refuses loudly"
empty_root=$(mktemp -d); mkdir -p "$empty_root/scripts" "$empty_root/skills"; cp scripts/install-discovery scripts/vaultconf.py "$empty_root/scripts/"; write_conf "$empty_root"
HOME="$fake_home" python3 "$empty_root/scripts/install-discovery" --skills 2>/dev/null; rc=$?
[ "$rc" -ne 0 ] || { echo "FAIL: empty skills/ installed nothing and exited 0"; fail=1; }
rm -rf "$empty_root"

echo "--- --pointer refuses a parent that is HOME or /"
err=$(run --pointer --parent "$fake_home" 2>&1 >/dev/null); rc=$?
[ "$rc" -eq 2 ] || { echo "FAIL: --pointer at HOME exit $rc, want 2"; fail=1; }
grep -q 'REFUSED --pointer' <<<"$err" || { echo "FAIL: home refusal not explained: $err"; fail=1; }
[ ! -e "$fake_home/AGENTS.md" ] && [ ! -L "$fake_home/CLAUDE.md" ] || { echo "FAIL: refused --pointer wrote into HOME"; fail=1; }
# / is covered by the dry run only, so a broken refusal can never write at the filesystem root.
out=$(run --parent /); grep -qF -- '--pointer: refused without --pointer-at-home, because / is $HOME or /' <<<"$out" ||
  { echo "FAIL: dry run does not flag / as refused: $out"; fail=1; }

echo "--- --pointer-at-home allows it, and uninstall removes the file and link it created"
out=$(run --pointer --pointer-at-home --parent "$fake_home"); rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL: --pointer-at-home exit $rc"; fail=1; }
grep -qF "wrote $fake_home/AGENTS.md" <<<"$out" || { echo "FAIL: write did not print its path: $out"; fail=1; }
grep -q "$vault_name:start" "$fake_home/AGENTS.md" || { echo "FAIL: no block in HOME AGENTS.md"; fail=1; }
run --uninstall --parent "$fake_home" >/dev/null || { echo "FAIL: uninstall at home exit $?"; fail=1; }
[ ! -e "$fake_home/AGENTS.md" ] && [ ! -L "$fake_home/CLAUDE.md" ] || { echo "FAIL: uninstall left the AGENTS.md or CLAUDE.md it created in HOME"; fail=1; }

echo "--- pointer writes through a symlinked AGENTS.md and keeps the link"
printf '# Shared\nkeep me\n' > "$fake_parent/elsewhere.md"
ln -s "$fake_parent/elsewhere.md" "$fake_parent/AGENTS.md"
run --pointer >/dev/null; rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL: --pointer exit $rc"; fail=1; }
[ -L "$fake_parent/AGENTS.md" ] || { echo "FAIL: --pointer replaced the symlinked AGENTS.md with a file"; fail=1; }
grep -q 'keep me' "$fake_parent/elsewhere.md" || { echo "FAIL: --pointer lost the link target's content"; fail=1; }
grep -q "$vault_name:start" "$fake_parent/elsewhere.md" || { echo "FAIL: --pointer did not write the block through the link"; fail=1; }
[ -L "$fake_parent/CLAUDE.md" ] || { echo "FAIL: --pointer did not create the CLAUDE.md link"; fail=1; }
out=$(run --pointer)
grep -q 'AGENTS.md unchanged' <<<"$out" || { echo "FAIL: second --pointer was not idempotent: $out"; fail=1; }

echo "--- uninstall removes the block, the CLAUDE.md link it created, and reports the .bak"
out=$(run --uninstall); rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL: uninstall exit $rc: $out"; fail=1; }
if grep -q "$vault_name:" "$fake_parent/elsewhere.md"; then echo "FAIL: block survived uninstall"; fail=1; fi
grep -q 'keep me' "$fake_parent/elsewhere.md" || { echo "FAIL: uninstall lost the AGENTS.md content"; fail=1; }
[ -L "$fake_parent/AGENTS.md" ] || { echo "FAIL: uninstall removed the operator's AGENTS.md link"; fail=1; }
[ ! -e "$fake_parent/CLAUDE.md" ] && [ ! -L "$fake_parent/CLAUDE.md" ] || { echo "FAIL: CLAUDE.md link survived uninstall"; fail=1; }
grep -qF "left $fake_parent/elsewhere.md.bak" <<<"$out" || { echo "FAIL: .bak not reported: $out"; fail=1; }
rm -f "$fake_parent/elsewhere.md.bak"

echo "--- uninstall removes an appended CLAUDE.md block and leaves a CLAUDE.md it did not create"
printf '# Claude notes\nkeep this too\n' > "$fake_parent/CLAUDE.md"
run --pointer >/dev/null || { echo "FAIL: --pointer with a real CLAUDE.md exit $?"; fail=1; }
grep -q "$vault_name:start" "$fake_parent/CLAUDE.md" || { echo "FAIL: block not appended to CLAUDE.md"; fail=1; }
run --uninstall >/dev/null || { echo "FAIL: uninstall exit $?"; fail=1; }
if grep -q "$vault_name:" "$fake_parent/CLAUDE.md"; then echo "FAIL: appended CLAUDE.md block survived uninstall"; fail=1; fi
grep -q 'keep this too' "$fake_parent/CLAUDE.md" || { echo "FAIL: uninstall removed the operator's CLAUDE.md"; fail=1; }
rm -f "$fake_parent/CLAUDE.md" "$fake_parent/CLAUDE.md.bak" "$fake_parent/elsewhere.md.bak"

echo "--- --pointer-codex writes ~/.codex/AGENTS.md; uninstall removes it"
out=$(run --pointer-codex); rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL: --pointer-codex exit $rc"; fail=1; }
grep -qF "wrote $fake_home/.codex/AGENTS.md" <<<"$out" || { echo "FAIL: codex write did not print its path: $out"; fail=1; }
grep -q "$vault_name:start" "$fake_home/.codex/AGENTS.md" || { echo "FAIL: no block in codex AGENTS.md"; fail=1; }
run --uninstall >/dev/null || { echo "FAIL: uninstall exit $?"; fail=1; }
[ ! -e "$fake_home/.codex/AGENTS.md" ] || { echo "FAIL: codex AGENTS.md created by the install survived uninstall"; fail=1; }
printf '# my codex rules\n' > "$fake_home/.codex/AGENTS.md"
run --pointer-codex >/dev/null && run --uninstall >/dev/null
[ "$(cat "$fake_home/.codex/AGENTS.md")" = "# my codex rules" ] || { echo "FAIL: uninstall changed the operator's codex AGENTS.md: $(cat "$fake_home/.codex/AGENTS.md")"; fail=1; }

echo "--- nothing left behind but the operator's own files"
left=$(find "$fake_home" \( -type l -o -name '*.md' \) ! -path "$fake_home/.codex/AGENTS.md" ! -name '*.bak' | wc -l | tr -d ' ')
[ "$left" -eq 0 ] || { echo "FAIL: $left install artifact(s) left under HOME"; find "$fake_home" -type l -o -name '*.md'; fail=1; }

if [ "$fail" -eq 0 ]; then echo "PASS: install-discovery dry run/--skills/--check/--pointer/--pointer-codex/--uninstall"; else echo "FAIL: install-discovery"; fi
exit "$fail"
