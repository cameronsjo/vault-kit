---
type: Reference
title: 'The raw and wiki contract'
description: 'How raw captures, the maintained wiki, and the append-only log fit together, and the four operation types.'
status: draft
generated:
  by: vault-kit/seed
  at: '2026-10-05T14:57:14-05:00'
---
# The raw and wiki contract

The vault follows the LLM-wiki pattern: keep source material separate from a maintained layer that an agent keeps current. Background: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f. This page states the local rules; the idea gist is context, not authority.

## Layers

- **`raw/`** holds curated captures and assets. A committed capture never changes. If a source changes, add a new dated capture and link it as superseding evidence. Never put a synthesized conclusion in a capture.
- **`wiki/`** holds maintained knowledge. Pages cite the captures and other sources they rely on, and change as evidence changes.
- **The agent contract** (`AGENTS.md`) tells every agent how to read and write the two layers.

Git is the canonical record. The search index is derived and can be rebuilt.

## The log

`wiki/log.md` is append-only. Each entry is headed:

```text
## [YYYY-MM-DD] <operation> | <title>
```

and followed by the actor, the changed pages or sources, the evidence, and unresolved gaps. Preserve every earlier byte. The staged hook and CI reject a rewritten log and require an entry whenever `raw/`, `wiki/`, or the agent contract changes.

## Operations

| Operation | Use it for |
|---|---|
| `ingest` | Add a source: record its identity and capture path, update affected pages, keep attribution, record conflicts. |
| `query` | Answer a question from the vault, cite evidence, and file the answer when it is reusable. |
| `lint` | Inspect for stale claims, contradictions, missing connections, and coverage gaps. |
| `maintenance` | Change the vault's own structure, tooling, or contract. |

## Limits

The hooks cannot verify that a page is true, that a source is complete, or that a claimed runtime test happened. Agents supply evidence and preserve uncertainty.
