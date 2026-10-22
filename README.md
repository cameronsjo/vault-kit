---
type: Reference
title: 'vault-kit'
description: 'A template for a shared, agent-readable knowledge vault with enforced standards, plus a blueprint for rebuilding it.'
status: draft
generated:
  by: vault-kit/build
  at: '2026-10-05T15:26:05-05:00'
---
# vault-kit

vault-kit is a template for one Obsidian-compatible Git repository that holds shared knowledge for several projects. Coding agents (Claude Code, Codex, Pi) and people read and maintain it. The rules that keep it trustworthy are enforced in code, not left to habit: raw source captures cannot change, the change log can only grow, every page has required metadata, and a secret scan blocks credentials and any names you list as private.

This README has two jobs. It is a quickstart for setting up a vault on a locked-down work Mac under your employer's GitHub organization. It is also a blueprint: each part is described by what it does and the rule it enforces, so you can rebuild it without access to the code.

## Layout

```text
vault.toml                  name, title, scope, root_env, [redaction] deny; template = true until init
engine.manifest             paths vault-kit owns; make engine-update overwrites only these
AGENTS.md                   instructions for every agent and person; CLAUDE.md is a symlink to it
README.md  LICENSE          this file; Apache-2.0
Makefile                    every command you run
requirements-dev.txt        PyYAML, pinned
.gitleaks.toml              secret-scan config for this vault (vault-owned, not updated by the engine)
.githooks/                  pre-commit, pre-merge-commit, and the chain pass-through
.github/workflows/check.yml CI
.github/CODEOWNERS          code owners: every path except content (an allowlist)
.obsidian/                  app, core-plugin and template settings; Sync is off
scripts/                    all code: checks, init, install, retrieval, outline, engine update, tests
templates/skills/           templates for the two agent skills
skills/                     rendered skills, created by init (<name>-discover, <name>-maintain)
raw/                        immutable source captures (created with the first capture)
docs/plans/                 implementation plans
wiki/                       maintained knowledge
  index.md  log.md          the entry point and the append-only change log
  system/                   how the vault works and how to write for it
  templates/                page templates
  runbooks/                 how-to pages, including retrieval, standards checks and seeding a new vault
  capabilities/ journeys/ doctrine/ field-reports/
.qmd/                       the search index for this vault (gitignored, created by make retrieval-setup)
.venv/                      the Python virtual environment (gitignored, created by make setup; never commit it)
```

## Prerequisites

You need these on the machine that holds the vault.

- Python 3.11 or newer. Check with `python3 --version`. If your system Python is older, install `python3.12` and run `make setup SETUP_PYTHON=python3.12`. Every script checks this first and exits 2 with the fix if Python is too old.
- PyYAML, from the pinned requirements file. `make setup` creates a virtual environment in `.venv/` (gitignored) and installs `requirements-dev.txt` into it, so nothing is installed outside the repository; Homebrew's Python refuses a global `pip install` (PEP 668). The Makefile, the hooks and the scripts ask `scripts/venv-python` which interpreter to run. It names `.venv/bin/python3` only when nothing under `.venv` is tracked in the checkout, `.venv` is a real directory rather than a symlink, and the interpreter is executable; a Git worktree without its own `.venv` uses the primary checkout's under the same rules. Otherwise they run `python3` from `PATH`. A committed `.venv` would let a pull replace the interpreter every check runs on, so `make check` and the hooks refuse a tracked `.venv` (`.venv must not be tracked`). When the venv is in use, `make` also puts its `bin/` first on `PATH`; it never does so otherwise. A script started with an interpreter that lacks PyYAML or is too old re-runs itself under the interpreter `scripts/venv-python` names, when it names one. Without `.venv`, scripts exit 2 and tell you to run `make setup`.
- QMD, the local search tool: `npm i -g @tobilu/qmd@2.8`. It brings its own Node runtime; set `QMD_NODE` to use a different Node.
- gitleaks 8.30.1 for the secret scan. You do not install it. `scripts/gitleaks` downloads the pinned release on first use, checks its SHA-256, and caches it under `${XDG_CACHE_HOME:-$HOME/.cache}/vault-kit/`. Pinned builds exist for macOS on arm64 and x64 and for Linux on x64. There is no pinned build for Linux on arm64, Windows, or anything else. On those, or where downloads are blocked, install gitleaks 8.30.1 yourself and set `GITLEAKS_BIN=<path>`; the wrapper refuses a binary whose `version` is not 8.30.1 unless you also set `GITLEAKS_ALLOW_UNPINNED=1`, which runs it with a loud warning. CI never sets that. `GITLEAKS_DOWNLOAD_BASE=<url>` points the download at an internal mirror, and the checksums still apply.
- `gh` (GitHub CLI), `make`, and Git 2.38 or newer. The history check uses `git merge-tree --write-tree`, which needs 2.38.

Embedding models. `qmd embed`, `vsearch` and `query` need GGUF models, which QMD downloads from huggingface.co on first use into `$XDG_CACHE_HOME/qmd/models` (default `~/.cache/qmd/models`). The cache is shared by every vault on the machine and holds models, not vault content. Expect about 330 MB for embeddings; `query` also pulls a 640 MB reranker and a 1.3 GB query-expansion model. `qmd search` needs none of them.

Behind a proxy or offline:

- `HF_ENDPOINT=<mirror>` is documented by QMD (`qmd doctor`) and read by its bundled download library. QMD's own freshness check of a cached model still contacts huggingface.co directly in 2.8.3; whether that works behind a blocking proxy was not tested.
- Copy the three `.gguf` files from a machine that has them into the models directory, or point `QMD_EMBED_MODEL`, `QMD_RERANK_MODEL` and `QMD_GENERATE_MODEL` at local files.
- Or stay lexical: `make retrieval-setup REFRESH_FLAGS=--lexical-only` builds a keyword index with no model download.

## Quickstart

1. On GitHub, open this repository and choose "Use this template". Create the new repository under your employer's organization and make it private.
2. Clone it, then work from that clone. Run every command below from the directory you cloned into, not from a Git worktree: the pointer and skill links would dangle when the worktree is removed, and `install-discovery` refuses to run in one.
3. Set up: `make setup`. It creates `.venv/`, installs `requirements-dev.txt` into it, and installs the Git hooks (see Git hooks). If `python3` is older than 3.11, run `make setup SETUP_PYTHON=python3.12`.
4. Initialize the vault. The slug is lowercase kebab-case, at most 31 characters, and starts with a letter. It names the skills and the search collection.

   ```bash
   scripts/init-vault --name acme-eng --title "Acme Engineering Vault" --scope "Acme engineering projects and platform services"
   ```

   The last line is `PASS: initialized <name> at <root>`.
5. Tell the skills where the vault is. The variable name is the slug in upper case with `_` for each non-alphanumeric run, plus `_ROOT`. For `acme-eng` it is `ACME_ENG_ROOT`. Add the line to your shell profile.

   ```bash
   export ACME_ENG_ROOT=/path/to/your/clone
   ```

6. Check the tree: `make check`.
7. Build the search index: `make retrieval-setup`. Add `REFRESH_FLAGS=--lexical-only` to skip the model download.
8. Preview what discovery will write. This prints the target paths and writes nothing. Read the list.

   ```bash
   scripts/install-discovery
   ```

9. Install the pointer and the skills.

   ```bash
   scripts/install-discovery --pointer --skills
   ```

   If you use Codex, add `--pointer-codex` (see Which harnesses read the pointer).

10. Commit the result and push. The pre-commit hook runs the checks on the staged files.

Then finish the setup that makes the vault safe to share:

- Fill `[redaction] deny` in `vault.toml` with a regex for each name that must never appear in the vault: internal hostnames, unreleased product names, customer names. The file has a commented example. Treat the list itself as sensitive (see Multi-project use and trust).
- Replace `@your-org/vault-owners` in `.github/CODEOWNERS` with the people or team who own the vault.
- Protect `main` in the repository settings: require the `check` job of the `Vault standards` workflow to pass, and require review from code owners.
- Turn on push protection and secret scanning for the organization or repository, if your plan offers them. They are a second line behind the local scan.
- Replace the line `No team tools are assigned roles yet.` in `AGENTS.md` once you know which tools do which jobs.

## Fill a new vault

A new vault is empty. [Fill a new vault on day one](wiki/runbooks/seeding-a-new-vault.md) shows how to capture a repository inventory by hand, sanitize it, and write the first capability cards, journeys and runbooks. It involves no seeding script. For a folder of existing docs, the maintain skill carries an ingest procedure.

## Which harnesses read the pointer

`--pointer` writes a marked block into `AGENTS.md` (and `CLAUDE.md`) in the directory above the vault. Each project under that directory is its own git repo, so the block sits above every project's git root. Measured on 2026-10-05 with a random token in the parent file, from a project root and from a subdirectory:

| Harness | Version | Reads the parent block |
|---|---|---|
| Claude Code | 2.1.289 | yes, through `CLAUDE.md` |
| Pi | 1.0.2 | yes |
| Codex CLI | 0.160.0 | no; it reads `AGENTS.md` only from the git root down |

For Codex, also run `scripts/install-discovery --pointer-codex`. It writes the same block into `~/.codex/AGENTS.md`, Codex's per-user instructions file, so every Codex session on the machine sees it. That file was not part of the measurement above; confirm it on your machine by asking a Codex session in a project to quote the block. The skills themselves are installed for all three harnesses by `--skills`, whatever the pointer does.

## Blueprint

Each subsection says what the part does, the rule it enforces, and why. All scripts are in `scripts/` and run from the vault root.

### Configuration, preflight and template mode

`vault.toml` is the single configuration file. Every script reads it at run time; nothing is rewritten across the tree. Keys: `template` (true or false), `name`, `title`, `scope`, `root_env`, and a `[redaction]` table with `deny`, a list of regex strings. If `root_env` is empty it is derived from `name` as upper case with each run of non-alphanumeric characters turned into `_`, plus `_ROOT`.

`scripts/vaultconf.py` loads it and every other Python script imports it first. Loading runs a preflight before anything else: Python below 3.11, or a missing PyYAML, first re-runs the script under the `.venv` interpreter `scripts/venv-python` names (see Prerequisites), when it names one. Otherwise Python below 3.11 exits 2 with `vault-kit needs Python >= 3.11 (found X.Y.Z); run make setup SETUP_PYTHON=python3.12 to build .venv with a newer one`, and a missing PyYAML exits 2 with `PyYAML missing; run make setup, which installs requirements-dev.txt into .venv (scripts switch to .venv/bin/python3 when it exists)`. Loading also rejects a `deny` that is not a list of strings, and a pattern that is not a valid regex, naming the pattern by number only.

Identity rules, enforced when skills are rendered: the name matches `^[a-z][a-z0-9]*(-[a-z0-9]+)*$` and is at most 31 characters; title is at most 64 characters and scope at most 160, each one line of printable ASCII and Latin-1 letters (so no invisible filler such as U+3164 or U+2800, and no format characters) with none of the characters `` ` " \ $ { } < > | ``; scope is one clause with no `;`; `root_env` matches `^[A-Z][A-Z0-9_]*$`.

In the template repository `template = true` and `name` is empty. In that mode `make check` still validates content but skips the rendered-skill check, and anything that needs an identity fails with `vault.toml: template = true and name unset; run scripts/init-vault --name <slug> --title "<Title>" --scope "<scope>"`. `make check-initialized` is the explicit gate for that: it fails in template mode. `scripts/retrieval-setup` (behind `make retrieval-setup` and `make retrieval-teardown`) runs the same check itself, so it refuses in template mode however it is started.

### Immutable raw captures and the append-only log

`raw/` holds source captures: the provider's own wording and data, with no conclusions written in. `wiki/log.md` is the change log. `scripts/check-history.py` enforces both rules against Git, in three modes:

- `--staged` compares the index with `HEAD` (with the empty tree when there is no `HEAD` yet). The pre-commit hooks use it.
- `--base <commit> [--head <ref>]` compares committed history; `--head` defaults to `HEAD`. CI uses it. A base that is all zeros is read as the empty tree.
- `--resolve-merge` writes the log a merge needs (see below).

Every run first executes the script's own self-tests, which assert each rule below with synthetic logs.

What it rejects:

- Any modified, deleted, or type-changed file under `raw/`, with the message `Existing raw captures are immutable; add a new dated capture instead.` Renames are not detected (`--no-renames`), so a rename counts as a delete plus an add and is rejected. Submodule changes are not ignored.
- A `wiki/log.md` whose old bytes are not an exact prefix of the new bytes: `wiki/log.md is append-only; preserve the previous bytes.` A log that did not exist before may start with anything.
- A change to any file under `raw/` or `wiki/` (other than the log itself), or to `AGENTS.md` or `CLAUDE.md`, with no change to the log: `Source, wiki, or agent-schema changes require an appended wiki/log.md entry.`
- An appended log section with no heading of the form `## [YYYY-MM-DD] <operation> | <title>`, where the operation is exactly one of `ingest`, `query`, `lint`, `maintenance`. At least one such heading must appear in the appended text.
- Staged mode also fails when `wiki/log.md` has edits that are not staged, and prints a reminder to `git add` it.

Merges of the default branch into a feature branch get a second rule, because two branches that both append to the log cannot both keep it as a byte prefix. A merge qualifies only when all of these hold: exactly one other parent is named in `MERGE_HEAD`; that commit is an ancestor of the remote default branch (`refs/remotes/origin/HEAD`, or `origin/main` if that is unset); the current branch does not already contain it; its log is an earlier state of the default branch's log; and `git merge-tree --write-tree` (Git 2.38 or newer) can compute Git's own merge. If any condition fails, the ordinary rule applies and the error says why. Merge handling applies only to `--staged`; a range check in CI reads committed history with no merge in progress.

When the merge rule applies, the staged log must start with exactly this: the default branch's log, then the entries this branch has that the default branch lacks, in their original order. Entries are split at the blank line before each `## [` heading. An entry present on both sides is kept once, and a repeated entry is not collapsed. After that prefix the branch may append its own new entries, and each addition needs a valid heading. If the two logs open differently, or hold different text under one heading (an entry that grew on one side), there is no automatic log. Then both rules must hold at once, which only a branch whose log already extends the default branch's can satisfy; otherwise abort the merge and rebuild the branch on the default branch. Raw captures are checked against every parent of the merge, so a capture changed on either side fails. Paths Git could not merge unaided, or that are staged as something other than its merge, still owe a log entry after the merged log; generated indexes are exempt from that. A `MERGE_HEAD` that does not hold full commit ids one per line, or names a commit Git cannot read, is a hard error.

`make merge-log` (`check-history.py --resolve-merge`) writes the expected log. It refuses if any conflicted file other than the log and generated indexes is unresolved, if the log is reached through a symlink, or if it cannot confirm the merged-in commit is the default branch. Then run `make indexes`, `git add` both, and append one entry describing any page you resolved by hand.

In CI the base commit is chosen by event, in `.github/workflows/check.yml`:

- A pull request uses the pull request's base SHA.
- A push to the default branch uses the commit the branch pointed at before the push. If that is all zeros (the first push), the history check is skipped with a printed reason, and the secret scan covers all of history instead.
- Any other push (the workflow only triggers on pushes to `main`, so this is a fallback) uses the merge-base of `refs/remotes/origin/<default>`, fetched by the full-history checkout, and `HEAD`. The pre-push tip would fail on a branch that merged the default branch back into itself.

The checkout uses full history (`fetch-depth: 0`), and the event values reach the shell through `env:` and are quoted, never interpolated into the script text.

### Metadata, links, names and indexes

`scripts/check-vault.py` validates the working tree: every tracked file plus every untracked file that `.gitignore` does not exclude (`git ls-files --cached --others --exclude-standard`), so a new page is checked before `git add` and an ignored `.DS_Store` is not. In the hook's staged snapshot, which has no `.git`, it reads every file. `make check` runs it first.

- Names. Every file and directory name is lowercase kebab-case: each path part matches `\.?[a-z0-9]+(?:[-.][a-z0-9]+)*`. Established filenames are exempt (`AGENTS.md`, `CLAUDE.md`, `README.md`, `LICENSE`, `CODEOWNERS`, `Makefile`, `CHANGELOG.md`, and a short list of similar convention names). `SKILL.md` is exempt only under `skills/`. Two tracked paths that differ only by case are rejected. An agent instruction file (`AGENTS.md`, `AGENTS.override.md`, `CLAUDE.md`, `CLAUDE.local.md`, `GEMINI.md`, in any letter case) is allowed only at the repository root and under `skills/`: agent harnesses load one from any directory they work in, and code-owner review does not cover the content directories. Obsidian names a pasted image `Pasted image <timestamp>.png`, which fails this rule (a capital letter and spaces). Core Obsidian has no setting for that name, so rename the file before you commit (right-click it in Obsidian and choose Rename, which updates the links), for example to `raw/assets/2026-10-05-deploy-diagram.png`, or use a community plugin that names pasted files for you. Ignored: `.git`, `__pycache__`, `.venv`, `.claude`, `.worktrees`, `.obsidian/themes`, `.obsidian/plugins`.
- `CLAUDE.md` must be a relative symlink to `AGENTS.md` when `AGENTS.md` exists.
- Symlinks. No symlink is allowed anywhere under `wiki/`, `raw/` or `skills/`; `CLAUDE.md` at the root is the one sanctioned link. The scripts that write into the vault (`index-vault.py`, `init-vault`) also refuse a destination when it, or any directory between it and the vault root, is a symlink, and they write through a temporary file and a rename. A committed symlink would otherwise send a write outside the clone.
- Frontmatter on every Markdown page except the exempt kinds below: string `type`, `title` and `description`; `status` one of `draft`, `stable`, `deprecated`; `tags`, if present, a list of strings; `generated` and `verified`, if present, entries with a `by` of the form `human:<id>`, `process:<id>` or `<tool>/<id>` and an optional timestamp (required for `verified`); timestamps need an explicit UTC offset; `sources`, if present, a list of entries with a string `resource`. Unknown keys are kept, not rejected.
- Exempt kinds: `index.md` files carry no frontmatter except the root one, which must declare `okf_version: "0.2"`; `log.md` carries none; Markdown under `raw/`, `skills/`, `apps/`, `templates/` and any dot-directory is outside the metadata and index rules (names, credential URLs and deny patterns still apply to them).
- Links. Every local Markdown link must resolve to an existing path inside the vault. Links inside fenced code blocks are ignored.
- Every directory that holds a page has an `index.md`.

`scripts/index-vault.py` generates those `index.md` files from each page's `title` and `description`, one line per child page and subdirectory. `make indexes` writes them; `make check` runs it with `--check` and fails on a stale index. `scripts/index-vault.py --title "<Title>"` overrides the root heading, which `init-vault` uses before `vault.toml` exists.

### Redaction floor

The floor keeps credentials and your private names out of the repository, and it runs on every commit and every CI run.

- The deny list. `[redaction] deny` in `vault.toml` is a list of regexes, matched case-insensitively against the content of every non-binary file `make check` reads (tracked, plus untracked and not ignored) and against every one of those path names. A file that starts with a UTF-16 or UTF-32 byte-order mark is decoded as such and scanned. Otherwise a file is binary if its first 8192 bytes contain a NUL, and is skipped (Obsidian attachments live in `raw/assets/`); other files are read as UTF-8 with undecodable bytes kept as placeholders, so a file in another encoding cannot hide an ASCII match. A symlink is never followed (it could point outside the vault), but its target text is scanned like a one-line file; the file it points at is scanned when it is listed itself. `vault.toml`'s content is exempt from the deny scan only, because it holds the patterns.
- Which list. `make check` uses the working tree's `vault.toml`. The hooks use `HEAD`'s, so a commit that empties or narrows `[redaction] deny` is still checked against the list it removes; the change takes effect from the next commit. A first commit has no `HEAD` and uses its own list.
- What it prints. A content hit prints `<path>:<line>: matches redaction deny pattern <N>`, where N counts from 1, and a path hit prints the path with each match replaced by `[redaction deny pattern N]`. It never prints the pattern or the matched text, because the list says what must stay private and CI logs are widely readable. A bad regex is reported by number and position only.
- History. `make deny-range` (`check-vault.py --deny-range`) applies the deny list to every commit in `SECRETS_BASE..HEAD`, one commit at a time: the commit message, the path names it touches, and the lines it adds, read with `--text` so a committed `.gitattributes` (`-diff`, `binary`) cannot hide them. A patch line of a UTF-16 or UTF-32 file holds a NUL between its ASCII characters and cannot match, so each such file (one with a byte-order mark) a commit adds or changes is decoded and scanned whole. A hit in an intermediate commit counts even when a later commit removed the text, because the text stays in the history that merges. It uses the base commit's deny list (with no base, `HEAD`'s), so emptying the list inside the range does not help. CI runs it on every pull request and every push to `main`. `SECRETS_BASE` follows the same rules as the secret scan.
- Credential URLs. A URL of any scheme with a user and password before the host (`<scheme>://user:password@`, so `https`, `ftp`, `postgres`, `redis` and the rest) fails in any non-binary file, even with an empty deny list.
- No suffix filter. The scan covers `.toml`, `.py`, `.json` and every other text file, not just Markdown.
- gitleaks. `scripts/gitleaks` runs gitleaks 8.30.1, pinned by SHA-256 of the release archive and, separately, of the binary inside it, and it re-checks the binary hash on every run, including a cached copy. Order: `GITLEAKS_BIN` if set, and only if `<bin> version` prints `8.30.1` (otherwise exit 2; `GITLEAKS_ALLOW_UNPINNED=1` runs it anyway with a loud warning, and CI never sets it); else the verified cached copy under `${XDG_CACHE_HOME:-$HOME/.cache}/vault-kit/gitleaks-<version>/`; else a download of the pinned archive, verified before it is unpacked. The unpacked `gitleaks` entry must be a regular file. A checksum mismatch, an unsupported platform, or no usable binary exits 2: the scan fails closed and nothing counts as scanned. `scripts/gitleaks --vault-resolve` prints the verified path and runs nothing.
- Modes. `make secrets` runs `scripts/scan-secrets.py $(SECRETS_MODE)`. `worktree` (the default, and what `make check` uses) scans every tracked file plus every untracked file `.gitignore` does not exclude, so it sees edits you have not staged. `staged` scans the index as the next commit would record it. `dir` scans every file under the current directory; the hooks use it on the staged snapshot, which has no `.git`. `range` scans the commits `SECRETS_BASE..HEAD`, or all history reachable from `HEAD` when `SECRETS_BASE` is empty; CI uses it. It passes gitleaks `--log-opts="-m --text <range>"`: `-m` reads a merge commit against each parent, so a secret that only a merge's own resolution adds is found, and `--text` keeps a committed `.gitattributes` from hiding a file. `SECRETS_BASE` must be empty or a full 40- or 64-character commit id that exists in the repository, or the scan exits 2 and says nothing was scanned. Any other `SECRETS_MODE` exits 2.
- Policy from the last reviewed commit. The scan's policy is `.gitleaks.toml` (rules and allowlists) and `.gitleaksignore` (findings to ignore, one fingerprint per line). They are read from `HEAD` in the `worktree`, `staged` and hook modes, and from `SECRETS_BASE` in `range` mode, never from the files being scanned, so a commit cannot silence its own findings. A change to either file takes effect from the next commit. Where the policy commit has no such file (the first commit, or a range scan with no base), the template defaults apply: gitleaks's default rules and nothing ignored. gitleaks also reads a `.gitleaksignore` at the root of whatever it scans, so the file modes scan a copy without it and range mode scans through a directory that holds only a pointer to the repository's Git data. A fingerprint for the file modes has the form `<path>:<rule>:<line>`; for range mode, `<commit>:<path>:<rule>:<line>`. gitleaks cannot read UTF-16 or UTF-32 text in range mode: it scans patch lines, where a NUL sits between the characters. The file modes decode such text, and `make deny-range` and the tripwire decode it in history, but a secret that a commit added in UTF-16 and a later commit removed is not found by the secret scan.
- Flags. Every scan passes `--redact --no-banner --ignore-gitleaks-allow --exit-code 1`, plus the policy's config and ignore file. `--ignore-gitleaks-allow` means an inline `gitleaks:allow` comment never silences a finding. `.gitleaks.toml` extends gitleaks's default rules; an exempt path is added there as a reviewed edit and, like other trust-root files, needs a code owner.
- `make check` runs the vault check, the index check, then `make secrets` in `worktree` mode, so it sees staged, unstaged and untracked edits alike. The hook checks the staged snapshot instead.

### Git hooks

`scripts/install-hooks` (run by `make setup`) links two hooks, `pre-commit` and `pre-merge-commit`, into Git's common hook directory. Git runs `pre-merge-commit` instead of `pre-commit` for a merge that completes without conflicts, so both hooks run the same command. The links are relative and point at `.githooks/` in the primary checkout, so every worktree of the repository shares them. It refuses to overwrite a hook that is a real file or a link to something else; chain it by hand. It checks every hook before linking any.

Git ignores the common hook directory whenever `core.hooksPath` is set, and many machines set it globally for a hook manager. So the script also sets the repository-local `core.hooksPath` to the common hook directory: local config overrides global, so the vault's hooks run. A global or system `core.hooksPath` (often an employer's own secret scan) is chained rather than dropped: the script records its directory in the repository-local `vaultkit.chainHooksPath` and prints `Chaining: global core.hooksPath is <path>`. Each vault hook then runs the same-named executable hook from that directory first, and stops the commit with `vault-kit: the chained <hook> hook in <path> failed` if it fails; a missing hook there is skipped. Every other executable hook in that directory that Git knows by name (`pre-push`, `commit-msg`, `post-checkout`, and the rest of githooks(5)) gets a link of the same name in the common hook directory to `.githooks/chain-passthrough`, which runs the chained hook with the same arguments and standard input and returns its exit status; the script prints `Passing through <hook>` for each, and a `WARNING` naming any hook it cannot link because a file of that name is already there. A chained hook added later needs `make install-hooks` again. The chain is refused with `WARNING: Not chaining` when the global value is a relative path (Git resolves it inside each repository, so the repository's own files would choose the hooks; set an absolute path) or names this vault's own `.githooks/` or hook directory. The hooks also export `VAULTKIT_CHAINED=1` to the chained hook and skip the chain when it is already set, so a chain that leads back into the vault's hooks runs once instead of calling itself without end. `scripts/install-hooks --no-chain` skips the chain, unsets `vaultkit.chainHooksPath`, and prints `WARNING: global core.hooksPath is <path>`, saying those hooks no longer run for this repository. Re-run `make install-hooks` after a global `core.hooksPath` changes. It refuses when the repository-local `core.hooksPath` already names another existing directory, and re-points one that names a directory that no longer exists (a moved clone). Its last lines name the active hooks path (`git rev-parse --git-path hooks`), and it exits 1 if that is not the common hook directory. `make uninstall-hooks` removes only links that point into a `.githooks/` directory (the pass-through links included), unsets `vaultkit.chainHooksPath`, and unsets the repository-local `core.hooksPath` only when it is the value the script set.

Both hooks run `scripts/check-staged.py`, which validates the proposed commit without touching the index or working tree:

1. `git diff --cached --check`, which rejects whitespace errors.
2. `check-history.py --staged`.
3. The rules that need the Git index itself: no two paths that differ only by case, and no tracked `.venv`. Name rules run in step 4, once.
4. A copy of the index (`git checkout-index`) into a temporary directory, then `make check PYTHON=<the hook's interpreter> SECRETS_MODE=dir` there, with the secret-scan policy and the deny list exported from `HEAD` (`scripts/scan-secrets.py export-policy HEAD <dir>`, passed as `SECRETS_POLICY` and `DENY_FROM`). The check reads exactly what the commit would record, not unstaged edits, and the commit cannot loosen the rules it is checked against.

`git commit --no-verify` skips the hooks. CI repeats the history and secret checks so a skipped hook is caught on the push.

### CI

`.github/workflows/check.yml`, named `Vault standards`, has one job, `check`. It runs on every pull request and on pushes to `main`; pull requests cover the other branches. If your default branch has another name, change `branches: [main]`, and re-apply that edit after each engine update, which replaces the workflow. A newer run for the same pull request cancels the one it supersedes; a push to `main` is never cancelled, because each push checks only its own commits. The job times out after 15 minutes. It runs on `ubuntu-latest` with read-only `contents` permission, actions pinned by full commit SHA, and a checkout that keeps no credentials (`persist-credentials: false`). It sets `PYTHON=python3`, so `make` runs the runner's interpreter and never one from a `.venv` in the checkout, and `VAULT_KIT_REQUIRE_GITLEAKS=1`, so the test suites fail instead of skipping the secret-scan cases when the pinned gitleaks cannot be resolved. Steps: check out with full history; set up Python 3.12; install `requirements-dev.txt`; restore `~/.cache/vault-kit` with `actions/cache`, keyed on the gitleaks version in `scripts/gitleaks` (the wrapper still checks the cached binary's SHA-256); `make check`; in an instance (`template = false`, read from `vault.toml` inside the step), `make check-initialized`; choose the base commit as described above; run the history check from that base; run the secret scan over the new commits (all of history when there is no base); run `make deny-range` over the same commits; in the template only, the private-name tripwire; `make test`, with `VAULT_KIT_TRIPWIRE` passed in so `test-init` also runs the tripwire over a freshly initialized vault's rendered skills (empty in an instance, so skipped there).

Private-name tripwire. The template repository also checks that none of its maintainer's private names (hosts, internal tools, org terms) leak into the shipped kit. The names are never committed, since a committed list would publish them. They live in the Actions secret `VAULT_KIT_TRIPWIRE`, one Python regex per line, matched case-insensitively and used as given (add `\b` word boundaries yourself). The CI step runs only when `vault.toml` has `template = true` (decided inside the step) and prints a notice and skips when the secret is empty, as it is for pull requests from forks. `scripts/tripwire` scans every file `git ls-files` lists (tracked, plus untracked and not ignored) that is not binary by its own bytes (UTF-16 and UTF-32 with a byte-order mark count as text; `.gitattributes` is not consulted), the target text of every symlink, every path name, and the messages and patches of the new commits (all of history with no base), read with `--text` so a committed `-diff` or `binary` attribute hides nothing. A UTF-16 or UTF-32 file a commit adds or changes is decoded and scanned whole, since its patch lines cannot match. A file it cannot read fails the step (exit 2). It prints `<path>:<line>: tripwire pattern N` and `<commit>: tripwire pattern N in the message|patch` (or `in a UTF-16 or UTF-32 file`), withholds a path whose name matches, and never prints a pattern or the matched text. A pattern that is not a valid regex fails the step by number. Run it locally with `scripts/tripwire --patterns <file>`; keep that file outside the repository.

### Skills

Two skills let agents use the vault. `<name>-discover` searches the vault before new work and answers with a table of reuse candidates. `<name>-maintain` walks the write path for an ingest, query, lint, or maintenance change on a worktree branch, then pushes and opens a pull request.

They are rendered from `templates/skills/<kind>/skill.md.tmpl` to `skills/<name>-<kind>/SKILL.md`; any other `<file>.md.tmpl` in a template directory renders to `<file>.md` in the same relative place. The placeholders are `{{name}}`, `{{title}}`, `{{scope}}` and `{{root_env}}`. An unknown placeholder, or one left unrendered, fails. Values go into frontmatter as single-quoted YAML scalars with quotes doubled. Each rendered file carries a comment naming its template and saying not to edit it.

Rendering also checks the Agent Skills limits: `name` equals the directory name, `description` is 1 to 1024 characters, and `compatibility` is 1 to 500.

- Identity gate. The discover skill takes the vault root only from the `{{root_env}}` environment variable, never from a guessed path. It runs `test -n "$root" && test -f "$root/skills/<name>-discover/SKILL.md"`. If that fails it replies `<title> is not reachable at <root>` and stops, and it never answers from memory. A failed search is reported as unreachable, never as "no match".
- Drift check. In an initialized vault, `make check` renders the templates into a temporary directory and compares them with `skills/`. A hand edit fails with `skills/<file> differs from templates/; run scripts/init-vault --render-skills`. Extra files inside a rendered skill directory that no template produces also fail.
- Re-render. `make render-skills` (the same as `scripts/init-vault --render-skills`) rewrites only changed files and removes files no template produces.
- The maintain skill carries a harness-neutral redaction checklist (employer hosts and products, credentials, key fingerprints, customer and personal data) and says `make check` runs the mechanical scan.

### init-vault

`scripts/init-vault --name <slug> --title "<Title>" --scope "<scope>"` turns the template into a vault. It validates the identity first, then does four steps in order:

1. Render the skills.
2. Append `## [<today>] maintenance | Initialize <name> from vault-kit` to `wiki/log.md`.
3. Regenerate every `index.md`.
4. Write `vault.toml` last, with `template = false`, the identity, and `root_env`. The `[redaction]` table and every comment are kept.

A vault counts as initialized only when `vault.toml` says so, so an interrupted run leaves `template = true`. Running the same command again prints the pieces that are still missing and finishes them. On success it prints a reminder to fill `[redaction] deny` and the code owners, and the last line is `PASS: initialized <name> at <root>`.

Exit codes: 0 done; 1 a step failed; 2 usage error or invalid value (stderr names the rule and the value); 3 already initialized.

### install-discovery

`scripts/install-discovery` connects the vault to the agents on a machine. POSIX only.

- With no flags it prints every path a write flag would touch and writes nothing, and exits 0.
- `--pointer`, `--pointer-codex` and `--skills` need an initialized vault: on the template they print `REFUSED` with the `init-vault` command and exit 2. The dry run and `--uninstall` work either way.
- `--pointer` writes a marked block, between `<!-- <name>:start -->` and `<!-- <name>:end -->`, into `AGENTS.md` in the parent directory (default: the directory that holds the vault), and makes `CLAUDE.md` there a symlink to it, or appends the block to an existing `CLAUDE.md`. The block tells the agent to invoke `<name>-discover` before proposing a tool, library, service or cross-project integration, and gives the paths to read if the skill is missing. Repeating it changes nothing.
- `--parent <dir>` names a directory whose `AGENTS.md` gets the block, for layouts where the vault and projects are not siblings. Repeat it when the covered projects sit under more than one directory; each gets its own block. Every check runs before any write, so one refused parent writes nothing. In a Git checkout of the vault, each pointer directory is recorded in the repository-local Git config as `vaultkit.pointerDir`, so `--uninstall` finds every one. A parent that is itself a Git repository gets a warning: the block shows up there as an uncommitted change.
- `--pointer-at-home` is required when the parent is `$HOME` or `/`, where the block would reach every session on the machine. Without it, `--pointer` prints `REFUSED` and exits 2.
- `--pointer-codex` writes the same block into `~/.codex/AGENTS.md`. It refuses if `~/.codex` does not exist.
- `--skills` symlinks `skills/<name>-discover/` and `skills/<name>-maintain/` into `~/.claude/skills`, `~/.codex/skills` and `~/.pi/agent/skills`, skipping any of those directories that does not exist. Any other directory under `skills/` is linked only when you name it with `--include <dir>` (repeatable), because a linked skill reaches every session on the machine and a contributor can add one in a pull request; the install lists the ones it left out. It never replaces an existing path that does not already resolve to this checkout; it prints `REFUSED` and exits 1.
- `--check` verifies every expected link resolves into this checkout, that no stray link points at a skill that no longer exists, that each skill's frontmatter name matches its directory, and that a rendered skill belongs to this vault and reads its root variable. It exits 1 on any failure. If the root variable is set and names another checkout, that is a failure too.
- `--uninstall` removes every skill link that resolves into this checkout (including `--include` ones), the block in the `AGENTS.md` and `CLAUDE.md` of each parent (the `--parent` directories or the default, plus every recorded `vaultkit.pointerDir`, which it then clears), the `CLAUDE.md` symlink and the `AGENTS.md` file only if this script created them, and the Codex block. It reports any `.bak` file it leaves. It exits 1 if an expected link was left in place. It cannot be combined with the write flags.
- Writes go through a temporary file and a rename, and the first write to an existing file keeps a `<file>.bak` of the prior content.
- Any flag that writes or uninstalls refuses to run from a Git worktree; use the primary checkout.

### Retrieval

Retrieval gives agents keyword and semantic search over `wiki/` using QMD. The details and recovery steps are in [the retrieval runbook](wiki/runbooks/retrieval.md). The rules:

- One index per vault, in `.qmd/` at the vault root (gitignored): `index.sqlite`, `index.yml` and `trusted.json`. A work vault and a personal vault never share a database, and nothing is written to QMD's global cache or config directories. The only shared file is the model cache.
- `scripts/qmd` is the only entry point. It sets `INDEX_PATH` and `QMD_CONFIG_DIR` to `.qmd/` and changes into the vault root, because QMD adopts the nearest `.qmd/` above the working directory and a stray one elsewhere must not capture a search. It refuses a search command when no index exists. Do not call the global `qmd` binary.
- `make retrieval-setup` (script `scripts/retrieval-setup setup [--lexical-only]`) registers the collection `collection add . --name <name> --mask 'wiki/**/*.md'`, adds `wiki/log.md` to the collection's ignore list in `.qmd/index.yml`, adds a context line built from the title and scope, then refreshes. `wiki/log.md` is excluded because it is history, not knowledge. Safe to repeat.
- `make refresh` runs `make check` and then updates and embeds this vault only.
- `make retrieval-teardown` removes the collection and deletes `.qmd/`. It refuses if `.qmd` is a symlink.
- `make retrieval` runs `scripts/check-retrieval.py`: a negative control, then a temporary page that must appear in a search after an update, change after an edit, and disappear after deletion.
- Search: `scripts/qmd search "terms" -c <name>` (keyword), `scripts/qmd query "question" -c <name>` (hybrid), `scripts/qmd vsearch "question" -c <name>` (vector).
- Large files. Claude Code's Read refuses a file over about 256 KB or 25,000 tokens without an offset and a limit, and QMD indexes only `wiki/`. `scripts/md-outline <file> [--json]` prints each heading with its line range and size in bytes, skipping YAML frontmatter and fenced code, so an agent reads one section of a large page or `raw/` capture instead of the whole file. It uses the standard library only and caches nothing.

### Engine update

`engine.manifest` lists, one path per line, the files vault-kit owns: the hooks, the CI workflow, `Makefile`, `requirements-dev.txt`, and the files in `scripts/`. Lines starting with `#` and blank lines are ignored. `make engine-update REF=<tag> [COMMIT=<full-sha>] [SOURCE=<git-url-or-path>]` runs `scripts/engine-update --ref <tag> [--commit <full-sha>] [--source <git-url-or-path>]`:

1. It refuses to run if the working tree has any change, including untracked files (exit 2, listing them).
2. It makes a shallow clone of the tag (a branch name also works) into a temporary directory. A fetch failure exits 3. `SOURCE` defaults to the public vault-kit repository; set it to an internal mirror or a local path where needed.
3. With `--commit`, the ref must resolve to exactly that full commit id, or nothing is copied (exit 2). A tag or branch can be moved after you review it; the commit id cannot. It prints the commit the ref resolved to either way.
4. It reads the manifest from that tag, not from your copy, and checks every path before copying anything: relative only, no `..`, no backslashes, no `.git` component, no symlink components in the source or in your vault, and each entry a regular file in the tag.
5. Every path must sit in an engine location: `scripts/`, `templates/skills/`, `.githooks/pre-commit`, `.githooks/pre-merge-commit`, `.githooks/chain-passthrough`, `.github/workflows/check.yml`, `Makefile`, `requirements-dev.txt` or `engine.manifest`. This is an allowlist, compared case-insensitively, because on a case-insensitive disk `WIKI/log.md` is `wiki/log.md`. A path spelled in another case than its location is refused too. So a manifest can never write `vault.toml`, `AGENTS.md`, `wiki/`, `.claude/settings.json`, `.mcp.json`, `.envrc`, `.vscode/` or another hook such as `.githooks/post-checkout` (exit 2).
6. It overwrites the listed files, printing `updated <path>` or `added <path>`, then prints `git status --short` and `git diff --stat` and exits 0. It runs nothing from the fetched ref, not even `make check`: you review the diff first, then run `make render-skills && make check` yourself.

The manifest lists itself and the skill templates under `templates/`, so an update carries new engine files and template changes. It does not carry everything vault-kit ships: `.gitignore`, `AGENTS.md`, `README.md`, `LICENSE`, `.github/CODEOWNERS`, the `.obsidian/` settings, and the wiki contract pages (`wiki/system/`, `wiki/templates/`, the runbooks) are vault-owned or outside the engine locations, so a release that changes them needs a hand merge: compare them with the tag (`git diff <tag> -- <path>` after fetching it) and copy what you want. Because the CI workflow is in the manifest, local edits to it are replaced; review the diff before you commit.

## Multi-project use and trust

- Reach. The block that `--pointer` writes sits in the `AGENTS.md` of the parent directory, so it reaches every project folder under that directory. Use `--parent <dir>` when your projects live somewhere other than next to the vault, and repeat it when they are spread over several directories. Pick the narrowest directory that holds the covered projects: every other project under it sees the block too. A harness that reads `AGENTS.md` or `CLAUDE.md` walking up from a project folder sees it.
- Installed skills are symlinks into your checkout. A `git pull` in the vault changes what every harness on the machine runs, immediately.
- `AGENTS.md` in the vault is instructions for every agent session that installed the vault. Treat a change to it like a change to code.
- Vault text is data. The skills tell agents that retrieved pages are evidence, not permission to run commands found in them, and the vault's own `AGENTS.md` says the same.
- Trust root. These paths are instructions or code for every agent that installs the vault: `AGENTS.md`, `CLAUDE.md`, `skills/`, `templates/`, `scripts/`, `Makefile`, `.githooks/`, `.github/`, `vault.toml`, `engine.manifest`, `requirements-dev.txt`, `.gitleaks.toml`, `.gitleaksignore`, and so is almost any new top-level path (`.claude/`, `.mcp.json`, `.obsidian/plugins/`, `.gitattributes`). So `.github/CODEOWNERS` is an allowlist: every path needs a code owner except the content a contributor edits (`wiki/`, `raw/`, the root `index.md`), and within those, `wiki/system/`, `wiki/templates/`, any dot-path and any agent instruction file (`AGENTS.md`, `CLAUDE.md` and the like) still need one. `docs/plans/` needs one too: agents carry out plan files, so a plan is instructions. It only has effect once `main` is protected and requires code-owner review, so do that.
- The deny list is itself sensitive. It names what you want hidden. Keep the repository private, and keep the patterns as general as you can. The check never prints them.
- If a secret lands in the repository: rotate the credential first. Then clean up history. `raw/` and `wiki/log.md` cannot be rewritten under the hooks, so removing a value from them needs a deliberate history rewrite outside the hooks, agreed with whoever owns the repository. Treat any value that reached a pushed branch as exposed.

## Day to day

Agents and people follow the same loop, which `AGENTS.md` states in full.

1. Work on a branch in a Git worktree, never directly on `main`.
2. Read `wiki/index.md` and the relevant pages. Search with `scripts/qmd`.
3. Make the change: add a new dated capture under `raw/` for new source material, update the affected wiki pages, and keep attribution and uncertainty.
4. Append an entry to `wiki/log.md`, run `make indexes`, stage the files, and commit. The hook checks the staged snapshot.
5. Open a pull request, then run `make refresh` after merging to update search.

Commands:

- `make check`: the vault check, the index check, and the secret scan.
- `make refresh`: `make check`, then update and embed the search index.
- `make test`: the test suites for the hooks, `install-discovery`, `engine-update`, `init-vault`, `scripts/tripwire` and `scripts/md-outline`, each on throwaway fixtures. `make test-retrieval` also exercises QMD and needs it installed; `VAULT_KIT_TEST_SEMANTIC=1` adds the embedding leg.
- `make indexes`: regenerate the directory indexes.

## Updating

```bash
make engine-update REF=v0.1.0 COMMIT=<the full commit id of v0.1.0 you reviewed>
```

Run it on a clean tree. Pass `COMMIT` so a tag moved after your review is refused. The update only copies files and prints `git status --short` and `git diff --stat`; it runs nothing from the fetched code. Review `git diff`, then run `make render-skills && make check`, then commit. The skill templates under `templates/` are engine files, so an update can change them, which is why `make render-skills` follows every update. Also run `make render-skills` after you edit a template yourself. The update writes only the engine locations listed under Engine update, never `vault.toml`, `.gitleaks.toml`, `AGENTS.md`, `wiki/`, `raw/`, `docs/`, `skills/` or `.obsidian/`; changes vault-kit makes outside them need a hand merge.

## Teardown

Run these from the vault's primary checkout.

```bash
scripts/install-discovery --uninstall
make retrieval-teardown
make uninstall-hooks
```

The first removes the skill links, the pointer block and what the install created. The second removes the search collection and `.qmd/`. The third removes the Git hook links. The shared model cache under `~/.cache/qmd/models` stays; delete it by hand if you want the space back.

## Sibling vault

vault-kit was extracted from a private vault with the same rules; fixes flow both ways.

## License

Apache-2.0. See `LICENSE`. Dependencies are referenced, not bundled: QMD, PyYAML, gitleaks and the pinned GitHub Actions are all MIT-licensed.
