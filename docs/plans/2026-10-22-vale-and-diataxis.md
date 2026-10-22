---
type: Plan
title: 'Vale prose checks and a Diátaxis lens for vault-kit'
description: 'Plan to lint vault pages and vault-kit docs with a pinned Vale, and to classify page types by Diátaxis question.'
status: draft
generated:
  by: claude-code/93d41cc1-e50e-4cf8-954d-27bd586ee6c0
  at: '2026-10-22T13:40:00-05:00'
next: "approve → Task 0 (security review of the controls) → Task 1 → PR A merged, tag v0.2.0 → Task 6 step 1 (artificer-made to v0.2.0) → Tasks 2-5 → PR B merged, tag v0.3.0 → Task 6 step 2 (artificer-made to v0.3.0)"
branch: plan/vale-diataxis
pr: "—"
updated: 2026-10-22
approved_session_id: "—"
date: 2026-10-22
session_id: 93d41cc1-e50e-4cf8-954d-27bd586ee6c0
model: claude-opus-5-5
harness: claude-code 2.1.289
machine: cf6e768835c7
---
# Vale prose checks and a Diátaxis lens for vault-kit

`status` holds the vault's OKF lifecycle value (`check-vault.py` accepts only `draft`, `stable`, or `deprecated`), so this plan's living state is carried by `next:`, `pr:`, and the PR states.

## Goal

The page writer, usually the agent following the maintain skill, gets an advisory prose check on the pages it changed. That check turns the rules in `wiki/system/writing.md` into Vale warnings. It runs on vault pages in every vault and on vault-kit's own docs. Page types are classified by the Diátaxis question each one answers, and vault-kit's README is ordered by those questions.

## Loop

Loop: none — the work adds a check and docs. Vale's alerts are printed output (and a CI step summary) with no stored state; nothing created here waits for someone to clear it.

## Concessions

4 concessions, 2 on platforms the operator owns. Highest owned: `engine-update` cannot ship Vale config, Kept reliability 3×2 = **6**, fix first. Approval files 0 issues.

| Concession | Limit, checked by | Owner | Kept | Fixed | Route |
|---|---|---|---|---|---|
| Hand-copy `.vale.ini` and the style into each vault | `engine-update` writes only `ENGINE_DIRS` (`scripts`, `templates/skills`) and `ENGINE_FILES`, and refuses the rest (`cameronsjo/vault-kit:scripts/engine-update:37-38`, main `fb6fee2`) | owned | reliability 3×2 = **6** (rules never reach existing vaults, or drift) | security 1×2 = 2 (a ref can now write Vale config; mitigated by Task 1's pre-copy content allowlist in the vault's own installed `engine-update`) | fix first — Task 1 adds `.vale.ini` and `.vale/styles/vaultkit/` as engine locations |
| Ship the engine-update change alone, one release before anything that uses it | a vault runs its own installed `engine-update`, which checks every manifest line before copying and refuses unknown locations (`scripts/engine-update:121`, `:172`); `--ref` takes a tag or branch and `--commit` must match it (`:168-170`) | owned | reliability 3×2 = **6** if shipped together (every vault's update exits 2) | n/a — the limit is by design: the script runs nothing from the fetched ref | fix first — PR A (Tasks 0-1) merges as tag `v0.2.0` and rolls out before PR B (`v0.3.0`); mitigated by Task 6's order |
| Trust the first capture of Vale's checksums | the release publishes `vale_3.24.0_checksums.txt` and no signature (asset list, `gh api repos/vale-cli/vale/releases/tags/v3.24.0`) | upstream | security 1×3 = 3 | n/a | conceded, same trust as gitleaks; mitigated by Task 2 (hash each archive locally from the tag URL and match the published file; every later run re-verifies the pin) |
| Vale config is read by editor plugins as soon as `engine-update` writes it, before the operator reviews the diff | vale-ls and editor plugins load the nearest `.vale.ini`; script rules get only Tengo `text`, `fmt`, `math` (`vale-cli/vale:internal/check/script.go:96` at `v3.24.0`), so no exec | upstream | security 1×2 = 2 | n/a | conceded; mitigated by Task 1's allowlist, checked by the vault's installed `engine-update` before it writes anything (so a refused config never lands), with `check-vault.py` as the CI backstop, and a docstring/README note |

Minor: an instance cannot add its own style without editing the engine-owned `.vale.ini` (Task 3 checks Vale 3.24's config docs for a second layer; `engine-update` shows the overwrite and stops); `wiki/` is instance-owned, so the Diátaxis classification lives in the engine-owned maintain skill and `knowledge-format.md` only carries a copy for people; the plan's living `status:` gives way to the OKF lifecycle value.

## Alternatives declined

- **alint for structure rules** — `scripts/check-vault.py` already checks names, indexes, frontmatter, and links, with tests. alint (v0.16, pre-1.0, a second binary to pin) duplicates those; its one unique use, instance-local structure rules, has no consumer.
- **A Diátaxis reorg of `wiki/`** into four directories — the type directories already answer the question, and renaming them breaks every vault's links for no reader gain. Use the questions to classify instead.
- **Vale packages (proselint `Hedging.yml`, write-good `Weasel.yml`, Microsoft, Google)** — their word lists encode other style guides, not `writing.md`. A package could be synced once and committed, but every rule would still need checking against this vault's guidance; four short rules written from `writing.md` are less to review.
- **Vale as a commit-blocking hook, or a ratchet that fails CI past N alerts** — prose rules are judgment calls, and a false block costs more than a missed hedge. The reader is the page writer (maintain skill), with a CI summary as backup.
- **A tutorial page type and template now** — no vault has a page that needs one. The classification names the gap; add the type when a vault needs onboarding by doing.

## Related

- A prior docs pass in a sibling project rejected a full Diátaxis reorg and used the questions as a classification. Context only; the decline above stands on its own reasons.

## Panel

Panel: plan-reviewer (conflicts), plan-reviewer (underspecified), security-posture-reviewer, developer-experience-reviewer, agent-experience-reviewer, cameron-review, plan-reviewer (second pass on the revision) ran — 75 findings, 74 folded in, 1 declined (see Panel review — findings declined)

Three questions the owner lens left to Cameron are answered here with the recommended option and listed in the presenting message: the style carries only rules stated in `writing.md` (two lines added to it, Task 3); no tutorial type yet (Alternatives declined); the CI step stays, as a summary over changed files.

## Panel review — findings declined

- **[Task 3] developer-experience: "the Makefile is not an engine location, so an updated vault may get no `make prose`"** — `Makefile` is in `ENGINE_FILES` (`scripts/engine-update:38`) and in `engine.manifest`, so the target ships with every engine update.

## Architecture

```text
writing.md rules ──► .vale/styles/vaultkit/*.yml   (engine-owned)
                     .vale.ini                     (engine-owned, keys allowlisted)
engine-update (installed copy) ──► allowlist on incoming .vale.ini keys and rule
                                   `extends:` kinds, before any file is copied
check-vault.py ──► same allowlist over the tree (make check, CI backstop)
scripts/vale ──► scripts/pinnedbin.py ◄── scripts/gitleaks   (one verifier)
scripts/prose ──► builds the file list, applies exclusions, skip policy,
                  runs scripts/vale --output=line
make prose [FILES=...] ──► scripts/prose
maintain skill Step 4 ──► make prose FILES="<pages you changed>"
CI ──► make prose on changed files; count to $GITHUB_STEP_SUMMARY
```

## Tech Stack

- Vale 3.24.0 (2026-10-01; archives `vale_3.24.0_{macOS_arm64,macOS_64-bit,Linux_64-bit}.tar.gz`, member `vale`, plus `vale_3.24.0_checksums.txt`; no signature asset). MIT.
- Python 3 stdlib for `scripts/pinnedbin.py`, `scripts/vale`, `scripts/prose`, matching `scripts/gitleaks`.
- Bash test scripts run by `make test`, matching the existing suites.

## Global Constraints

- `make check` and `make test` pass after every task. Every new path passes `check-vault.py`'s name rule (lowercase, digits, `-` and `.`; no underscores or capitals).
- A pinned binary fails closed on integrity: a checksum mismatch, a planted cache, or a `*_BIN` whose version output is not the exact expected string exits 2. The one escape is the tool's existing allow-unpinned variable (`GITLEAKS_ALLOW_UNPINNED`, which runs with a loud warning); Vale gets none.
- Availability is advisory for Vale only: `scripts/vale` exits **3** when no verified Vale can be obtained (download failed, no pin for the platform) and **2** on any integrity failure. `scripts/prose` turns exit 3 into one line naming the cause and exit 0, unless `VAULT_KIT_REQUIRE_VALE=1` (CI sets it), and passes exit 2 through. gitleaks keeps exit 2 for both, since the secret scan fails closed.
- No Vale rule ships at `error` level, so Vale's own findings never fail a run.
- `raw/` and `wiki/log.md` are never linted, whatever `FILES=` names.
- `scripts/gitleaks` keeps its `VERSION = "x.y.z"` line, its cache layout `<tool>-<version>/<tool>`, and every refusal text `scripts/test-hooks.py` asserts ("not the pinned", "checksum mismatch for cached", "The secret scan fails closed", `GITLEAKS_BIN` in the offline hint), byte for byte; the shared module builds each text from per-tool fields. `scripts/vale` has its own `VERSION = "3.24.0"` line. No step edits `scripts/test-hooks.py` or the CI version grep to make the refactor pass.
- Every engine file added is listed in `engine.manifest`; `engine-update` accepts nothing outside its engine locations.
- Commits carry the producer tuple; every change to `wiki/` appends a `wiki/log.md` entry; `make indexes` before each commit that adds a page.

## Orchestrator

**Driver:** opus — trigger: Tasks 0-2 review and refactor the checksum-verified download the secret scan depends on, and widen what `engine-update` may write in every vault; security findings feed back.

---

## Tasks

### Task 0 — Security review of the controls before changing them

**Files:** none changed; report only.

**Dispatch:** fresh independent security reviewer · Opus

**Report:** `<panel-dir>/task0-security.md`, out of tree

**Steps:**
- [ ] Review the file set as it stands on main: `scripts/gitleaks`, `scripts/scan-secrets.py`, `scripts/check-staged.py`, `.githooks/pre-commit`, `scripts/engine-update`, `scripts/vaultconf.py` (`symlink_component`, `checked_base`), `.github/workflows/check.yml`. Neither `scripts/gitleaks` nor `scripts/engine-update` has had a PR review
- [ ] Fix Critical and Important findings in PR A, or file each one on cameronsjo/vault-kit with the reason it waits

### Task 1 — Engine locations for Vale config, with a content allowlist (PR A)

**Files:**
- Modify: `scripts/engine-update`, `scripts/vaultconf.py`, `scripts/check-vault.py`, `scripts/test-engine-update.sh`, `README.md` (Engine update section)

**Interfaces:**
- Produces: `.vale.ini` and every file under `.vale/styles/vaultkit/` are engine locations. One allowlist function (in `scripts/vaultconf.py`, which both scripts import) refuses, and `engine-update` runs it on the fetched ref's files before copying anything while `check-vault.py` runs it on the tree. It refuses a `.vale.ini` whose keys fall outside the allowlist (`StylesPath` equal to `.vale/styles`, `MinAlertLevel`, and per-glob `BasedOnStyles`, `TokenIgnores`, `BlockIgnores`), and a `.vale/styles/**/*.yml` whose `extends:` is not one of `existence`, `substitution`, `occurrence`, `repetition`, `consistency`, `conditional`, `capitalization`, `metric`, `sequence`. Parsing: `configparser` over the text with a synthetic `[*root*]` header prepended, so keys before the first section are read (plain `configparser` raises `MissingSectionHeaderError` on them); a parse error is a refusal

**Dispatch:** In-context · Opus

**Report:** —

**Steps:**
- [ ] Tests first: a manifest listing `.vale.ini` and `.vale/styles/vaultkit/hedging.yml` updates both; `.vale/other.yml` and `.vale/styles/config/x.txt` are refused. A fetched ref whose `.vale.ini` has `Packages`, `[formats]`, `Transform`, or an absolute or `..` `StylesPath`, or whose rule has `extends: script`, makes `engine-update` exit 2 with nothing copied; `make check` refuses the same files in a tree. Run, expect RED
- [ ] Implement; docstring and README say Vale config is read by editor plugins as soon as it is written, and what the allowlist holds
- [ ] GREEN; stage one break per refusal and confirm each goes red
- [ ] `make indexes` (this plan's page), commit: `feat(engine-update): ship Vale config as engine files; allowlist its contents`
- [ ] Polish; open PR A (Tasks 0-1 and this plan). Cameron merges; tag the merge commit `v0.2.0` and push the tag

### Task 2 — Shared verifier and the pinned Vale wrapper (PR B)

**Files:**
- Create: `scripts/pinnedbin.py`, `scripts/vale`, `scripts/test-vale.sh`
- Modify: `scripts/gitleaks`, `engine.manifest`, `Makefile` (`test-vale` in `test:` and `.PHONY`), `.github/workflows/check.yml` (cache key includes the Vale version; `VAULT_KIT_REQUIRE_VALE: '1'` in the job env)

**Interfaces:**
- Produces: `pinnedbin.resolve(spec: ToolSpec) -> str`, where `ToolSpec` is a frozen dataclass: `name`, `version`, `release_url`, `archives` (platform → archive name), `pins` (platform → `{archive, binary}` SHA-256), `member`, `env_prefix` (`GITLEAKS`, `VALE`), `version_args` (`["version"]`, `["--version"]`), `version_output` (exact expected stdout, stripped: `8.30.1`, `vale version 3.24.0`), `allow_unpinned_env` (`GITLEAKS_ALLOW_UNPINNED`; `None` for Vale), `install_hint`, `unavailable_exit` (2 for gitleaks, 3 for Vale). The return value keeps today's `resolve()` contract (`*_BIN` returned as given). Two exception types inside the module, `Unavailable` (download failed, no pin) and `Integrity` (checksum mismatch, planted cache, missing archive member, version mismatch); each wrapper maps them to exits. Refusal texts are built from per-tool fields so gitleaks' asserted wording stays byte for byte (Global Constraints); Vale's texts say which case it is, and an integrity text ends "do not retry, report it". Before a first-run download the module prints `downloading <name> <version> to <cache dir>` on stderr. `scripts/vale <args>` passes every argument to the verified binary; `--vault-resolve` prints its path

**Dispatch:** In-context · Opus (supply-chain verification, U9)

**Report:** —

**Steps:**
- [ ] Add `scripts/pinnedbin.py` to `engine.manifest` first (the hook tests copy only manifest entries). Move gitleaks' platform detection, cache, download, archive verify, and binary re-verify into it. A failed import in `scripts/gitleaks` exits 2 with the install hint, never 1 ("leaks found"). Run `make test-hooks test-init` before any Vale work: they pass unchanged
- [ ] Capture pins: for each platform, download from `https://github.com/vale-cli/vale/releases/download/v3.24.0/<archive>`, hash locally, match the line in `vale_3.24.0_checksums.txt` from the same tag, extract member `vale`, hash it. Paste the commands and their output into this step when ticking it. Read the 3.24.0 release notes for security fixes; record the result
- [ ] `scripts/vale` built on `ToolSpec`
- [ ] `scripts/test-vale.sh`, each case with its own `XDG_CACHE_HOME`: a tampered archive from a local `VALE_DOWNLOAD_BASE` exits 2 and caches nothing; an archive without a `vale` member exits 2; a planted cached binary exits 2 and never runs; `VALE_BIN` stubs printing `vale version 3.24.0-evil` and `vale version 3.24.01` exit 2; an unreachable `VALE_DOWNLOAD_BASE` exits 3 with the `download failed` text; the first-run download prints the `downloading` line; a genuine resolve returns a path whose `--version` prints `vale version 3.24.0`. The genuine case prints `SKIP` when offline, unless `VAULT_KIT_REQUIRE_VALE=1`, then fails. Stage breaks of the archive check and the cache re-verify; confirm red
- [ ] Commit: `feat(scripts): pinned vale wrapper on a verifier shared with gitleaks`

### Task 3 — Rules, `scripts/prose`, and `make prose` (PR B)

**Files:**
- Create: `.vale.ini`, `.vale/styles/vaultkit/{unproven.yml,filler.yml,sentence-length.yml}`, `scripts/prose`, `scripts/test-prose.sh`
- Modify: `wiki/system/writing.md`, `wiki/log.md`, `Makefile` (`prose`, `test-prose` in `test:` and `.PHONY`), `.github/workflows/check.yml`, `engine.manifest`, `README.md` (Day to day), `wiki/runbooks/standards-checks.md`

**Interfaces:**
- Consumes: `scripts/vale` (Task 2); engine locations and allowlist (Task 1, merged)
- Produces: `make prose [FILES="a.md b.md"]` → `scripts/prose`, which prints one `path:line:col:rule:message` record per alert (`--output=line --no-wrap`) and a final `N alerts in M files` line; exit 0, except 2 on an integrity failure or when Vale itself errors, and 2 on unavailability only under `VAULT_KIT_REQUIRE_VALE=1`. Files named in `FILES=` that do not exist are dropped with a note

**Dispatch:** Serial (after Task 2) · In-context · Opus

**Report:** —

**Steps:**
- [ ] Add the two rules `writing.md` does not yet state, under Style: "Cut filler phrases (worth noting, it is important to note, in order to, basically)." and "Keep a sentence under about 35 words." Log entry. Every rule below now cites a `writing.md` line
- [ ] Check Vale 3.24's config docs: a second config layer (record in the Minor concession and `## Deviations`), and whether frontmatter and `[[wikilinks]]` are skipped in Markdown (add `TokenIgnores` for wikilinks if not)
- [ ] Rules, all `warning` except sentence length (`suggestion`): `unproven` (existence: "should work", "probably works", "seems to work", "hopefully works"; from "A README or a plan does not prove something works"; leaves "might" alone, since limitation sections need it), `filler`, `sentence-length` (occurrence, `scope: sentence`, max 35 tokens)
- [ ] `.vale.ini`: `StylesPath = .vale/styles`, `MinAlertLevel = suggestion`, `[*.md] BasedOnStyles = vaultkit`. No `Vocab` (no rule reads one)
- [ ] `scripts/prose`: default list from `git ls-files -- 'wiki/*.md' 'docs/*.md' README.md AGENTS.md` (git pathspec `*` crosses `/`), or `FILES=`; drop `raw/**` and `wiki/log.md` from either; empty list prints `0 files` and exits 0
- [ ] `scripts/test-prose.sh`, all through `make prose` in one Vale run over a fixture vault: each rule's trigger page gives exactly its rule's record; a clean page with frontmatter and wikilinks gives none; `FILES=raw/x.md` and `FILES=wiki/log.md` give `0 files`; a page in `wiki/a/b/` deep is linted; `Do not store credentials.` gives none; a `VALE_DOWNLOAD_BASE` stub that makes `scripts/vale` exit 3 gives exit 0 with the skip line, and exit 2 under `VAULT_KIT_REQUIRE_VALE=1`; a tampered archive gives exit 2 either way. Stage a break per rule; confirm red. Measure warm runtime; budget under 10 s added to `make test`
- [ ] Run `make prose` over vault-kit; record per-rule counts in `## Learnings`; when more than half of a rule's hits are wrong, narrow the rule and record before/after
- [ ] CI step after the `base` step (`check.yml`): with a base, `make prose FILES="$(git diff --name-only --diff-filter=d "$BASE" HEAD -- '*.md')"`; when the base step sets `skip` (first push), plain `make prose` over the default list. Append the count line to `$GITHUB_STEP_SUMMARY`
- [ ] Commit: `feat(prose): vaultkit Vale style and make prose`

### Task 4 — Tell the page writer, and classify by Diátaxis question (PR B)

**Files:**
- Modify: `templates/skills/maintain/skill.md.tmpl` (Step 2 table, Step 4), `templates/skills/maintain/references/operation-checklist.md.tmpl`, `wiki/system/knowledge-format.md`, `AGENTS.md` (§ Before you commit, three words), `wiki/log.md`

**Dispatch:** In-context · Opus

**Report:** —

**Steps:**
- [ ] Step 2 table (`skill.md.tmpl:47-55`) gains a "question it answers" column on its existing rows: capability → look something up; journey → understand why (it explains how one outcome flows across parts; its steps live in runbooks); runbook → do a task; doctrine → understand why; system → look something up (the vault's own contract); raw → none (evidence, not a page); field report → understand why. Under the table, two sentences: "No page type answers learn-by-doing yet; write a runbook and say in its first line that it walks a newcomer through. A page that answers two questions becomes two linked pages."
- [ ] Step 4 becomes `make indexes && make check && make prose FILES="<pages you wrote or edited>"`, then: "`make prose` prints Vale warnings from `wiki/system/writing.md`, one `path:line:col:rule:message` per line. They never block. Fix a warning in a page you changed unless the wording is quoted or required, and wrap a quoted passage in `<!-- vale off -->` / `<!-- vale on -->`; leave alerts in other pages. Exit 2 means Vale could not be verified: report the stderr line and continue." The ingest, query, and lint checklist lines that run `make check` gain the same `make prose` call. The tool-surface line (`skill.md.tmpl:14`) adds `prose` to its make targets
- [ ] `knowledge-format.md` gets the same table for people, with a pointer to the skill as the source; `AGENTS.md:45` names "`make prose` (advisory)"
- [ ] Verify in template mode: `make test-init` (it renders the skills; `make render-skills` refuses in the template) and `make check`; log entry
- [ ] Commit: `feat(maintain): classify pages by Diátaxis question; run make prose on changed pages`

### Task 5 — README ordered by question (PR B)

**Files:**
- Modify: `README.md`

**Dispatch:** In-context · Opus

**Report:** —

**Steps:**
- [ ] Reorder the existing H2 sections, with no new heading levels and no renamed headings (anchors stay valid): Set up (Prerequisites, Quickstart, Fill a new vault); Daily use (Day to day, Updating, Teardown); Reference (Layout, Which harnesses read the pointer, Blueprint); Background (Multi-project use and trust, Sibling vault); License last. A five-line map under the title names each group and its sections in plain words. Cross-link `## Updating` and `### Engine update`
- [ ] Verify nothing was lost: `diff <(git show HEAD:README.md | grep -v '^$' | sort) <(grep -v '^$' README.md | sort)` shows only the map lines and the cross-link. `grep -rn 'README.md#' scripts wiki templates AGENTS.md` finds no broken anchor
- [ ] `make prose FILES=README.md`; fix only alerts in the new lines
- [ ] Commit: `docs(readme): order sections by the question they answer`
- [ ] Run the pre-PR review pass over PR B; its independent Opus security review must cover `scripts/pinnedbin.py`, `scripts/vale`, `scripts/prose`, `scripts/gitleaks`, `.vale.ini`, and `.vale/styles/vaultkit/`; fold findings; open PR B. Cameron merges; tag the merge commit `v0.3.0` and push the tag

### Task 6 — Roll out to artificer-made

**Files:**
- Modify (in `artificermade/artificer-made`): engine files via `scripts/engine-update`

**Dispatch:** Serial (step 1 after `v0.2.0`, step 2 after `v0.3.0` and step 1's PR merge) · In-context

**Report:** —

**Steps:**
- [ ] After `v0.2.0` exists: `scripts/engine-update --ref v0.2.0 --commit <its sha>` in a worktree; `make check`; PR (Cameron merges). This installs the engine-update that accepts `.vale*` and checks its contents
- [ ] After `v0.3.0` exists and step 1's PR merged: `scripts/engine-update --ref v0.3.0 --commit <its sha>`; `make render-skills && make check && make prose`; record the alert count; PR (Cameron merges)

## Deviations

## Learnings
