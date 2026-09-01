.PHONY: setup migrate run test check schema ci-serve ci-stop

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

# Regenerates the OpenAPI schema that the Postman collection (../postman/) is derived
# from - see ../postman/README.md.
schema:
	$(PYTHON) manage.py spectacular --format openapi-json --file ../postman/schema.json

# Starts a server for the api-behavior-verification pipeline (CI or local) and waits
# until it answers health checks. CI checkouts have no db.sqlite3 (gitignored), so
# `migrate` there always starts from a clean database.
ci-serve: migrate
	$(PYTHON) manage.py runserver 0.0.0.0:8000 > /tmp/ci-serve.log 2>&1 & echo $$! > /tmp/ci-serve.pid
	@for i in $$(seq 1 30); do \
		if curl -sf http://127.0.0.1:8000/api/health/ > /dev/null 2>&1; then \
			echo "Server is up (pid $$(cat /tmp/ci-serve.pid))"; \
			exit 0; \
		fi; \
		sleep 1; \
	done; \
	echo "Server did not become healthy in time" >&2; \
	cat /tmp/ci-serve.log >&2; \
	exit 1

ci-stop:
	@if [ -f /tmp/ci-serve.pid ]; then \
		kill $$(cat /tmp/ci-serve.pid) 2>/dev/null || true; \
		rm -f /tmp/ci-serve.pid; \
	fi
