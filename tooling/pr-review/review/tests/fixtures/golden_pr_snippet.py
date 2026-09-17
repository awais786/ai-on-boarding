"""Golden PR fixture for manually evaluating Phase 3's review skills (task 9.3, used
during task 10's manual verification). Contains three deliberately planted issues,
each cleanly mapped to exactly one skill, and none of them things Ruff would ever
flag - the point is to check the AI skills add value beyond the deterministic check,
not to re-test Ruff. Not meant to be merged - a reference/manual-test aid only.
"""
from django.db import connection

SECRET_API_KEY = "not-a-real-secret-placeholder-abcdef123456"  # planted: security


def get_user_orders(user_id):
    # planted: architecture - hand-written SQL reimplementing what the ORM
    # (Order.objects.filter(user_id=...)) already provides, mixing data access
    # directly into what should be a thin view function. Parameterized, so this is
    # NOT a security/injection issue - purely a "shouldn't be written this way" one.
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM orders WHERE user_id = %s", [user_id])
        return cursor.fetchall()


def process(x):
    # planted: code-quality - "process"/"x" give no indication this computes a
    # discount-adjusted total. Ruff has no rule for unclear naming.
    y = x * 0.9 if x > 100 else x
    return y
