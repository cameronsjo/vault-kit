---
type: Runbook
title: 'Enforce vault standards'
description: 'What each vault check enforces, when it runs, and what it cannot prove.'
status: draft
generated:
  by: vault-kit/seed
  at: '2026-10-05T14:57:14-05:00'
---
# Enforce vault standards

## Purpose and scope

The vault's rules are enforced in code, in three places: `make` targets you run by hand, a pair of Git hooks, and CI. This page says what each check enforces and what it cannot prove.

## Checks

| Check | Command | Enforces |
|---|---|---|
| Vault profile | `make check` | Over every tracked file and every untracked file `.gitignore` does not exclude: lowercase kebab-case names, a `CLAUDE.md` symlink to `AGENTS.md`, required frontmatter, valid timestamps and actors, no broken local links, an index in every content directory, no symlink under `wiki/`, `raw/` or `skills/`, no credential-bearing URLs, no match for the `[redaction] deny` patterns in `vault.toml`, in content or in a path name. The hook checks against `HEAD`'s deny list, so emptying it takes effect from the next commit. |
| Indexes | `make check` (runs `scripts/index-vault.py --check`) | Directory indexes match page descriptions. `make indexes` regenerates them. |
| Rendered skills | `make check` | In an initialized vault, every file under `skills/<name>-discover/` and `skills/<name>-maintain/` matches a fresh render of `templates/skills/`. A hand edit fails with `skills/<file> differs from templates/; run scripts/init-vault --render-skills`. Skipped in the unconfigured template. |
| Secrets | `make secrets` (and `make check`) | A pinned gitleaks scan. The default mode, `worktree`, reads every tracked file and every untracked file `.gitignore` does not exclude, so it sees unstaged edits; `SECRETS_MODE=staged` reads the index; `SECRETS_MODE=dir` scans a directory; `SECRETS_MODE=range` scans a commit range; there gitleaks cannot read UTF-16 or UTF-32 text, which the deny-range scan and the tripwire decode instead. `.gitleaks.toml` and `.gitleaksignore` are read from `HEAD` (from the range's base in range mode), so a change to them takes effect from the next commit. |
| Deny history | `make deny-range` | Every commit in `SECRETS_BASE..HEAD`, one at a time: its message, the path names it touches and the lines it adds, against the base commit's deny list. A UTF-16 or UTF-32 file it adds or changes is decoded and scanned whole. Text a later commit removed still counts. |
| Initialization | `make check-initialized` | `vault.toml` names the vault. It fails on the unconfigured template. |
| Tests | `make test` | The history rules below, `install-discovery`, `engine-update`, `init-vault`, and `scripts/tripwire`, each against throwaway fixtures. |
| CI | `.github/workflows/check.yml` | `make check`, `make check-initialized` in an instance, the history check, a secret scan and a deny scan of new commits, and `make test`, on every pull request and every push to `main`. |

## Source and history

The staged hook and CI reject changes to existing `raw/` captures. They require `wiki/log.md` to keep its old bytes and append a dated entry whenever `raw/`, `wiki/`, or the agent contract changes. Install the hooks with `make setup`.

When two branches both append to the log, merge the default branch into yours. If Git reports no conflict, stop. Otherwise resolve every conflicted file except the log and generated indexes, then run `make merge-log && make indexes`, add the results, and append one entry saying how you resolved any page by hand.

## Verify the result

`make check` exits 0 and prints `PASS` lines. A failure names the path and the rule.

## Recovery

A bad name or missing frontmatter: fix the page. A stale index: run `make indexes`. A secret match: remove the value, rotate the credential, and do not rely on an inline allow comment; they are ignored on purpose.

## Provenance

These checks cannot prove a page is true, a source is complete, or a claimed test ran. A commit made with `--no-verify` skips the local hook; CI repeats the history check, the secret scan and the deny-range scan over the new commits, so they cannot be skipped there. Protect `main` and require code-owner review so the checks and the trust-root files stay under review.
