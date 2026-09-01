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

# Writes the OpenAPI schema the api-conformance-testing pipeline derives its
# Postman collection from - see ../postman/README.md.
schema:
	$(PYTHON) manage.py spectacular --file ../postman/schema.json --format openapi-json

# Starts a live instance against a fresh migration for the conformance pipeline
# to run Newman against, and waits until it answers /api/health/. Paired with
# ci-stop, which the workflow always runs afterward regardless of outcome.
ci-serve: migrate
	$(PYTHON) manage.py runserver --noreload 0.0.0.0:8000 > server.log 2>&1 & echo $$! > server.pid
	@for i in $$(seq 1 30); do \
		curl -sf http://127.0.0.1:8000/api/health/ > /dev/null 2>&1 && exit 0; \
		sleep 1; \
	done; \
	echo "Server did not become healthy in time" >&2; cat server.log >&2; exit 1

ci-stop:
	@if [ -f server.pid ]; then kill $$(cat server.pid) 2>/dev/null || true; rm -f server.pid; fi
