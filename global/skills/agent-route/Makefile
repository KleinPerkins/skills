.PHONY: help test verify doctor

SKILL_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
REPO_DIR := $(abspath $(SKILL_DIR)/../../..)

help:
	@echo "test/verify: synthetic source-backed consumer package checks"
	@echo "doctor: read-only optional dependency check"

test verify:
	@python3 -B -m unittest discover -s "$(REPO_DIR)/scripts/tests" -p 'test_ecosystem_consumers.py'

doctor:
	@bash "$(SKILL_DIR)/install.sh" --doctor
