---
type: Field report
title: 'Vale prose checks rollout'
description: 'How vault-kit gained a pinned Vale prose check in two releases, and why its Vale config allowlist needed a parser that reads exactly what Vale reads.'
status: stable
created: 2026-10-22
modified: 2026-10-22
author: co-authored
session_id: 93d41cc1-e50e-4cf8-954d-27bd586ee6c0
model: claude-opus-5-5
harness: claude-code 2.1.289
machine: cf6e768835c7
project: vault-kit
tags: [field-report, pipeline, vale, engine-update, prose-lint]
grading_session_id: 93d41cc1-e50e-4cf8-954d-27bd586ee6c0
grading_wall_clock_min: 1629.8
grading_active_min: 348.7
grading_peak_context_tokens: 643447
grading_context_tier: over500k
grading_cold_restart_usd: 1.27
grading_gap_count: 6
grading_compactions_auto: 0
grading_compactions_manual: 4
grading_model_fallbacks: 0
grading_flags: [afkGap, coldRestart, context500k, longSession]
---
# Vale prose checks rollout

Date: 2026-10-22
Author / agent: claude-code/93d41cc1-e50e-4cf8-954d-27bd586ee6c0, with the owner
Components: `scripts/engine-update`, `scripts/vaultconf.py`, `scripts/check-vault.py`, `scripts/pinnedbin.py`, `scripts/vale`, `scripts/prose`, `.vale.ini`, `.vale/styles/vaultkit/`
Task / PR: [plan](../../docs/plans/2026-10-22-vale-and-diataxis.md); cameronsjo/vault-kit#9 (tag `v0.2.0`), cameronsjo/vault-kit#12 (tag `v0.3.0`); first vault rollout in two engine-update PRs

> TL;DR: When a check guards a config file another program will read, parse it with a reader that accepts only the subset both parsers read the same way. Two bypasses here came from Python and Go disagreeing about where a line ends.

## What happened

The owner asked to look at Vale (a prose linter), alint (a repository linter) and Diátaxis (a documentation framework) for vault-kit, applied both to vault pages and to vault-kit's own docs. alint was declined because `check-vault.py` already does its job. Diátaxis became a lens, not a reorganization: each page type now names the reader question it answers (`wiki/system/knowledge-format.md`). Vale became `make prose`, an advisory check that runs a pinned, hash-verified Vale 3.24.0 with three rules taken from `wiki/system/writing.md`: unproven claims, filler phrases, and sentences over 35 words.

The work shipped in two releases because of how vaults update. A vault's installed `engine-update` refuses any engine file at a location it does not know. So `v0.2.0` taught `engine-update` to accept and check `.vale.ini` and `.vale/styles/vaultkit/`, and `v0.3.0` shipped the Vale files themselves. A vault must take `v0.2.0` before `v0.3.0`.

The most reusable finding is the config allowlist. `engine-update` copies files from a fetched ref, and a Vale config can make Vale run programs (`Transform` runs `xsltproc`) or read paths outside the vault (`StylesPath`). So `vaultconf.vale_errors` allows only `StylesPath = .vale/styles`, `MinAlertLevel`, and a few per-glob keys. Review found it bypassable twice:

| Round | Python read | Vale (go-ini) read | Effect |
|---|---|---|---|
| 1 | `configparser`: an indented line continues the previous value | a new key or section | `[formats]`, `Transform`, or `[DEFAULT]` hidden under `TokenIgnores` passed |
| 2 | `str.splitlines()`: U+2028, U+0085 and other separators end a line | one line | `StylesPath = .vale/styles<U+2028>#/../../scripts` passed; Vale resolves it to `scripts/` |

The fix replaced `configparser` with a strict line parser. It splits on `\n` only and refuses indented lines, `\r`, every other line separator, continuations, quoted multi-line values, duplicate keys and `[DEFAULT]`. Anything the two parsers might read differently is refused, not interpreted. `engine-update` also refuses any engine file that is not UTF-8 or that contains C0, C1, bidi or line-separator characters.

An outside review (CodeRabbit on #9) found a second class: checking out the fetched ref runs any smudge or process filter the developer has configured, wherever the fetched `.gitattributes` selects it, before anything is reviewed. `engine-update` now clones with `--no-checkout` and `transfer.fsckObjects`, then writes the tree from raw blobs through one `git cat-file --batch` call, refusing `..`, `.git` and symlinked path components. Vale rule YAML now loads with a loader that refuses a repeated key, because PyYAML keeps the last of two `extends:` lines.

The gitleaks downloader was refactored into `scripts/pinnedbin.py`, shared with `scripts/vale`. Its review found that the new cache-ownership check refused directories the wrapper itself had created under umask 002, the Ubuntu and Fedora default. That would have blocked every gitleaks run there. Missing cache levels are now created 0700 whatever the umask.

## Evidence and verification

- About 40 staged breaks, one per safeguard: each was a working-tree edit that removed the safeguard, made its test go red, and was then restored.
- `make test` passed at each merge (9 suites at `v0.3.0`), and CI passed on #9 and #12.
- `vale test --coverage .vale/styles/vaultkit` passes the tests embedded in each rule.
- First vault rollout: both engine-update PRs passed `make render-skills && make check && make test`, and every engine file was byte-identical to its tag. After `v0.3.0`, `make prose` reported 6 alerts in 26 files there, all `sentence-length`, against 57 in vault-kit.
- Vale pins were checked against the release's `checksums.txt` for darwin arm64, darwin x64 and linux x64.

## What changed for future work

- Vale merges the user's global config and styles unless it is passed `--no-global`. `scripts/prose` always passes `--config .vale.ini --no-global`, so results do not depend on the machine.
- BSD `stat -f` succeeds on Linux with a different meaning, so a fallback to GNU `stat -c` never ran in CI. Try `stat -c '%a'` first.
- Bash ignores the exit status of a `< <(...)` process substitution. The CI prose step writes `git diff` names to a file first, so a failed diff stops the step instead of reading as "no Markdown changed".
- A pre-post text scan helps only if posting depends on its exit status. One posting loop printed the scan's finding and posted anyway; the text was edited out, but GitHub's edit history keeps it. Chain the post with `&&` after the scan.
- A local pre-push guard that scans tag contents cannot resolve a tag that does not exist yet. Create the tag in one command and push it in the next.

## Unresolved work

- cameronsjo/vault-kit#10: the CI secret scan runs scanner code from the change it scans.
- cameronsjo/vault-kit#11: the tripwire secret reaches every test suite.
- cameronsjo/vault-kit#13: a shared, non-sticky cache ancestor allows a swap between the hash check and exec.
- No Linux arm64 Vale pin; that platform fails closed.
- No page type answers the Diátaxis "learn by doing" question yet.
