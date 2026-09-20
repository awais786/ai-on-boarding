from collections import defaultdict

from django.db import migrations


def assign_existing_users(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    Organization = apps.get_model('api', 'Organization')
    Membership = apps.get_model('api', 'Membership')

    users = list(User.objects.order_by('pk'))

    # Refuse rather than choose between two accounts that would collide (the old email
    # index normally prevents this, but it was only ever created by a hook).
    by_email = defaultdict(list)
    by_username = defaultdict(list)
    for user in users:
        if user.email:
            by_email[user.email.lower()].append(user.username)
        by_username[user.username.lower()].append(user.username)
    clashes = [
        f'{kind} {value!r}: accounts {names}'
        for kind, table in (('email', by_email), ('username', by_username))
        for value, names in table.items()
        if len(names) > 1
    ]
    if clashes:
        raise RuntimeError(
            'Cannot place existing accounts in one organization; resolve these clashes and '
            'retry: ' + '; '.join(clashes)
        )

    organization, _ = Organization.objects.get_or_create(
        slug='default', defaults={'name': 'Default'}
    )
    Membership.objects.bulk_create(
        Membership(
            user=user,
            organization=organization,
            email=user.email.lower(),
            username=user.username.lower(),
        )
        for user in users
    )


def remove_default_organization(apps, schema_editor):
    apps.get_model('api', 'Membership').objects.all().delete()
    apps.get_model('api', 'Organization').objects.filter(slug='default').delete()


class Migration(migrations.Migration):

    dependencies = [('api', '0005_organization_membership')]

    operations = [migrations.RunPython(assign_existing_users, remove_default_organization)]
