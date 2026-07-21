SHELL := /usr/bin/env bash

ROOT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
SHARED_REPO ?= $(ROOT_DIR)
PRIVATE_REPO ?= $(ROOT_DIR)/../agent-skills-private

SKILLS_DIR ?= $(HOME)/.agents/skills
CLAUDE_SKILLS_DIR ?= $(HOME)/.claude/skills
LEGACY_CODEX_SKILLS_DIR ?= $(HOME)/.codex/skills
AGENTS_DIR ?= $(HOME)/.claude/agents

# shared private machine clients
LAYERS_ORDER ?= shared private machine clients

ASSEMBLE := ./assemble.sh

COMMON_ENV := SHARED_REPO="$(SHARED_REPO)" PRIVATE_REPO="$(PRIVATE_REPO)" \
  SKILLS_DIR="$(SKILLS_DIR)" CLAUDE_SKILLS_DIR="$(CLAUDE_SKILLS_DIR)" \
  LEGACY_CODEX_SKILLS_DIR="$(LEGACY_CODEX_SKILLS_DIR)" \
  LAYERS_ORDER="$(LAYERS_ORDER)"
CLAUDE_ENV := $(COMMON_ENV) AGENTS_DIR="$(AGENTS_DIR)"
CODEX_ENV := $(COMMON_ENV) SKIP_AGENTS=1

.PHONY: help clean-code validate-skills test-validate-skills test-assemble test-second-opinion list doctor doctor-codex clean clean-dry-run apply apply-codex dry-run dry-run-codex

help:
	@echo "make clean-code"
	@echo "make validate-skills"
	@echo "make test-validate-skills"
	@echo "make test-assemble"
	@echo "make test-second-opinion"
	@echo "make list"
	@echo "make doctor"
	@echo "make doctor-codex    # compatibility alias; same shared skill root"
	@echo "make apply PROFILE=my-machine"
	@echo "make apply MACHINE=my-machine CLIENTS='my-client my-other-client'"
	@echo "make apply-codex PROFILE=my-machine  # compatibility alias; skips agents"
	@echo "make dry-run PROFILE=my-machine"
	@echo "make dry-run-codex PROFILE=my-machine"
	@echo "make clean"
	@echo "make clean-dry-run"
	@echo ""
	@echo "Vars:"
	@echo "  SKILLS_DIR=$(SKILLS_DIR)"
	@echo "  CLAUDE_SKILLS_DIR=$(CLAUDE_SKILLS_DIR)"
	@echo "  LEGACY_CODEX_SKILLS_DIR=$(LEGACY_CODEX_SKILLS_DIR)"
	@echo "  LAYERS_ORDER='$(LAYERS_ORDER)'"

clean-code:
	@command -v shellcheck >/dev/null 2>&1 || { echo "ERROR: shellcheck is required" >&2; exit 127; }
	@find . -type f -name '*.sh' -not -path './.git/*' -exec bash -n {} \;
	@find . -type f -name '*.sh' -not -path './.git/*' -exec shellcheck --severity=warning {} +

validate-skills:
	@python3 scripts/validate-skills.py

test-validate-skills:
	@python3 -m unittest discover -s tests -p 'test_validate_skills.py'

test-assemble:
	@python3 -m unittest discover -s tests -p 'test_assemble.py'

test-second-opinion:
	@skills/second-opinion/tests/test-review-panel.sh
	@skills/second-opinion/tests/test-openrouter-panel.sh

list:
	@$(CLAUDE_ENV) $(ASSEMBLE) list

doctor:
	@$(CLAUDE_ENV) $(ASSEMBLE) doctor

doctor-codex:
	@$(CODEX_ENV) $(ASSEMBLE) doctor

clean:
	@$(CLAUDE_ENV) $(ASSEMBLE) clean

clean-dry-run:
	@$(CLAUDE_ENV) $(ASSEMBLE) clean --dry-run

apply:
	@$(CLAUDE_ENV) $(ASSEMBLE) apply \
	    $(if $(PROFILE),--profile "$(PROFILE)",) \
	    $(if $(MACHINE),--machine "$(MACHINE)",) \
	    $(if $(CLIENTS),--clients "$(CLIENTS)",)

apply-codex:
	@$(CODEX_ENV) $(ASSEMBLE) apply \
	    $(if $(PROFILE),--profile "$(PROFILE)",) \
	    $(if $(MACHINE),--machine "$(MACHINE)",) \
	    $(if $(CLIENTS),--clients "$(CLIENTS)",)

dry-run:
	@$(CLAUDE_ENV) $(ASSEMBLE) apply --dry-run \
	    $(if $(PROFILE),--profile "$(PROFILE)",) \
	    $(if $(MACHINE),--machine "$(MACHINE)",) \
	    $(if $(CLIENTS),--clients "$(CLIENTS)",)

dry-run-codex:
	@$(CODEX_ENV) $(ASSEMBLE) apply --dry-run \
	    $(if $(PROFILE),--profile "$(PROFILE)",) \
	    $(if $(MACHINE),--machine "$(MACHINE)",) \
	    $(if $(CLIENTS),--clients "$(CLIENTS)",)
