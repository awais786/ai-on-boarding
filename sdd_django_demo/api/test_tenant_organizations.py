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

import uuid
from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from rest_framework.test import APIClient

from api.factories import create_member, make_organization
from api.models import Membership, Organization


def new_organization(slug, domain=None, **fields):
    """Create an Organization straight through the ORM, with a Site of its own."""
    domain = domain or f'{slug or "blank"}-{Site.objects.count()}.test'
    site = Site.objects.create(domain=domain, name=slug)
    return Organization.objects.create(name='Other', slug=slug, site=site, **fields)


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
    run('create_organization', 'Acme Inc', 'acme', 'acme.example.com')

    organization = Organization.objects.get(slug='acme')
    assert organization.name == 'Acme Inc'
    assert organization.site.domain == 'acme.example.com'
    assert organization.is_active is True
    assert organization.created_at is not None
    assert organization.updated_at is not None


# Requirement: Keep organization slugs unique


@pytest.mark.django_db
def test_a_duplicate_slug_is_refused_by_the_database():
    make_organization('acme')

    with pytest.raises(IntegrityError), transaction.atomic():
        new_organization('acme')

    assert Organization.objects.filter(slug='acme').count() == 1


@pytest.mark.django_db
def test_a_slug_differing_only_in_case_is_refused():
    make_organization('acme')

    with pytest.raises(IntegrityError), transaction.atomic():
        new_organization('ACME')

    assert Organization.objects.exclude(slug='default').count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize('slug', ['acme_inc', 'acme inc', 'acme.inc', 'Acme', ''])
def test_a_slug_with_a_disallowed_character_is_refused(slug):
    with pytest.raises(IntegrityError), transaction.atomic():
        new_organization(slug)


@pytest.mark.django_db
def test_the_command_refuses_a_duplicate_or_malformed_slug():
    run('create_organization', 'Acme', 'acme', 'acme.example.com')

    with pytest.raises(CommandError):
        run('create_organization', 'Other', 'acme', 'other.example.com')
    with pytest.raises(CommandError):
        run('create_organization', 'Other', 'Not_Valid', 'other.example.com')

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
    output = run('create_organization', 'Acme', 'acme', 'acme.example.com')

    assert signup(APIClient(), 'acme', printed_code(output)).status_code == 200


@pytest.mark.django_db
def test_the_stored_join_credential_is_not_the_code():
    code = printed_code(run('create_organization', 'Acme', 'acme', 'acme.example.com'))

    digest = Organization.objects.get(slug='acme').join_code_digest
    assert digest and digest != code
    assert code not in digest


@pytest.mark.django_db
def test_no_later_command_reveals_the_code_again():
    code = printed_code(run('create_organization', 'Acme', 'acme', 'acme.example.com'))

    listing = run('rotate_join_code', 'acme')

    assert code not in listing


@pytest.mark.django_db
def test_rotating_replaces_the_previous_code():
    old = printed_code(run('create_organization', 'Acme', 'acme', 'acme.example.com'))
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


@pytest.mark.django_db(transaction=True)
def test_rolling_back_the_default_organization_migration_only_touches_default(before_tenancy):
    """0006's reverse must delete only the memberships it created - an organization made after
    the upgrade (and its memberships) must survive a rollback of this migration untouched."""
    migrate_to_latest()
    globex = make_organization('globex')
    survivor = create_member('bob', 'bob@globex.com', organization=globex)

    apps = migrate_to(('api', '0005_organization_membership'))
    HistoricOrganization = apps.get_model('api', 'Organization')
    HistoricMembership = apps.get_model('api', 'Membership')

    assert HistoricOrganization.objects.filter(slug='globex').exists()
    assert HistoricMembership.objects.filter(user_id=survivor.pk).exists()
    assert not HistoricOrganization.objects.filter(slug='default').exists()


@pytest.mark.django_db(transaction=True)
def test_rolling_back_never_deletes_the_default_organizations_site_row(before_tenancy):
    """The reverse migration only detaches the Site, so it can never destroy one this
    migration reused rather than created (design.md D10) - such as the sites app's own
    seeded example.com row, or one an operator made by hand."""
    migrate_to_latest()
    site_pk = Organization.objects.get(slug='default').site_id

    migrate_to(('api', '0007_drop_global_email_unique_index'))

    assert Site.objects.filter(pk=site_pk).exists()


# Requirement: Keep email and username unique within an organization only (database boundary)


@pytest.mark.django_db
def test_a_case_only_duplicate_email_is_refused_by_the_database_directly():
    """A write that skips the serializer (the admin, a shell, a future admin API) must still
    be caught: the constraint compares on the lowercased value, not the raw column."""
    organization = make_organization('acme')
    Membership.objects.create(
        user=User.objects.create_user(username=uuid.uuid4().hex, password='x'),
        organization=organization, email='ada@example.com', username='ada',
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        Membership.objects.create(
            user=User.objects.create_user(username=uuid.uuid4().hex, password='x'),
            organization=organization, email='Ada@Example.com', username='grace',
        )


@pytest.mark.django_db
def test_a_case_only_duplicate_username_is_refused_by_the_database_directly():
    organization = make_organization('acme')
    Membership.objects.create(
        user=User.objects.create_user(username=uuid.uuid4().hex, password='x'),
        organization=organization, email='ada@example.com', username='ada',
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        Membership.objects.create(
            user=User.objects.create_user(username=uuid.uuid4().hex, password='x'),
            organization=organization, email='other@example.com', username='ADA',
        )


# Requirement: Give every organization a unique domain


@pytest.mark.django_db
def test_a_domain_already_taken_by_another_organization_is_refused():
    run('create_organization', 'Acme', 'acme', 'shared.example.com')

    with pytest.raises(CommandError):
        run('create_organization', 'Globex', 'globex', 'shared.example.com')

    assert not Organization.objects.filter(slug='globex').exists()


@pytest.mark.django_db
def test_the_database_itself_refuses_two_organizations_on_one_site():
    first = make_organization('acme')

    with pytest.raises(IntegrityError), transaction.atomic():
        Organization.objects.create(name='Twin', slug='twin', site=first.site)


@pytest.mark.django_db
@pytest.mark.parametrize(
    'domain',
    [
        'https://acme.example.com',
        'acme.example.com/app',
        'http://acme.example.com/app',
        ' ',
        'acme.example.com?x=1',
        'acme.example.com#fragment',
        'user@acme.example.com',
        'acme.example.com:not-a-port',
    ],
    ids=[
        'scheme', 'path', 'scheme-and-path', 'blank',
        'query-string', 'fragment', 'userinfo', 'invalid-port',
    ],
)
def test_a_domain_that_is_not_a_bare_host_is_refused(domain):
    with pytest.raises(CommandError):
        run('create_organization', 'Acme', 'acme', domain)

    assert not Organization.objects.filter(slug='acme').exists()
    assert not Site.objects.filter(name='Acme').exists()


@pytest.mark.django_db
def test_an_organization_cannot_be_created_without_a_domain():
    with pytest.raises(CommandError):
        run('create_organization', 'Acme', 'acme')

    assert not Organization.objects.filter(slug='acme').exists()


@pytest.mark.django_db
def test_an_organization_row_cannot_exist_without_a_site():
    with pytest.raises(IntegrityError), transaction.atomic():
        Organization.objects.create(name='Siteless', slug='siteless')


@pytest.mark.django_db
def test_the_domain_is_stored_lowercase_and_a_port_is_allowed():
    run('create_organization', 'Acme', 'acme', 'ACME.Example.com:8443')

    assert Organization.objects.get(slug='acme').site.domain == 'acme.example.com:8443'


@pytest.mark.django_db
def test_the_upgrade_gives_the_default_organization_the_reset_link_host(before_tenancy):
    from urllib.parse import urlsplit

    from django.conf import settings

    migrate_to_latest()

    default = Organization.objects.get(slug='default')
    assert default.site.domain == urlsplit(settings.RESET_LINK_BASE_URL).netloc.lower()


@pytest.fixture
def before_sites(transactional_db):
    """The database one migration before organizations got a Site, restored afterwards."""
    apps = migrate_to(('api', '0007_drop_global_email_unique_index'))
    yield apps
    migrate_to_latest()


@pytest.mark.django_db(transaction=True)
def test_reapplying_after_a_rollback_gives_unlinked_organizations_a_placeholder_domain(
    before_sites,
):
    """A rollback drops every organization's Site link; re-applying must still complete."""
    old_org = before_sites.get_model('api', 'Organization')
    old_org.objects.create(name='Globex', slug='globex')

    migrate_to_latest()

    assert Organization.objects.get(slug='globex').site.domain == 'globex.invalid'
