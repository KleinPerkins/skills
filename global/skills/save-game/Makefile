.PHONY: help test verify install-local

SKILL_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
REPO_ROOT := $(shell git -C "$(SKILL_DIR)" rev-parse --show-toplevel)

help:
	@echo "save-game Makefile targets:"
	@echo "  make test          - unit tests (stdlib, auto-discovered under tests/)"
	@echo "  make verify        - unit tests + repo-wide skills verifier"
	@echo "  make install-local - run install.sh"

# -s tests + -p 'test_*.py' auto-discovers every test module later phases add;
# this target never needs editing as the engine grows.
test:
	@python3 -m unittest discover -s "$(SKILL_DIR)/tests" -p 'test_*.py' -v

verify: test
	@cd "$(REPO_ROOT)" && bash .github/scripts/verify-skills.sh

install-local:
	@bash "$(SKILL_DIR)/install.sh"
