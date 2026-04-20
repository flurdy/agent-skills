SHELL := /usr/bin/env bash

ROOT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
SHARED_REPO ?= $(ROOT_DIR)
PRIVATE_REPO ?= $(ROOT_DIR)/../agent-skills-private

ACTIVE_DIR  ?= $(HOME)/.claude/skills.active
SKILLS_DIR  ?= $(HOME)/.claude/skills
AGENTS_DIR  ?= $(HOME)/.claude/agents

# warn | fail | allow
COLLISION_MODE ?= warn

# shared private machine clients
LAYERS_ORDER ?= shared private machine clients

ASSEMBLE := ./assemble.sh

# Common env for Claude targets (skills + agents)
CLAUDE_ENV := SHARED_REPO="$(SHARED_REPO)" PRIVATE_REPO="$(PRIVATE_REPO)" \
  ACTIVE_DIR="$(ACTIVE_DIR)" SKILLS_DIR="$(SKILLS_DIR)" AGENTS_DIR="$(AGENTS_DIR)" \
  COLLISION_MODE="$(COLLISION_MODE)" LAYERS_ORDER="$(LAYERS_ORDER)"

# Codex has no sub-agent concept — skip the agents layer
CODEX_ENV := SHARED_REPO="$(SHARED_REPO)" PRIVATE_REPO="$(PRIVATE_REPO)" \
  ACTIVE_DIR="$(ACTIVE_DIR)" SKILLS_DIR="$(HOME)/.codex/skills" \
  COLLISION_MODE="$(COLLISION_MODE)" LAYERS_ORDER="$(LAYERS_ORDER)" \
  SKIP_AGENTS=1

.PHONY: help list doctor doctor-codex clean clean-dry-run apply apply-codex dry-run dry-run-codex

help:
	@echo "make list"
	@echo "make doctor"
	@echo "make doctor-codex"
	@echo "make apply PROFILE=my-machine"
	@echo "make apply MACHINE=my-machine CLIENTS='my-client my-other-client'"
	@echo "make apply-codex PROFILE=my-machine"
	@echo "make apply FORCE=1    # skip safety check for non-symlinks"
	@echo "make dry-run PROFILE=my-machine"
	@echo "make dry-run-codex PROFILE=my-machine"
	@echo "make clean"
	@echo "make clean FORCE=1    # skip safety check for non-symlinks"
	@echo "make clean-dry-run"
	@echo ""
	@echo "Vars:"
	@echo "  COLLISION_MODE=$(COLLISION_MODE)  (warn|fail|allow)"
	@echo "  LAYERS_ORDER='$(LAYERS_ORDER)'"
	@echo "  FORCE=1  (skip safety check for user content in ACTIVE_DIR)"

list:
	@$(CLAUDE_ENV) $(ASSEMBLE) list

doctor:
	@$(CLAUDE_ENV) $(ASSEMBLE) doctor

doctor-codex:
	@$(CODEX_ENV) $(ASSEMBLE) doctor

clean:
	@$(CLAUDE_ENV) $(ASSEMBLE) clean $(if $(FORCE),--force,)

clean-dry-run:
	@$(CLAUDE_ENV) $(ASSEMBLE) clean --dry-run

apply:
	@$(CLAUDE_ENV) $(ASSEMBLE) apply \
	    $(if $(PROFILE),--profile "$(PROFILE)",) \
	    $(if $(MACHINE),--machine "$(MACHINE)",) \
	    $(if $(CLIENTS),--clients "$(CLIENTS)",) \
	    $(if $(FORCE),--force,)

apply-codex:
	@$(CODEX_ENV) $(ASSEMBLE) apply \
	    $(if $(PROFILE),--profile "$(PROFILE)",) \
	    $(if $(MACHINE),--machine "$(MACHINE)",) \
	    $(if $(CLIENTS),--clients "$(CLIENTS)",) \
	    $(if $(FORCE),--force,)

dry-run:
	@$(CLAUDE_ENV) $(ASSEMBLE) apply --dry-run \
	    $(if $(PROFILE),--profile "$(PROFILE)",) \
	    $(if $(MACHINE),--machine "$(MACHINE)",) \
	    $(if $(CLIENTS),--clients "$(CLIENTS)",) \
	    $(if $(FORCE),--force,)

dry-run-codex:
	@$(CODEX_ENV) $(ASSEMBLE) apply --dry-run \
	    $(if $(PROFILE),--profile "$(PROFILE)",) \
	    $(if $(MACHINE),--machine "$(MACHINE)",) \
	    $(if $(CLIENTS),--clients "$(CLIENTS)",) \
	    $(if $(FORCE),--force,)
