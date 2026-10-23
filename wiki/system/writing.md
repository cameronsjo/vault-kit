---
type: Reference
title: 'Writing guidance'
description: 'How to write vault pages: plain, short, sourced, dated, and honest about limits.'
status: draft
generated:
  by: vault-kit/seed
  at: '2026-10-05T14:57:14-05:00'
---
# Writing guidance

## Style

- Write plainly and keep pages short. One topic per page, one idea per sentence.
- Keep a sentence under about 35 words.
- Cut filler phrases: `worth noting`, `it is important to note`, `in order to`, `basically`.
- Say what is, not what is not. Prefer a direct statement to a hedge.
- Define a term of art the first time it appears.
- Link to a source or sibling page instead of copying its text.

## Evidence

- Date every claim about live state, with the source and how it was checked.
- Separate three things: the intended purpose, the implementation evidence, and the runtime state. A README or a plan does not prove something works.
- Record limitations on every page: unknowns, constraints, and the next useful verification.
- When sources conflict, record the conflict and keep both. Do not fill unknowns with guesses.

## Structure

- Every capability separates purpose from available support and runtime verification.
- Every runbook gives prerequisites, steps, expected evidence, and recovery.
- Every field report names its original author, date, affected components, outcome, evidence, and unresolved work.
- A doctrine page carries a cross-cutting rule, its reason, and a dated evidence line.
- Link a task or pull request rather than copying a live checklist into several pages.

Start from the templates in [templates](../templates/index.md).

## Names and paths

Follow established filename conventions (`AGENTS.md`, `README.md`, `Makefile`); otherwise use lowercase kebab-case for files and directories. Use descriptive names and standard relative Markdown links. Prefer repository-relative paths to machine-only absolute paths.

## Ownership and concurrent edits

One page has one canonical path. Independently maintained duplicates are not allowed. Edit on an isolated branch or worktree, stage only your own files, and resolve conflicts with the other contribution kept. A clean commit does not prove the search index has refreshed.

## Moving material

Inventory and classify existing material first. Keep original frontmatter and provenance. Check links, embeds, and attachment paths before moving a page, update inbound links, and confirm the new copy before removing the old one. Do not publish unrelated private material because it shares a folder.
