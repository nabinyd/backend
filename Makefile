.PHONY: run watch worker watch-worker venv activate install freeze

PY := .venv/bin/python
PIP := .venv/bin/pip

run:
	$(PY) run.py

watch:
	watchfiles "$(PY) run.py" app

worker:
	$(PY) worker_runner.py

watch-worker:
	watchfiles "$(PY) worker_runner.py" app

venv:
	python3 -m venv .venv

activate:
	@echo "Run this in your shell:"
	@echo "source .venv/bin/activate"

install:
	$(PIP) install -r requirements.txt

freeze:
	$(PIP) freeze > requirements.txt
