SHELL := /usr/bin/env bash

ROOT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
SHARED_REPO ?= $(ROOT_DIR)
PRIVATE_REPO ?= $(ROOT_DIR)/../agent-skills-private

ACTIVE_DIR  ?= $(HOME)/.claude/skills.active
SKILLS_DIR  ?= $(HOME)/.claude/skills

# warn | fail | allow
COLLISION_MODE ?= warn

# shared machine clients
LAYERS_ORDER ?= shared machine clients

ASSEMBLE := ./assemble.sh

.PHONY: help list doctor clean apply dry-run

help:
	@echo "make list"
	@echo "make doctor"
	@echo "make apply PROFILE=my-machine"
	@echo "make apply MACHINE=my-machine CLIENTS='my-client my-other-client'"
	@echo "make dry-run PROFILE=my-machine"
	@echo "make clean"
	@echo ""
	@echo "Vars:"
	@echo "  COLLISION_MODE=$(COLLISION_MODE)  (warn|fail|allow)"
	@echo "  LAYERS_ORDER='$(LAYERS_ORDER)'"

list:
	@SHARED_REPO="$(SHARED_REPO)" PRIVATE_REPO="$(PRIVATE_REPO)" \
	  ACTIVE_DIR="$(ACTIVE_DIR)" SKILLS_DIR="$(SKILLS_DIR)" \
	  COLLISION_MODE="$(COLLISION_MODE)" LAYERS_ORDER="$(LAYERS_ORDER)" \
	  $(ASSEMBLE) list

doctor:
	@SHARED_REPO="$(SHARED_REPO)" PRIVATE_REPO="$(PRIVATE_REPO)" \
	  ACTIVE_DIR="$(ACTIVE_DIR)" SKILLS_DIR="$(SKILLS_DIR)" \
	  COLLISION_MODE="$(COLLISION_MODE)" LAYERS_ORDER="$(LAYERS_ORDER)" \
	  $(ASSEMBLE) doctor

clean:
	@SHARED_REPO="$(SHARED_REPO)" PRIVATE_REPO="$(PRIVATE_REPO)" \
	  ACTIVE_DIR="$(ACTIVE_DIR)" SKILLS_DIR="$(SKILLS_DIR)" \
	  COLLISION_MODE="$(COLLISION_MODE)" LAYERS_ORDER="$(LAYERS_ORDER)" \
	  $(ASSEMBLE) clean

apply:
	@SHARED_REPO="$(SHARED_REPO)" PRIVATE_REPO="$(PRIVATE_REPO)" \
	  ACTIVE_DIR="$(ACTIVE_DIR)" SKILLS_DIR="$(SKILLS_DIR)" \
	  COLLISION_MODE="$(COLLISION_MODE)" LAYERS_ORDER="$(LAYERS_ORDER)" \
	  $(ASSEMBLE) apply \
	    $(if $(PROFILE),--profile "$(PROFILE)",) \
	    $(if $(MACHINE),--machine "$(MACHINE)",) \
	    $(if $(CLIENTS),--clients "$(CLIENTS)",)

dry-run:
	@SHARED_REPO="$(SHARED_REPO)" PRIVATE_REPO="$(PRIVATE_REPO)" \
	  ACTIVE_DIR="$(ACTIVE_DIR)" SKILLS_DIR="$(SKILLS_DIR)" \
	  COLLISION_MODE="$(COLLISION_MODE)" LAYERS_ORDER="$(LAYERS_ORDER)" \
	  $(ASSEMBLE) apply --dry-run \
	    $(if $(PROFILE),--profile "$(PROFILE)",) \
	    $(if $(MACHINE),--machine "$(MACHINE)",) \
	    $(if $(CLIENTS),--clients "$(CLIENTS)",)
