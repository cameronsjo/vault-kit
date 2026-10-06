# Update history

## [2026-10-05] maintenance | Seed vault from vault-kit

Actor: vault-kit/seed. Created the agent contract, the `wiki/system/` pages, the page templates, the retrieval and standards runbooks, and empty section indexes. Evidence: `make check` passes on the seeded tree. Gaps: the retrieval page defers its registration commands to `make retrieval-setup`; the role list in `AGENTS.md` is unassigned.

## [2026-10-05] maintenance | Add skill templates and init-vault

Actor: vault-kit/build. Added `templates/skills/` (discover, maintain, and the maintain operation checklist), `scripts/init-vault`, and the rendered-skill check in `make check`; updated `wiki/runbooks/standards-checks.md` with that check and the `make test` suite. Evidence: `make check` and `make test` pass in template mode. Gaps: `make retrieval-setup`, named by the discover skill, arrives with the per-vault retrieval work.

## [2026-10-05] maintenance | Per-vault retrieval runbook

Actor: vault-kit/build. Rewrote `wiki/runbooks/retrieval.md` with the real commands for the per-vault QMD index in `.qmd/`: `make retrieval-setup`, `make refresh`, `make retrieval`, `make retrieval-teardown`, model download and proxy notes. Evidence: `make test-retrieval` passes lexical and semantic legs under a throwaway home directory. Gaps: QMD's model freshness check behind a blocking proxy is untested.

## [2026-10-05] maintenance | Seeding runbook and ingest procedure

Actor: vault-kit/build. Added `wiki/runbooks/seeding-a-new-vault.md` (hand-made repository inventory capture, sanitizing, first pages, re-runs) and the maintain skill's `references/ingest.md` template (hash-based, manifest-tracked ingest of a folder of docs; no script); linked it from the maintain skill and the operation checklist, listed it in `engine.manifest`, and added a "Fill a new vault" section to the README. Evidence: `gh repo list cli --limit 5 --json ...` ran read-only and returned the six fields; `GH_HOST` checked against `gh help environment`. Gaps: the GitHub Enterprise form was checked in help text only; the ingest procedure was not run against a real docs folder.

## [2026-10-05] maintenance | Refuse symlinks under wiki, raw and skills

Actor: vault-kit/build. `wiki/runbooks/standards-checks.md` now lists the symlink rule in the vault-profile check: `make check` rejects a symlink under `wiki/`, `raw/` or `skills/`, and `index-vault.py` and `init-vault` refuse to write through one. Evidence: `scripts/test-init.sh` cases for a symlinked `index.md`, `wiki/log.md` and `skills/` pass, and each goes red with its guard removed. Gaps: none known.

## [2026-10-05] maintenance | Secret-scan policy from the reviewed commit

Actor: vault-kit/build. `wiki/runbooks/standards-checks.md` now says `make secrets` defaults to the `worktree` mode and that `.gitleaks.toml` and `.gitleaksignore` are read from `HEAD`, or from the range base in CI, never from the change being scanned. Evidence: `scripts/test-hooks.py` refuses a staged `.gitleaksignore` and a staged allowlist that would silence a staged key, and a range scan ignores an ignore entry added inside the range; each case goes red when the policy is read from the scanned files. Gaps: none known.

## [2026-10-05] maintenance | Deny scan covers untracked files, path names and history

Actor: vault-kit/build. `wiki/runbooks/standards-checks.md` now says the vault-profile check reads untracked files that `.gitignore` does not exclude and path names, that the hook checks against `HEAD`'s deny list, and adds the `make deny-range` row for CI's per-commit scan of messages, path names and added lines. The maintain skill and ingest templates say the same. Evidence: `scripts/test-hooks.py` and the `check-vault.py` self-tests cover an untracked page, a staged path name, an emptied deny list, and a removed line, a path and a message inside a range; each goes red with its control removed. Gaps: other `check-vault.py` messages (name and link errors) still print the raw path.

## [2026-10-05] maintenance | CI triggers and instance check

Actor: vault-kit/build. `wiki/runbooks/standards-checks.md` now says CI runs on every pull request and every push to `main`, and runs `make check-initialized` in an initialized instance. Evidence: `actionlint` and `zizmor --offline` report nothing on `.github/workflows/check.yml`; `scripts/test-hooks.py` and `scripts/test-init.sh` exit 1 with `VAULT_KIT_REQUIRE_GITLEAKS=1` and an unverifiable gitleaks, and skip without it. Gaps: the workflow has not run on GitHub yet.

## [2026-10-05] maintenance | Agent contract scope and ingest hashes

Actor: vault-kit/build. `AGENTS.md` no longer lists "derived inventory" among what `wiki/` holds; the kit ships no inventory pages. The maintain skill's ingest template now commits only hashes of the files as committed under `raw/`, and keeps pre-sanitizing source hashes in a gitignored local state file, `.ingest-state/<slug>.json`, so a sanitized capture's original text cannot be recovered offline from its hash. Evidence: `make check` passes; `make test-init` renders the template. Gaps: the ingest procedure has still not been run against a real docs folder.

## [2026-10-06] maintenance | Standards runbook: tripwire tests and the deny-range scan

Actor: vault-kit/build. `wiki/runbooks/standards-checks.md` now lists `scripts/tripwire` among what `make test` covers, and its Provenance paragraph names the deny-range scan among the checks CI repeats for a commit made with `--no-verify`. Evidence: `make test-tripwire` passes; `.github/workflows/check.yml` runs `make deny-range` over the new commits. Gaps: none new.

## [2026-10-06] maintenance | Range scans read UTF-16 and UTF-32 text

Actor: vault-kit/build. `wiki/runbooks/standards-checks.md` now says `make deny-range` decodes a UTF-16 or UTF-32 file a commit adds or changes and scans it whole, and that gitleaks range mode cannot read such text. Evidence: `make test-tripwire` finds UTF-16 and UTF-32 text added then removed; `scripts/test-hooks.py` asserts `make deny-range` reports a removed UTF-16 note by path and pattern number. Gaps: UTF-16 without a byte-order mark is still read as binary, in the tree and in history; gitleaks range mode still misses removed UTF-16 secrets.

## [2026-10-06] maintenance | Empty indexes end after their heading

Actor: vault-kit/build. `scripts/index-vault.py` no longer writes a trailing blank line into an index with nothing to list, so `docs/plans/index.md`, `wiki/capabilities/index.md`, `wiki/doctrine/index.md`, `wiki/field-reports/index.md` and `wiki/journeys/index.md` were regenerated. Evidence: a fresh repository built from the tracked tree could not make its first commit through the hooks, because `git diff --cached --check` reported "new blank line at EOF" in those five files; `make test-init` now asserts a generated empty index passes `git diff --check`. Gaps: none new.
