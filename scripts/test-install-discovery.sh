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

echo "--- repeated --parent writes each, records them, and a bare --uninstall removes them all"
# A git checkout of the fixture vault, so the pointer dirs are recorded in its local config.
git_parent="$fake_parent/git-layout"; git_root="$git_parent/vault"
p1="$fake_parent/apps-one"; p2="$fake_parent/apps-two"; repo_dir="$fake_parent/one-repo"
mkdir -p "$git_root" "$p1" "$p2" "$repo_dir/.git"
cp -R "$fake_root/scripts" "$fake_root/skills" "$fake_root/vault.toml" "$git_root/"
git_run() { env -u "$root_env" HOME="$fake_home" GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null \
  PYTHONDONTWRITEBYTECODE=1 python3 "$git_root/scripts/install-discovery" "$@"; }
GIT_CONFIG_GLOBAL=/dev/null git -C "$git_root" init -q || { echo "FAIL: git init"; fail=1; }
out=$(git_run --parent "$p1" --parent "$p2"); rc=$?
[ "$rc" -eq 0 ] && grep -qF -- "--pointer: $p1/AGENTS.md (would be created)" <<<"$out" &&
  grep -qF -- "--pointer: $p2/AGENTS.md (would be created)" <<<"$out" || { echo "FAIL: dry run does not list both parents (rc=$rc): $out"; fail=1; }
out=$(git_run --pointer --parent "$p1" --parent "$p2" --parent "$repo_dir"); rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL: --pointer with three parents exit $rc: $out"; fail=1; }
for dir in "$p1" "$p2" "$repo_dir"; do
  grep -q "$vault_name:start" "$dir/AGENTS.md" || { echo "FAIL: no block in $dir/AGENTS.md"; fail=1; }
done
grep -qF "warning: $repo_dir is itself a git repository" <<<"$out" || { echo "FAIL: no warning for a parent that is a git root: $out"; fail=1; }
if grep -q "warning: $p1 " <<<"$out"; then echo "FAIL: warned about a parent that is not a git root"; fail=1; fi
recorded=$(git -C "$git_root" config --local --get-all vaultkit.pointerDir)
[ "$recorded" = "$(printf '%s\n%s\n%s' "$p1" "$p2" "$repo_dir")" ] || { echo "FAIL: recorded pointer dirs: $recorded"; fail=1; }
git_run --pointer --parent "$p1" >/dev/null
[ "$(git -C "$git_root" config --local --get-all vaultkit.pointerDir | wc -l | tr -d ' ')" -eq 3 ] ||
  { echo "FAIL: a repeated --pointer recorded a parent twice"; fail=1; }
out=$(git_run --uninstall); rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL: bare --uninstall exit $rc: $out"; fail=1; }
for dir in "$p1" "$p2" "$repo_dir"; do
  [ ! -e "$dir/AGENTS.md" ] && [ ! -L "$dir/CLAUDE.md" ] || { echo "FAIL: bare --uninstall left the pointer in $dir"; fail=1; }
done
git -C "$git_root" config --local --get-all vaultkit.pointerDir >/dev/null && { echo "FAIL: --uninstall left vaultkit.pointerDir set"; fail=1; }
echo "--- a recorded dir that is gone keeps its record; the rest are removed"
git_run --pointer --parent "$p1" --parent "$p2" >/dev/null
mv "$p2" "$p2.moved"
out=$(git_run --uninstall); rc=$?
[ "$rc" -eq 0 ] && grep -qF "left $p2 recorded" <<<"$out" || { echo "FAIL: a missing recorded dir was not reported (rc=$rc): $out"; fail=1; }
[ "$(git -C "$git_root" config --local --get-all vaultkit.pointerDir)" = "$p2" ] || { echo "FAIL: records after uninstall with a missing dir: $(git -C "$git_root" config --local --get-all vaultkit.pointerDir)"; fail=1; }
[ ! -e "$p1/AGENTS.md" ] || { echo "FAIL: the present dir's block survived"; fail=1; }
mv "$p2.moved" "$p2"
git_run --uninstall >/dev/null
[ ! -e "$p2/AGENTS.md" ] && ! git -C "$git_root" config --local --get-all vaultkit.pointerDir >/dev/null ||
  { echo "FAIL: a re-run after the dir came back did not finish the uninstall"; fail=1; }
echo "--- a refused parent stops every write"
out=$(git_run --pointer --parent "$p1" --parent "$fake_home" 2>&1); rc=$?
[ "$rc" -eq 2 ] && [ ! -e "$p1/AGENTS.md" ] || { echo "FAIL: a HOME parent did not stop the other writes (rc=$rc)"; fail=1; }
ln -s "$fake_parent/no-such-file" "$p2/CLAUDE.md"
out=$(git_run --pointer --parent "$p1" --parent "$p2" 2>&1); rc=$?
[ "$rc" -ne 0 ] && [ ! -e "$p1/AGENTS.md" ] && grep -q 'dangling symlink' <<<"$out" ||
  { echo "FAIL: a dangling CLAUDE.md in the second parent did not stop the first write (rc=$rc): $out"; fail=1; }
git -C "$git_root" config --local --get-all vaultkit.pointerDir >/dev/null && { echo "FAIL: a refused run recorded a parent"; fail=1; }
rm "$p2/CLAUDE.md"

echo "--- --remove-parent removes one pointer and leaves the other, its record, the skills, and Codex"
records() { git -C "$git_root" config --local --get-all vaultkit.pointerDir; }
git_run --pointer --pointer-codex --skills --parent "$p1" --parent "$p2" >/dev/null || { echo "FAIL: install for --remove-parent exit $?"; fail=1; }
links_before=$(find "$fake_home" -type l | sort)
out=$(git_run --remove-parent "$p1"); rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL: --remove-parent exit $rc: $out"; fail=1; }
[ ! -e "$p1/AGENTS.md" ] && [ ! -L "$p1/CLAUDE.md" ] || { echo "FAIL: --remove-parent left the pointer in $p1"; fail=1; }
grep -q "$vault_name:start" "$p2/AGENTS.md" && [ -L "$p2/CLAUDE.md" ] || { echo "FAIL: --remove-parent touched the other pointer"; fail=1; }
[ "$(records)" = "$p2" ] || { echo "FAIL: records after --remove-parent: $(records)"; fail=1; }
[ "$(find "$fake_home" -type l | sort)" = "$links_before" ] || { echo "FAIL: --remove-parent changed the skill links"; fail=1; }
grep -q "$vault_name:start" "$fake_home/.codex/AGENTS.md" || { echo "FAIL: --remove-parent removed the Codex block"; fail=1; }

echo "--- --remove-parent with --pointer moves a pointer in one run"
out=$(git_run --remove-parent "$p2" --pointer --parent "$p1"); rc=$?
[ "$rc" -eq 0 ] || { echo "FAIL: move exit $rc: $out"; fail=1; }
[ ! -e "$p2/AGENTS.md" ] && grep -q "$vault_name:start" "$p1/AGENTS.md" || { echo "FAIL: move did not swap the pointer"; fail=1; }
[ "$(records)" = "$p1" ] || { echo "FAIL: records after move: $(records)"; fail=1; }

echo "--- --remove-parent refuses an unknown name before removing anything, and bad combinations"
err=$(git_run --remove-parent "$p1" --remove-parent "$fake_parent/never-there" 2>&1); rc=$?
[ "$rc" -eq 2 ] && grep -q 'not a directory and not recorded' <<<"$err" || { echo "FAIL: unknown --remove-parent (rc=$rc): $err"; fail=1; }
grep -q "$vault_name:start" "$p1/AGENTS.md" || { echo "FAIL: a refused --remove-parent removed $p1"; fail=1; }
err=$(git_run --uninstall --remove-parent "$p1" 2>&1); rc=$?
[ "$rc" -eq 2 ] && grep -q 'cannot be combined with --uninstall' <<<"$err" || { echo "FAIL: --uninstall --remove-parent (rc=$rc): $err"; fail=1; }
err=$(git_run --pointer --parent "$p1" --remove-parent "$p1" 2>&1); rc=$?
[ "$rc" -eq 2 ] && grep -q 'name the same directory' <<<"$err" || { echo "FAIL: same dir in --parent and --remove-parent (rc=$rc): $err"; fail=1; }
grep -q "$vault_name:start" "$p1/AGENTS.md" || { echo "FAIL: a refused combination removed $p1"; fail=1; }
err=$(git_run --remove-parent "$p1" --parent "$p2" 2>&1); rc=$?
[ "$rc" -eq 2 ] && grep -q 'does nothing without --pointer' <<<"$err" || { echo "FAIL: --parent without --pointer (rc=$rc): $err"; fail=1; }
err=$(git_run --remove-parent= 2>&1); rc=$?
[ "$rc" -eq 2 ] && grep -q 'needs a directory' <<<"$err" || { echo "FAIL: empty --remove-parent= accepted (rc=$rc): $err"; fail=1; }
err=$(git_run --remove-parent "" 2>&1); rc=$?
[ "$rc" -eq 2 ] && grep -q 'needs a directory' <<<"$err" || { echo "FAIL: empty --remove-parent \"\" accepted (rc=$rc): $err"; fail=1; }
err=$(git_run --remove-parent "$p1" --pointer --parent "$fake_home" 2>&1); rc=$?
[ "$rc" -eq 2 ] && grep -q 'REFUSED --pointer' <<<"$err" || { echo "FAIL: refused move (rc=$rc): $err"; fail=1; }
grep -q "$vault_name:start" "$p1/AGENTS.md" && [ "$(records)" = "$p1" ] || { echo "FAIL: a refused move removed the old pointer"; fail=1; }
printf '<!-- %s:start -->\nno end marker\n' "$vault_name" > "$p2/AGENTS.md"
err=$(git_run --remove-parent "$p1" --remove-parent "$p2" 2>&1); rc=$?
[ "$rc" -ne 0 ] && grep -q 'without' <<<"$err" || { echo "FAIL: unterminated block in a later dir (rc=$rc): $err"; fail=1; }
grep -q "$vault_name:start" "$p1/AGENTS.md" || { echo "FAIL: an unterminated block in a later dir did not stop the first removal"; fail=1; }
rm "$p2/AGENTS.md"

echo "--- --remove-parent strips a block appended through a CLAUDE.md link to another file"
git_run --remove-parent "$p1" >/dev/null || { echo "FAIL: reset before CLAUDE.md link case exit $?"; fail=1; }
printf '# shared claude\n' > "$fake_parent/shared-claude.md"
ln -s "$fake_parent/shared-claude.md" "$p1/CLAUDE.md"
git_run --pointer --parent "$p1" >/dev/null || { echo "FAIL: --pointer with a linked CLAUDE.md exit $?"; fail=1; }
grep -q "$vault_name:start" "$fake_parent/shared-claude.md" || { echo "FAIL: block not appended through the CLAUDE.md link"; fail=1; }
git_run --remove-parent "$p1" >/dev/null || { echo "FAIL: --remove-parent with a linked CLAUDE.md exit $?"; fail=1; }
if grep -q "$vault_name:" "$fake_parent/shared-claude.md"; then echo "FAIL: block left in the CLAUDE.md link target"; fail=1; fi
[ -L "$p1/CLAUDE.md" ] && grep -q 'shared claude' "$fake_parent/shared-claude.md" || { echo "FAIL: the operator's CLAUDE.md link or content changed"; fail=1; }
rm -f "$p1/CLAUDE.md" "$fake_parent"/shared-claude.md*
git_run --pointer --parent "$p1" >/dev/null

echo "--- --remove-parent drops the record of a recorded dir that is gone"
git_run --pointer --parent "$p2" >/dev/null
mv "$p2" "$p2.moved"
out=$(git_run --remove-parent "$p2"); rc=$?
[ "$rc" -eq 0 ] && [ "$(records)" = "$p1" ] || { echo "FAIL: missing recorded dir not forgotten (rc=$rc): $(records) $out"; fail=1; }
mv "$p2.moved" "$p2"
git_run --remove-parent "$p2" >/dev/null || { echo "FAIL: --remove-parent of an unrecorded dir with a block exit $?"; fail=1; }
[ ! -e "$p2/AGENTS.md" ] || { echo "FAIL: --remove-parent left the block in an unrecorded dir"; fail=1; }
git_run --uninstall >/dev/null || { echo "FAIL: uninstall after --remove-parent tests exit $?"; fail=1; }
[ "$(cat "$fake_home/.codex/AGENTS.md")" = "# my codex rules" ] || { echo "FAIL: codex AGENTS.md after --remove-parent tests: $(cat "$fake_home/.codex/AGENTS.md")"; fail=1; }
rm -f "$fake_home/.codex/AGENTS.md.bak"
rm -rf "$git_parent" "$p1" "$p2" "$repo_dir"

echo "--- nothing left behind but the operator's own files"
left=$(find "$fake_home" \( -type l -o -name '*.md' \) ! -path "$fake_home/.codex/AGENTS.md" ! -name '*.bak' | wc -l | tr -d ' ')
[ "$left" -eq 0 ] || { echo "FAIL: $left install artifact(s) left under HOME"; find "$fake_home" -type l -o -name '*.md'; fail=1; }

if [ "$fail" -eq 0 ]; then echo "PASS: install-discovery dry run/--skills/--check/--pointer/--pointer-codex/--uninstall/--remove-parent"; else echo "FAIL: install-discovery"; fi
exit "$fail"
