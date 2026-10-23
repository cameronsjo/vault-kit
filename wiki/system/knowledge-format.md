---
type: Reference
title: 'Open Knowledge Format profile'
description: 'The OKF v0.2 authoring profile this vault uses and the limits of its validator.'
status: draft
generated:
  by: vault-kit/seed
  at: '2026-10-05T14:57:14-05:00'
---
# Open Knowledge Format profile

The vault uses Open Knowledge Format (OKF) v0.2 as its Markdown bundle convention. Specification: https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md.

## Authoring contract

A concept document is UTF-8 Markdown with YAML frontmatter. OKF requires `type`. This vault also requires `title`, `description`, and a lifecycle `status` of `draft`, `stable`, or `deprecated`. That is a stricter local profile, not a claim that OKF requires those fields. Unknown keys and unknown types stay valid.

```yaml
---
type: Runbook
title: Short title
description: One sentence that says when to open this page.
status: draft
generated:
  by: <harness>/<id>
  at: '2026-01-01T09:00:00+00:00'
---
```

- `generated` names the writer and edit time. `by` is `human:<name>`, `process:<name>`, or `<tool>/<id>`; `at` needs an explicit UTC offset.
- Add `verified` only after a named actor checks the page's claims. Generation and a passing link check are not verification. Missing `verified` means unverified.
- Keep evidence in `sources` (each entry has a `resource`). Draft content is discoverable but is not a completed integration.

## Indexes and links

Each content directory has an `index.md` for progressive discovery. `make indexes` generates them from page descriptions. The root index declares `okf_version: "0.2"`; other indexes have no frontmatter. `log.md` has no frontmatter either.

Use file-relative Markdown links; Obsidian and Git both render them. Keep paths stable. To retire a concept, mark it `deprecated` and point to its replacement before removing inbound links. OKF consumers tolerate broken links; this vault's check rejects them so the tree stays navigable.

## Page types by question

Each page type answers one of the four reader questions of the Diátaxis documentation framework. Name the question before picking a type; a page that answers two questions becomes two linked pages. The maintain skill's placement table (`templates/skills/maintain/skill.md.tmpl`, Step 2) is the source; this copy is for people.

| Question | Page types |
|---|---|
| Learn by doing | none yet; a runbook whose first line says it walks a newcomer through |
| Do a task | Runbook |
| Look something up | Capability, the system pages |
| Understand why | Doctrine, Field report, Journey (how one outcome flows across parts; its steps live in runbooks) |

## Templates

Templates in `wiki/templates/` are `type: Template` concepts. When you copy one, set the new page's real type, title, description, writer, time, and sources. Do not copy a verification claim.

## Limits

`scripts/check-vault.py` checks this profile, YAML shape, timestamps, local links, and directory indexes. It does not implement every optional OKF feature and does not prove a page is true.
