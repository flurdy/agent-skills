SHELL := /usr/bin/env bash

ROOT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
SHARED_REPO ?= $(ROOT_DIR)
PRIVATE_REPO ?= $(ROOT_DIR)/../agent-skills-private

SKILLS_DIR ?= $(HOME)/.agents/skills
CLAUDE_SKILLS_DIR ?= $(HOME)/.claude/skills
LEGACY_CODEX_SKILLS_DIR ?= $(HOME)/.codex/skills
AGENTS_DIR ?= $(HOME)/.claude/agents
PI_PROMPTS_DIR ?= $(HOME)/.pi/agent/prompts

# shared private machine clients
LAYERS_ORDER ?= shared private machine clients

ASSEMBLE := ./assemble.sh

COMMON_ENV := SHARED_REPO="$(SHARED_REPO)" PRIVATE_REPO="$(PRIVATE_REPO)" \
  SKILLS_DIR="$(SKILLS_DIR)" CLAUDE_SKILLS_DIR="$(CLAUDE_SKILLS_DIR)" \
  LEGACY_CODEX_SKILLS_DIR="$(LEGACY_CODEX_SKILLS_DIR)" \
  PI_PROMPTS_DIR="$(PI_PROMPTS_DIR)" LAYERS_ORDER="$(LAYERS_ORDER)"
CLAUDE_ENV := $(COMMON_ENV) AGENTS_DIR="$(AGENTS_DIR)"
CODEX_ENV := $(COMMON_ENV) SKIP_AGENTS=1 SKIP_PROMPTS=1

.PHONY: help check test lint-python clean-code security-scan validate-skills test-validate-skills test-assemble test-artifact-hygiene test-second-opinion test-trello-beads test-project-brief test-skill-pilot test-architect test-plan-to-backlog test-beads test-next test-handoffs test-pi-spend test-review-pr test-review-requests test-pr-feedback test-pr-feedback-actions test-ready-to-release test-release-ci test-release-order test-release-status test-today test-yesterday test-wrap-up test-watch-admin test-watch-pr-feedback test-watch-prs test-watch-release test-watch-review-requests test-watch-rollouts test-watch-protocols list doctor doctor-codex clean clean-dry-run apply apply-codex dry-run dry-run-codex

help:
	@echo "make check   (clean-code, lint-python, validate-skills, security-scan, test)"
	@echo "make test    (every test-* suite)"
	@echo "make lint-python"
	@echo "make clean-code"
	@echo "make security-scan"
	@echo "make validate-skills"
	@echo "make test-validate-skills"
	@echo "make test-assemble"
	@echo "make test-artifact-hygiene"
	@echo "make test-second-opinion"
	@echo "make test-trello-beads"
	@echo "make test-project-brief"
	@echo "make test-skill-pilot"
	@echo "make test-architect"
	@echo "make test-plan-to-backlog"
	@echo "make test-beads"
	@echo "make test-next"
	@echo "make test-handoffs"
	@echo "make test-pi-spend"
	@echo "make test-review-pr"
	@echo "make test-review-requests"
	@echo "make test-pr-feedback"
	@echo "make test-pr-feedback-actions"
	@echo "make test-ready-to-release"
	@echo "make test-release-ci"
	@echo "make test-release-order"
	@echo "make test-release-status"
	@echo "make test-today"
	@echo "make test-yesterday"
	@echo "make test-wrap-up"
	@echo "make test-watch-admin"
	@echo "make test-watch-pr-feedback"
	@echo "make test-watch-prs"
	@echo "make test-watch-release"
	@echo "make test-watch-review-requests"
	@echo "make test-watch-rollouts"
	@echo "make test-watch-protocols"
	@echo "make list"
	@echo "make doctor"
	@echo "make doctor-codex    # compatibility alias; same shared skill root"
	@echo "make apply PROFILE=my-machine"
	@echo "make apply MACHINE=my-machine CLIENTS='my-client my-other-client'"
	@echo "make apply-codex PROFILE=my-machine  # compatibility alias; skips agents and Pi prompts"
	@echo "make dry-run PROFILE=my-machine"
	@echo "make dry-run-codex PROFILE=my-machine"
	@echo "make clean"
	@echo "make clean-dry-run"
	@echo ""
	@echo "Vars:"
	@echo "  SKILLS_DIR=$(SKILLS_DIR)"
	@echo "  CLAUDE_SKILLS_DIR=$(CLAUDE_SKILLS_DIR)"
	@echo "  LEGACY_CODEX_SKILLS_DIR=$(LEGACY_CODEX_SKILLS_DIR)"
	@echo "  PI_PROMPTS_DIR=$(PI_PROMPTS_DIR)"
	@echo "  LAYERS_ORDER='$(LAYERS_ORDER)'"

clean-code:
	@command -v shellcheck >/dev/null 2>&1 || { echo "ERROR: shellcheck is required" >&2; exit 127; }
	@find . -type f -name '*.sh' -not -path './.git/*' -exec bash -n {} \;
	@find . -type f -name '*.sh' -not -path './.git/*' -exec shellcheck --severity=warning {} +

# Every test-* suite. test-pr-feedback-actions and the individual watch-* suites
# are omitted because test-pr-feedback and test-watch-protocols already run them.
TEST_TARGETS := test-validate-skills test-assemble test-artifact-hygiene \
  test-second-opinion test-trello-beads test-project-brief test-skill-pilot \
  test-architect test-plan-to-backlog test-beads test-next test-handoffs \
  test-pi-spend test-review-pr test-review-requests test-pr-feedback \
  test-ready-to-release test-release-ci test-release-order test-release-status \
  test-today test-yesterday test-wrap-up test-watch-protocols

test: $(TEST_TARGETS)

# The gate a change should pass before review.
check: clean-code lint-python validate-skills security-scan test

lint-python:
	@command -v ruff >/dev/null 2>&1 || { echo "ERROR: ruff is required (pip install ruff)" >&2; exit 127; }
	@ruff check .

security-scan:
	@./scripts/security-scan.sh

validate-skills:
	@python3 scripts/validate-skills.py

test-validate-skills:
	@python3 -m unittest discover -s tests -p 'test_validate_skills.py'

test-assemble:
	@python3 -m unittest discover -s tests -p 'test_assemble.py'

test-artifact-hygiene:
	@skills/artifact-hygiene/tests/test-skill-contract.sh
	@python3 -m unittest discover -s skills/artifact-hygiene/tests -p 'test_artifact_hygiene.py'

test-second-opinion:
	@skills/second-opinion/tests/test-review-panel.sh
	@skills/second-opinion/tests/test-openrouter-panel.sh

test-trello-beads:
	@skills/trello-beads/tests/test_trello_requests.sh
	@skills/trello-beads/tests/test_trello_workflows.sh

test-project-brief:
	@skills/project-brief/tests/test-collect.sh
	@python3 -m unittest discover -s skills/project-brief/tests -p 'test_evaluation.py'

test-skill-pilot:
	@python3 -m unittest discover -s tests -p 'test_run_skill_pilot.py'

test-architect:
	@bash skills/architect/tests/test-skill-contract.sh

test-plan-to-backlog:
	@skills/plan-to-backlog/tests/test-helpers.sh
	@skills/plan-to-backlog/tests/test-skill-contract.sh
	@python3 -m unittest discover -s skills/plan-to-backlog/tests -p 'test_decision_fixtures.py'

test-beads:
	@bash skills/beads/tests/test-skill-contract.sh
	@python3 -m unittest discover -s skills/next/tests -p 'test_next_select.py'

test-next:
	@python3 -m unittest discover -s skills/next/tests -p 'test_*.py'

test-handoffs:
	@python3 -m unittest discover -s skills/handoffs/tests -p 'test_*.py'

test-pi-spend:
	@python3 -m unittest discover -s skills/pi-spend/tests -p 'test_*.py'

test-review-pr:
	@python3 -m unittest discover -s skills/review-pr/tests -p 'test_snapshot.py'
	@bash skills/review-pr/tests/test-wrappers.sh
	@bash skills/review-pr/tests/test-skill-contract.sh

test-review-requests:
	@python3 -m unittest discover -s skills/pr-status/tests -p 'test_review_request_queue.py'
	@python3 -m unittest discover -s skills/pr-status/tests -p 'test_checkout_resolver.py'

test-pr-feedback-actions:
	@bash skills/review-comments/tests/test-attended-contract.sh
	@bash skills/reply-comments/tests/test-attended-contract.sh

test-pr-feedback: test-pr-feedback-actions
	@python3 -m unittest discover -s skills/pr-status/tests -p 'test_feedback_inventory.py'
	@bash skills/pr-status/tests/test-feedback-contract.sh

test-ready-to-release:
	@bash skills/ready-to-release/tests/test-skill-contract.sh

test-release-ci:
	@python3 -m unittest discover -s skills/release-manager/tests -p 'test_release_ci.py'
	@bash skills/release-manager/tests/test-skill-contract.sh

test-release-order:
	@python3 -m unittest discover -s skills/release-manager/tests -p 'test_release_order.py'
	@bash skills/release-manager/tests/test-skill-contract.sh

test-release-status:
	@bash skills/release-status/tests/test-skill-contract.sh

test-today:
	@bash skills/today/tests/test-skill-contract.sh

test-yesterday:
	@bash skills/yesterday/tests/test-skill-contract.sh

test-wrap-up:
	@bash skills/wrap-up/tests/test-activity.sh
	@bash skills/wrap-up/tests/test-handoff-path.sh
	@bash skills/wrap-up/tests/test-skill-contract.sh

test-watch-admin:
	@bash skills/watch-admin/tests/test-skill-contract.sh
	@python3 -m unittest discover -s skills/watch-admin/tests -p 'test_*.py'

test-watch-pr-feedback:
	@bash skills/watch-pr-feedback/tests/test-skill-contract.sh

test-watch-prs:
	@bash skills/watch-prs/tests/test-skill-contract.sh

test-watch-release:
	@bash skills/watch-release/tests/test-skill-contract.sh

test-watch-review-requests:
	@bash skills/watch-review-requests/tests/test-skill-contract.sh

test-watch-rollouts:
	@bash skills/watch-rollout/tests/test-skill-contract.sh
	@bash skills/watch-flux-rollout/tests/test-skill-contract.sh

test-watch-protocols: test-watch-admin test-watch-pr-feedback test-watch-prs test-watch-release test-watch-review-requests test-watch-rollouts

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
