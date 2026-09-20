"""Tests for specs/tenant-organizations/spec.md, written from the spec.

Each requirement and what a test needs to observe to protect it:

- Describe an organization -> name, slug, both timestamps and an active flag exist.
- Keep organization slugs unique -> a duplicate slug, and a slug that is not lowercase
  letters/digits/hyphens, are refused by the database itself, whatever wrote the row.
- Create organizations only through an operator command -> the command creates one, and no
  API route creates, edits or deletes one.
- Issue a join code once -> printed at creation and rotation, stored only as a digest, and a
  rotated-away code stops working.
- Every user belongs to exactly one organization -> a second membership is refused, and a
  signup that fails midway leaves no account behind.
- Keep email and username unique within an organization only -> allowed across two
  organizations, refused within one.
- Move existing users into a default organization -> the upgrade places them there, they can
  still sign in, and signup into it stays closed until a code is issued.
- Let an operator deactivate an organization -> its users cannot sign in or sign up, and can
  again once it is reactivated.
"""

from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from rest_framework.test import APIClient

from api.factories import create_member, make_organization
from api.models import Membership, Organization


def run(command, *args):
    out = StringIO()
    call_command(command, *args, stdout=out)
    return out.getvalue()


def printed_code(output):
    return output.strip().splitlines()[-1]


def signup(client, organization, join_code, email='ada@example.com', username='ada'):
    return client.post(
        '/api/signup/',
        {
            'organization': organization,
            'join_code': join_code,
            'email': email,
            'username': username,
            'password': 'lovelace1',
            'country': 'France',
        },
        format='json',
    )


def signin(client, organization, identifier='ada', password='lovelace1'):
    return client.post(
        '/api/signin/',
        {'organization': organization, 'email_or_username': identifier, 'password': password},
        format='json',
    )


# Requirement: Describe an organization


@pytest.mark.django_db
def test_a_new_organization_is_active_and_carries_name_slug_and_timestamps():
    run('create_organization', 'Acme Inc', 'acme')

    organization = Organization.objects.get(slug='acme')
    assert organization.name == 'Acme Inc'
    assert organization.is_active is True
    assert organization.created_at is not None
    assert organization.updated_at is not None


# Requirement: Keep organization slugs unique


@pytest.mark.django_db
def test_a_duplicate_slug_is_refused_by_the_database():
    make_organization('acme')

    with pytest.raises(IntegrityError), transaction.atomic():
        Organization.objects.create(name='Other', slug='acme')

    assert Organization.objects.filter(slug='acme').count() == 1


@pytest.mark.django_db
def test_a_slug_differing_only_in_case_is_refused():
    make_organization('acme')

    with pytest.raises(IntegrityError), transaction.atomic():
        Organization.objects.create(name='Other', slug='ACME')

    assert Organization.objects.exclude(slug='default').count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize('slug', ['acme_inc', 'acme inc', 'acme.inc', 'Acme', ''])
def test_a_slug_with_a_disallowed_character_is_refused(slug):
    with pytest.raises(IntegrityError), transaction.atomic():
        Organization.objects.create(name='Other', slug=slug)


@pytest.mark.django_db
def test_the_command_refuses_a_duplicate_or_malformed_slug():
    run('create_organization', 'Acme', 'acme')

    with pytest.raises(CommandError):
        run('create_organization', 'Other', 'acme')
    with pytest.raises(CommandError):
        run('create_organization', 'Other', 'Not_Valid')

    assert Organization.objects.exclude(slug='default').count() == 1


# Requirement: Create organizations only through an operator command


@pytest.mark.django_db
def test_no_api_route_creates_edits_or_deletes_an_organization():
    admin = create_member('root', 'root@example.com', is_staff=True)
    client = APIClient()
    client.force_authenticate(admin)

    for path in ('/api/organizations/', '/api/organizations/acme/', '/api/organization/'):
        for method in ('post', 'put', 'patch', 'delete'):
            assert getattr(client, method)(path).status_code == 404, (method, path)

    from api import urls

    assert not [p for p in urls.urlpatterns if 'organization' in str(p.pattern)]


# Requirement: Issue a join code once


@pytest.mark.django_db
def test_the_join_code_is_printed_at_creation_and_opens_signup():
    output = run('create_organization', 'Acme', 'acme')

    assert signup(APIClient(), 'acme', printed_code(output)).status_code == 200


@pytest.mark.django_db
def test_the_stored_join_credential_is_not_the_code():
    code = printed_code(run('create_organization', 'Acme', 'acme'))

    digest = Organization.objects.get(slug='acme').join_code_digest
    assert digest and digest != code
    assert code not in digest


@pytest.mark.django_db
def test_no_later_command_reveals_the_code_again():
    code = printed_code(run('create_organization', 'Acme', 'acme'))

    listing = run('rotate_join_code', 'acme')

    assert code not in listing


@pytest.mark.django_db
def test_rotating_replaces_the_previous_code():
    old = printed_code(run('create_organization', 'Acme', 'acme'))
    new = printed_code(run('rotate_join_code', 'acme'))

    assert new != old
    assert signup(APIClient(), 'acme', old).status_code == 400
    assert signup(APIClient(), 'acme', new).status_code == 200


@pytest.mark.django_db
def test_rotating_an_unknown_organization_is_an_error():
    with pytest.raises(CommandError):
        run('rotate_join_code', 'nowhere')


# Requirement: Every user belongs to exactly one organization


@pytest.mark.django_db
def test_an_account_cannot_be_given_a_second_organization():
    user = create_member('ada', 'ada@example.com', organization='acme')
    other = make_organization('globex')

    with pytest.raises(IntegrityError), transaction.atomic():
        Membership.objects.create(user=user, organization=other, email='x@y.z', username='ada')

    assert Membership.objects.get(user=user).organization.slug == 'acme'


@pytest.mark.django_db
def test_a_signup_that_fails_before_attaching_leaves_no_account():
    code = make_organization('acme').issue_join_code()

    with patch('api.serializers.record_account_country', side_effect=RuntimeError('boom')):
        with pytest.raises(RuntimeError):
            signup(APIClient(), 'acme', code)

    assert User.objects.count() == 0
    assert Membership.objects.count() == 0


@pytest.mark.django_db
def test_a_signed_up_account_belongs_to_the_organization_named():
    acme_code = make_organization('acme').issue_join_code()
    make_organization('globex').issue_join_code()

    signup(APIClient(), 'acme', acme_code)

    assert Membership.objects.get().organization.slug == 'acme'


# Requirement: Keep email and username unique within an organization only


@pytest.mark.django_db
def test_the_same_email_and_username_can_exist_in_two_organizations():
    create_member('ada', 'ada@example.com', organization='acme')
    create_member('ada', 'ada@example.com', organization='globex')

    assert Membership.objects.filter(email='ada@example.com', username='ada').count() == 2


@pytest.mark.django_db
def test_the_same_email_twice_in_one_organization_is_refused_by_the_database():
    create_member('ada', 'ada@example.com', organization='acme')

    with pytest.raises(IntegrityError), transaction.atomic():
        create_member('grace', 'ada@example.com', organization='acme')


@pytest.mark.django_db
def test_the_same_username_twice_in_one_organization_is_refused_by_the_database():
    create_member('ada', 'ada@example.com', organization='acme')

    with pytest.raises(IntegrityError), transaction.atomic():
        create_member('ada', 'other@example.com', organization='acme')


# Requirement: Let an operator deactivate an organization


@pytest.mark.django_db
def test_deactivating_an_organization_closes_signin_and_signup_and_reactivating_reopens_them():
    organization = make_organization('acme')
    code = organization.issue_join_code()
    create_member('ada', 'ada@example.com', organization=organization)
    client = APIClient()

    organization.is_active = False
    organization.save()
    assert signin(client, 'acme').status_code == 401
    assert signup(client, 'acme', code, 'new@example.com', 'newbie').status_code == 400
    assert User.objects.count() == 1  # data left intact

    organization.is_active = True
    organization.save()
    assert signin(client, 'acme').status_code == 200


# Requirement: Move existing users into a default organization


def migrate_to(target):
    executor = MigrationExecutor(connection)
    executor.migrate([target])
    return executor.loader.project_state([target]).apps


def migrate_to_latest():
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(executor.loader.graph.leaf_nodes())


@pytest.fixture
def before_tenancy(transactional_db):
    """The database as it was before organizations existed, restored to latest afterwards."""
    apps = migrate_to(('api', '0004_signinattempt_window_started_at'))
    yield apps
    migrate_to_latest()


@pytest.mark.django_db(transaction=True)
def test_existing_accounts_land_in_the_default_organization_and_can_still_sign_in(before_tenancy):
    old_user = before_tenancy.get_model('auth', 'User')
    from django.contrib.auth.hashers import make_password

    old_user.objects.create(
        username='Ada', email='Ada@Example.com', password=make_password('lovelace1')
    )
    old_user.objects.create(
        username='grace', email='grace@example.com', password=make_password('hopper12')
    )

    migrate_to_latest()

    members = Membership.objects.select_related('organization')
    assert {m.organization.slug for m in members} == {'default'}
    assert Membership.objects.count() == 2
    assert signin(APIClient(), 'default', 'ada@example.com').status_code == 200
    assert signin(APIClient(), 'default', 'grace', 'hopper12').status_code == 200


@pytest.mark.django_db(transaction=True)
def test_the_default_organization_is_closed_to_signup_until_a_code_is_issued(before_tenancy):
    migrate_to_latest()

    assert signup(APIClient(), 'default', 'anything-at-all').status_code == 400
    assert signup(APIClient(), 'default', '').status_code == 400

    code = printed_code(run('rotate_join_code', 'default'))
    assert signup(APIClient(), 'default', code).status_code == 200


@pytest.mark.django_db(transaction=True)
def test_the_upgrade_refuses_to_guess_between_clashing_accounts(before_tenancy):
    old_user = before_tenancy.get_model('auth', 'User')
    old_user.objects.create(username='Ada', email='a1@example.com')
    old_user.objects.create(username='ada', email='a2@example.com')

    with pytest.raises(RuntimeError, match='ada'):
        migrate_to(('api', '0006_default_organization'))
    assert not Organization.objects.filter(slug='default').exists()

    old_user.objects.all().delete()  # so the fixture can migrate forward again


@pytest.mark.django_db(transaction=True)
def test_the_default_organization_starts_with_no_join_code_at_all(before_tenancy):
    migrate_to_latest()

    assert Organization.objects.get(slug='default').join_code_digest == ''
