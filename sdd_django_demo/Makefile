.PHONY: setup migrate run test check

VENV := .venv
PYTHON := $(VENV)/bin/python

setup:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -r requirements.txt

migrate:
	$(PYTHON) manage.py migrate

run: migrate
	$(PYTHON) manage.py runserver

test:
	$(PYTHON) -m pytest -v

check:
	$(PYTHON) manage.py check
