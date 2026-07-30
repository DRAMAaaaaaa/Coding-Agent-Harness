ifeq ($(OS),Windows_NT)
PYTHON := .venv/Scripts/python.exe
NPM := npm.cmd
CHECK_PYTHON = @if not exist "$(PYTHON)" (echo ERROR: Python environment missing; create .venv and install project dependencies. & exit /b 2)
CHECK_NPM = @where "$(NPM)" >NUL 2>NUL || (echo ERROR: npm command missing; install the required Node.js 24 runtime. & exit /b 2)
CHECK_WEB = @if not exist "web\node_modules\" (echo ERROR: Web dependencies missing; run npm --prefix web ci. & exit /b 2)
else
PYTHON := .venv/bin/python
NPM := npm
CHECK_PYTHON = @if [ ! -x "$(PYTHON)" ]; then echo "ERROR: Python environment missing; create .venv and install project dependencies."; exit 2; fi
CHECK_NPM = @command -v "$(NPM)" >/dev/null 2>&1 || { echo "ERROR: npm command missing; install the required Node.js 24 runtime."; exit 2; }
CHECK_WEB = @if [ ! -d web/node_modules ]; then echo "ERROR: Web dependencies missing; run npm --prefix web ci."; exit 2; fi
endif

.PHONY: check-python check-web test-unit test-e2e test demo

check-python:
	$(CHECK_PYTHON)

check-web: check-python
	$(CHECK_NPM)
	$(CHECK_WEB)

test-unit: check-web
	"$(PYTHON)" -m pytest
	"$(NPM)" --prefix web run test -- --run

test-e2e: check-web
	"$(NPM)" --prefix web run build
	"$(NPM)" --prefix web run e2e

test: check-web
	"$(PYTHON)" -m ruff check src tests
	"$(PYTHON)" -m mypy src
	"$(PYTHON)" -m pytest
	"$(NPM)" --prefix web run lint
	"$(NPM)" --prefix web run typecheck
	"$(NPM)" --prefix web run test -- --run
	"$(NPM)" --prefix web run build
	"$(NPM)" --prefix web run e2e

demo: check-python
	"$(PYTHON)" scripts/mechanism_demo.py
