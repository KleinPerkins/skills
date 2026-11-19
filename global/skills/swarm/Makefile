.PHONY: test benchmark verify install-local

SKILL_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

test:
	@python3 -m unittest discover -s "$(SKILL_DIR)/tests" -p 'test_*.py' -v

benchmark:
	@printf '%s\n' 'offline deterministic marker fixture; not an agent benchmark'
	@python3 "$(SKILL_DIR)/tests/test_benchmark.py"

verify:
	@bash "$(SKILL_DIR)/tests/run_tests.sh"

install-local:
	@bash "$(SKILL_DIR)/install.sh"
