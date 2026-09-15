"""Domain validation rules checked before spending a round trip on a call
the backend would reject anyway. Not a client concern - nothing here talks
to the backend.
"""

import re


class ValidationError(Exception):
    """A tool argument fails a rule this server checks itself, before
    spending a round trip on a call the backend would reject anyway."""


def validate_password_strength(password):
    """Reject a password the backend would reject too, before spending a round trip on it.

    Mirrors sdd_django_demo/api/serializers.py::validate_password_strength - both
    run password_strength_cases.json so a drift between them fails a test.
    """
    if len(password) < 8 or not re.search(r'[A-Za-z]', password) or not re.search(r'\d', password):
        raise ValidationError('Must be at least 8 characters and contain a letter and a digit.')
