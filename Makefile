.PHONY: test test-harness test-django

# The harness has no venv of its own; it reuses the Django project's, which
# already provides the PyYAML and pytest pins in harness/requirements.txt.
PYTHON := sdd_django_demo/.venv/bin/python

test: test-harness test-django

test-harness:
	$(PYTHON) -m pytest harness -v

test-django:
	$(MAKE) -C sdd_django_demo test
