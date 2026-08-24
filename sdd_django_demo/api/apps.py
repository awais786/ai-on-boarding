from django.apps import AppConfig
from django.db.models.signals import post_migrate


def create_unique_email_index(sender, **kwargs):
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS api_auth_user_email_unique ON auth_user (email);'
        )


class ApiConfig(AppConfig):
    name = 'api'

    def ready(self):
        post_migrate.connect(create_unique_email_index, sender=self)
