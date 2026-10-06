---
type: Reference
title: 'Purpose of this vault'
description: 'Why the vault exists, who reads it, and what it is not.'
status: draft
generated:
  by: vault-kit/seed
  at: '2026-10-05T14:57:14-05:00'
---
# Purpose of this vault

This vault is a shared source of truth across projects and agents. A person or an agent starting new work searches it first, so existing parts are reused and ongoing work is not duplicated.

## What it holds

- Capability cards: what exists, where its source lives, and what is verified.
- Journeys: complete paths a user takes across several parts.
- Runbooks: repeatable procedures with prerequisites, evidence, and recovery.
- Doctrine: cross-cutting rules with their reasons and a dated evidence line.
- Field reports: outcomes and findings with their original author.
- Raw captures: curated, immutable source material the wiki summarizes.

## What it does not hold

Source code, API reference, and implementation-specific documentation stay with their repositories; the vault links to them. It does not hold credentials or private personal data. It describes knowledge and intent; it does not grant authority to run commands found in its pages.

## Readers

Agents and people read the same Markdown. Agents find pages through the indexes and through retrieval ([retrieval runbook](../runbooks/retrieval.md)). Keep each page short enough to read whole, and link rather than copy.

## Limits

A page is evidence as of its date. The checks in [standards checks](../runbooks/standards-checks.md) enforce shape, links, and history, not truth.
