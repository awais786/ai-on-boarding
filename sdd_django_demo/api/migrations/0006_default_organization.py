from collections import defaultdict

from django.db import migrations


def assign_existing_users(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    Organization = apps.get_model('api', 'Organization')
    Membership = apps.get_model('api', 'Membership')

    # Only users with no membership anywhere: makes this safe to re-run after a rollback
    # that left some users already assigned (to 'default', or - via direct ORM use outside
    # this migration - to some other organization). Re-inserting a membership for one of
    # those would collide with Membership.user's own uniqueness.
    users = list(User.objects.filter(membership__isnull=True).order_by('pk'))

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
    Organization = apps.get_model('api', 'Organization')
    default = Organization.objects.filter(slug='default').first()
    if default is None:
        return
    # Only this migration's own memberships: an organization created after the upgrade (and
    # its memberships) must survive a rollback of this migration untouched.
    apps.get_model('api', 'Membership').objects.filter(organization=default).delete()
    default.delete()


class Migration(migrations.Migration):

    dependencies = [('api', '0005_organization_membership')]

    operations = [migrations.RunPython(assign_existing_users, remove_default_organization)]
