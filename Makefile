ifeq ($(OS),Windows_NT)
PYTHON := .venv/Scripts/python.exe
NPM := npm.cmd
else
PYTHON := .venv/bin/python
NPM := npm
endif

.PHONY: test-unit test

test-unit:
	"$(PYTHON)" -m pytest

test:
	"$(PYTHON)" -m ruff check src tests
	"$(PYTHON)" -m mypy src
	"$(PYTHON)" -m pytest
	"$(NPM)" --prefix web run lint
	"$(NPM)" --prefix web run typecheck
