---
type: Runbook
title: 'Fill a new vault on day one'
description: 'How to seed an empty vault: capture a repository inventory by hand, sanitize it, and write the first capability cards, journeys and runbooks.'
status: draft
generated:
  by: vault-kit/build
  at: '2026-10-05T16:40:00-05:00'
---
# Fill a new vault on day one

## Purpose and scope

A new vault is empty. This runbook gets the first useful pages in on day one. There is no seeding script: you capture the sources by hand, and an agent using the maintain skill writes the pages. For a folder of existing docs, the maintain skill's `references/ingest.md` is the procedure; this page covers the repository inventory and what to write first.

Rules that shape every step:

- A committed file under `raw/` can never be edited (see [standards checks](standards-checks.md)). Write each capture once, with its `manifest.json`, then commit it.
- A re-run is a new dated capture. It never edits the old one.
- The capture is evidence; the wiki pages are the maintained knowledge and cite it.

## Prerequisites

- An initialized vault (`make check-initialized` passes) and a worktree branch, as the maintain skill's Step 1 sets up. Do not write in the primary checkout.
- `gh` logged in for the organization (`gh auth status`). Every command below only reads.
- `[redaction] deny` in `vault.toml` filled in. The check reads it; this runbook cannot know your private names.

## Steps

1. **Capture the repository inventory.** Pick the date and a scope. From the worktree root:

   ```sh
   mkdir -p raw/<YYYY-MM-DD>-repository-inventory
   gh repo list <org> --limit 1000 --json name,description,defaultBranchRef,isArchived,repositoryTopics,url > raw/<YYYY-MM-DD>-repository-inventory/repos.json
   ```

   On GitHub Enterprise, name the host with `GH_HOST` (`gh help environment` documents it: the hostname used when a command is not given one; stored credentials for that host are used, otherwise set `GH_ENTERPRISE_TOKEN`):

   ```sh
   GH_HOST=<host> gh repo list <org> --limit 1000 --json name,description,defaultBranchRef,isArchived,repositoryTopics,url > raw/<YYYY-MM-DD>-repository-inventory/repos.json
   ```

   `--limit` defaults to 30, so always set it. `gh repo list` prints only repositories owned by the org you name. Add `--no-archived` to leave archived repositories out, or `--topic <topic>` to narrow the scope, and say so in the manifest. Keep only the fields the pages need: drop a field you do not need from the `--json` list rather than deleting it afterwards.

2. **Write `manifest.json` beside it**, once:

   ```json
   {
     "source": "https://<host>/<org>",
     "command": "gh repo list <org> --limit 1000 --json name,description,defaultBranchRef,isArchived,repositoryTopics,url",
     "captured_at": "<ISO-8601 time with UTC offset>",
     "scope": "<which org, which filters>",
     "excluded": "<what was left out and why, for example private repositories you cannot read, or fields dropped>",
     "previous_capture": null
   }
   ```

3. **Sanitize before you commit.** Read `repos.json` for descriptions that carry an internal hostname, a codename, a customer name or a ticket link. Anything that matches `[redaction] deny` fails the check; anything the patterns cannot see is on you (the maintain skill has the redaction checklist). Fix it now by removing the repository from the capture or the field from the command, and say so under `excluded` in the manifest. A committed capture cannot be corrected, so this is the only chance. Then stage and scan:

   ```sh
   git add -- raw/<YYYY-MM-DD>-repository-inventory
   make check
   ```

   `make check` includes the secret scan over staged files. If it fails, unstage, fix the files, and run it again. If a file was committed with a leak, see the vault README on what to do (rotate first).

4. **Write the first pages**, in this order. Use the templates in `wiki/templates/` and place each page as the maintain skill's Step 2 says.
   1. A source-summary page for the capture, in `wiki/doctrine/` or `wiki/runbooks/` as fits: what the inventory covers, the date, and what it excludes. Link the capture folder. One such page per capture.
   2. One capability card per shared component or team service: something another project can consume. Read the repository's README for each (not only the description) and record the owner, the interface, and how to find it. Give purpose, implementation evidence and run-state separate evidence dates; do not claim a service runs because its README says so.
   3. Journeys for the two or three most common cross-project tasks (for example "ship a change", "add a service", "get access"). Each links the capability cards it crosses.
   4. Runbooks for recurring operational steps that people ask about twice.

   Every page lists the files it used under `sources:` and links its raw capture.

5. **Log it.** Append one entry per ingest to `wiki/log.md`:

   ```markdown
   ## [YYYY-MM-DD] ingest | Repository inventory for <org>

   <actor>, raw/<YYYY-MM-DD>-repository-inventory, <pages created>, <evidence>, <what was excluded or not read>.
   ```

6. **Check and commit.** `make indexes && make check`, then explicit-path `git add`, `git commit -- <paths>`, push and open a pull request as the maintain skill's Step 5 says. After the merge, `make refresh` in the primary checkout so search sees the new pages.

## Re-running

Run steps 1 to 3 again with the new date. The new folder gets its own `manifest.json` with `previous_capture` naming the older folder. Do not touch the old capture. Update the wiki pages whose repositories changed, and cite the newer capture as superseding evidence (keep the older citation where it still supports a claim). Log it as another `ingest` entry. Compare the two `repos.json` files with `diff` to find the repositories that were added, archived or changed.

For a folder of docs, follow `references/ingest.md` in the maintain skill: it hashes each file and processes only the new or changed ones.

## Verify the result

- `make check` exits 0 on the branch.
- `git diff --cached --name-only` lists only the files you meant to commit, with the capture folder holding exactly `repos.json` and `manifest.json`.
- Each new page links its capture and each capture has a source-summary page.
- After the merge and `make refresh`, `scripts/qmd search "<a repo name>" -c <name>` returns the page.

## Recovery

- The check names a deny-pattern hit by path and pattern number only. Open that file, find the text, remove it, and run the check again, before the commit.
- `gh: command not found` or an authentication error: `gh auth login`, or for Enterprise `gh auth login --hostname <host>`.
- The list is shorter than you expect: raise `--limit`; a private repository you lack access to does not appear.
- You committed a capture that should not have been: do not edit it. Stop, and follow the vault README's guidance on a leak (rotate a credential first; removing a value from `raw/` needs a deliberate history rewrite outside the hooks, agreed with the repository owner).

## Provenance

The `gh repo list` command was run read-only against a public org with `--limit 5` on 2026-10-05 using gh as installed on the build machine, and returned the six fields named above. `GH_HOST` and the flags were checked against `gh help environment` and `gh repo list --help`; the Enterprise form was not run against an Enterprise host. The runbook's source is the vault-kit build; limits: the inventory shows what a repository says about itself, not whether it is maintained or running.
