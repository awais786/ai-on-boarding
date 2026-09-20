from django.db import migrations


class Migration(migrations.Migration):
    """Email is unique per organization now (Membership), not across the whole table.

    The index was created by a post_migrate hook in apps.py, not by a model, so no model
    change would ever remove it: with it in place the same email could not exist in two
    organizations.
    """

    dependencies = [('api', '0006_default_organization')]

    operations = [
        migrations.RunSQL(
            sql='DROP INDEX IF EXISTS api_auth_user_email_unique;',
            reverse_sql=(
                'CREATE UNIQUE INDEX IF NOT EXISTS api_auth_user_email_unique '
                'ON auth_user (email);'
            ),
        )
    ]
