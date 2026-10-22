.PHONY: setup check secrets deny-range check-initialized indexes merge-log refresh retrieval retrieval-setup retrieval-teardown test-retrieval install-hooks uninstall-hooks test-hooks test-install test-engine-update test-init test-tripwire test-md-outline test-vale test engine-update render-skills
# The repository virtualenv (.venv, gitignored, made by make setup) when scripts/venv-python
# says it is safe to run (untracked, not a symlink; a worktree falls back to the primary
# checkout's), else python3. Override with PYTHON=<interpreter>; check-staged.py passes its
# own, and CI passes PYTHON=python3.
VENV_PYTHON := $(shell sh scripts/venv-python 2>/dev/null)
PYTHON ?= $(or $(VENV_PYTHON),python3)
# When the venv's interpreter is the one in use, the python3 that scripts and tests start is
# the venv's too. Never otherwise: a PATH entry inside the checkout could replace git.
ifneq ($(VENV_PYTHON),)
ifeq ($(PYTHON),$(VENV_PYTHON))
export PATH := $(dir $(VENV_PYTHON)):$(PATH)
endif
endif
# make setup builds .venv with this interpreter (3.11 or newer), e.g. SETUP_PYTHON=python3.12.
SETUP_PYTHON ?= python3
.PHONY: test-env

# Creates .venv, installs requirements-dev.txt into it (nothing outside the repository), and
# installs the Git hooks. Homebrew's Python refuses a global pip install (PEP 668); the venv
# avoids that.
setup:
	$(SETUP_PYTHON) -m venv .venv
	.venv/bin/python3 -m pip install --quiet -r requirements-dev.txt
	.venv/bin/python3 scripts/install-hooks
# DENY_FROM=<path> checks against another copy of vault.toml's deny list (check-staged.py
# passes HEAD's, so a commit cannot empty the list it is checked against).
check:
	$(PYTHON) scripts/check-vault.py $(if $(DENY_FROM),--deny-from "$(DENY_FROM)")
	$(PYTHON) scripts/index-vault.py --check
	$(MAKE) --no-print-directory secrets

# Secret scan with the pinned gitleaks (scripts/scan-secrets.py). SECRETS_MODE picks what it reads:
#   worktree (default)  tracked and untracked files, minus .gitignore'd ones: your edits
#   staged              the index, as the next commit would record it
#   dir                 every file under this directory; check-staged.py uses it on the
#                       staged snapshot, which has no .git, passing SECRETS_POLICY
#   range               commits SECRETS_BASE..HEAD (CI); all history from HEAD when empty
# .gitleaks.toml and .gitleaksignore come from HEAD (SECRETS_BASE in range mode), never
# from the files being scanned. SECRETS_BASE is read from the environment.
SECRETS_MODE ?= worktree
secrets:
	$(PYTHON) scripts/scan-secrets.py $(SECRETS_MODE)

# The [redaction] deny list over every commit SECRETS_BASE..HEAD (CI): messages, path names
# and added lines, with the base commit's deny list. Catches text a later commit removed.
deny-range:
	$(PYTHON) scripts/check-vault.py --deny-range
check-initialized:
	$(PYTHON) scripts/vaultconf.py --check-initialized
indexes:
	$(PYTHON) scripts/index-vault.py
merge-log:
	$(PYTHON) scripts/check-history.py --resolve-merge
# Retrieval: one QMD index per vault, in .qmd/ (gitignored). retrieval-setup registers the
# collection, excludes wiki/log.md, adds context and builds the index; add
# REFRESH_FLAGS=--lexical-only to skip embeddings. retrieval-teardown deletes .qmd/.
# make refresh updates and embeds this vault only.
refresh: check
	./scripts/refresh-qmd

retrieval:
	$(PYTHON) scripts/check-retrieval.py

# scripts/retrieval-setup refuses an uninitialized vault itself, however it is started.
retrieval-setup:
	$(PYTHON) scripts/retrieval-setup setup $(REFRESH_FLAGS)

retrieval-teardown:
	$(PYTHON) scripts/retrieval-setup teardown

install-hooks:
	$(PYTHON) scripts/install-hooks

uninstall-hooks:
	$(PYTHON) scripts/install-hooks --uninstall

test-hooks:
	bash scripts/test-env.sh $(PYTHON) scripts/test-hooks.py

test-install:
	bash scripts/test-env.sh bash scripts/test-install-discovery.sh
test-engine-update:
	bash scripts/test-env.sh bash scripts/test-engine-update.sh
test-init:
	bash scripts/test-env.sh bash scripts/test-init.sh
test-tripwire:
	bash scripts/test-env.sh bash scripts/test-tripwire.sh
test-vale:
	bash scripts/test-env.sh bash scripts/test-vale.sh
test-md-outline:
	bash scripts/test-env.sh bash scripts/test-md-outline.sh
test-env:
	bash scripts/test-env.sh $(PYTHON) scripts/test-test-env.py
test: test-env test-hooks test-install test-engine-update test-init test-tripwire test-md-outline test-vale

# Needs npm QMD installed; not part of `make test`. VAULT_KIT_TEST_SEMANTIC=1 adds the embedding leg.
test-retrieval:
	bash scripts/test-env.sh bash scripts/test-retrieval.sh

# Re-render skills/ from templates/skills/ after editing a template or an engine update.
render-skills:
	$(PYTHON) scripts/init-vault --render-skills

# Pull engine files from a vault-kit tag:
#   make engine-update REF=v0.1.0 [COMMIT=<full-sha>] [SOURCE=<git-url-or-path>]
# It copies files and prints the diff; it runs nothing. Review, then make render-skills check.
engine-update:
	@test -n "$(REF)" || { echo "usage: make engine-update REF=<tag> [COMMIT=<full-sha>] [SOURCE=<git-url-or-path>]" >&2; exit 2; }
	$(PYTHON) scripts/engine-update --ref "$(REF)" $(if $(COMMIT),--commit "$(COMMIT)") $(if $(SOURCE),--source "$(SOURCE)")
