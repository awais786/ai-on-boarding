"""Tests for the signup, signin and password-reset deltas of add-multi-tenant-foundation,
written from the specs.

Signup (specs/user-signup):
- Reject a missing organization / join code -> each names its own field.
- Admit a signup only with the organization's join code -> right code works; a wrong code,
  another organization's code and a rotated-away code are all refused, creating nothing.
- Refuse an unknown, inactive or wrongly-coded organization identically -> four causes, one
  response.
- Never return the join code -> absent from success and failure bodies.
- Duplicates are judged within the organization -> the same email or username elsewhere is fine.

Signin (specs/user-signin):
- Reject a missing organization -> names the field.
- Authenticate within the named organization -> the same email in two organizations signs in to
  each with its own password.
- Reject all failure modes identically -> unknown, wrong, inactive organization/account,
  wrong-organization and lockout all match a wrong password.
- Lock out per organization -> failures in one never lock out the other.
- Issue a token bound to the account's organization -> the token acts only there.

Password reset (specs/user-password-reset):
- Reject a missing organization -> names the field.
- Look the address up only within the named organization -> the other organization's account is
  neither mailed nor has its code superseded; an inactive account receives nothing.
- Answer every request identically -> other-organization, unknown and inactive-organization
  requests all match an unregistered address.
- Limit per organization and address -> one organization's flood does not throttle the other.
"""

import pytest
from django.core.cache import cache
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from api.factories import create_member, make_organization
from api.models import Membership, PasswordResetCode


@pytest.fixture(autouse=True)
def fresh_throttle_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def acme_code(db):
    return make_organization('acme').issue_join_code()


def signup(client, organization='acme', join_code='', email='ada@example.com', username='ada'):
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


def signin(client, identifier='ada@example.com', password='lovelace1', organization='acme'):
    return client.post(
        '/api/signin/',
        {'organization': organization, 'email_or_username': identifier, 'password': password},
        format='json',
    )


def request_reset(client, email='ada@example.com', organization='acme'):
    return client.post(
        '/api/password-reset/', {'organization': organization, 'email': email}, format='json'
    )


def code_from(mail):
    link = next(w for w in mail.body.split() if w.startswith('http'))
    return link.rstrip('/').rsplit('/', 1)[-1]


# --- Signup ------------------------------------------------------------------------


@pytest.mark.django_db
def test_signup_without_an_organization_names_the_organization_field(client, acme_code):
    response = client.post(
        '/api/signup/',
        {'join_code': acme_code, 'email': 'a@b.co', 'username': 'ada', 'password': 'lovelace1',
         'country': 'France'},
        format='json',
    )

    assert response.status_code == 400
    assert 'organization' in response.data


@pytest.mark.django_db
def test_signup_without_a_join_code_names_the_join_code_field(client, acme_code):
    response = client.post(
        '/api/signup/',
        {'organization': 'acme', 'email': 'a@b.co', 'username': 'ada', 'password': 'lovelace1',
         'country': 'France'},
        format='json',
    )

    assert response.status_code == 400
    assert 'join_code' in response.data


@pytest.mark.django_db
def test_signup_with_the_correct_join_code_creates_the_account_in_that_organization(
    client, acme_code
):
    response = signup(client, join_code=acme_code)

    assert response.status_code == 200
    assert Membership.objects.get(email='ada@example.com').organization.slug == 'acme'


@pytest.mark.django_db
def test_signup_with_a_wrong_join_code_creates_nothing(client, acme_code):
    response = signup(client, join_code='not-the-code')

    assert response.status_code == 400
    assert not Membership.objects.exists()


@pytest.mark.django_db
def test_signup_with_another_organizations_join_code_creates_nothing_in_either(client, acme_code):
    globex_code = make_organization('globex').issue_join_code()

    response = signup(client, organization='acme', join_code=globex_code)

    assert response.status_code == 400
    assert not Membership.objects.exists()


@pytest.mark.django_db
def test_a_caller_cannot_place_themselves_in_an_organization_whose_code_they_lack(
    client, acme_code
):
    make_organization('globex').issue_join_code()

    response = signup(client, organization='globex', join_code=acme_code)

    assert response.status_code == 400
    assert not Membership.objects.exists()


@pytest.mark.django_db
def test_signup_with_a_rotated_away_join_code_is_refused(client, acme_code):
    make_organization('acme').issue_join_code()

    assert signup(client, join_code=acme_code).status_code == 400


@pytest.mark.django_db
def test_the_four_organization_failures_are_indistinguishable(client, acme_code):
    make_organization('closed')  # no join code issued
    inactive = make_organization('dormant', is_active=False)
    inactive_code = inactive.issue_join_code()

    unknown = signup(client, organization='nowhere', join_code=acme_code)
    is_inactive = signup(client, organization='dormant', join_code=inactive_code)
    no_code_issued = signup(client, organization='closed', join_code=acme_code)
    wrong_code = signup(client, organization='acme', join_code='wrong')

    responses = [unknown, is_inactive, no_code_issued, wrong_code]
    assert {r.status_code for r in responses} == {400}
    assert all(r.data == unknown.data for r in responses)
    assert 'join_code' in unknown.data


@pytest.mark.django_db
def test_a_duplicate_does_not_confirm_that_an_organization_exists(client, acme_code):
    """The duplicate check runs only after the organization is settled."""
    signup(client, join_code=acme_code)

    real_org_wrong_code = signup(client, join_code='wrong', username='other')
    fake_org = signup(client, organization='nowhere', join_code='wrong', username='other')

    assert real_org_wrong_code.data == fake_org.data


@pytest.mark.django_db
def test_the_join_code_is_never_in_a_signup_response(client, acme_code):
    ok = signup(client, join_code=acme_code)
    refused = signup(client, join_code=acme_code, username='ada2')  # duplicate email
    wrong = signup(client, join_code='wrong-code-value')

    for response in (ok, refused, wrong):
        assert 'join_code' not in ok.data
        assert acme_code not in response.content.decode()
    assert 'wrong-code-value' not in wrong.content.decode()


@pytest.mark.django_db
def test_the_same_email_and_username_can_sign_up_into_two_organizations(client, acme_code):
    globex_code = make_organization('globex').issue_join_code()

    first = signup(client, organization='acme', join_code=acme_code)
    second = signup(client, organization='globex', join_code=globex_code)

    assert first.status_code == second.status_code == 200
    assert Membership.objects.filter(email='ada@example.com').count() == 2


@pytest.mark.django_db
def test_a_duplicate_within_the_organization_is_still_refused(client, acme_code):
    signup(client, join_code=acme_code)

    by_email = signup(client, join_code=acme_code, username='ada2')
    by_username = signup(client, join_code=acme_code, email='other@example.com')

    assert 'email' in by_email.data
    assert 'username' in by_username.data
    assert Membership.objects.count() == 1


# --- Signin ------------------------------------------------------------------------


@pytest.mark.django_db
def test_signin_without_an_organization_names_the_organization_field(client):
    response = client.post(
        '/api/signin/',
        {'email_or_username': 'ada@example.com', 'password': 'lovelace1'},
        format='json',
    )

    assert response.status_code == 401
    assert 'organization' in response.data


@pytest.mark.django_db
def test_the_same_email_in_two_organizations_signs_in_to_each_with_its_own_password(client):
    acme = create_member('ada', 'ada@example.com', 'acme-pass1', organization='acme')
    globex = create_member('ada', 'ada@example.com', 'globex-pass1', organization='globex')

    in_acme = signin(client, password='acme-pass1', organization='acme')
    in_globex = signin(client, password='globex-pass1', organization='globex')

    assert in_acme.data['token'] == Token.objects.get(user=acme).key
    assert in_globex.data['token'] == Token.objects.get(user=globex).key
    assert signin(client, password='acme-pass1', organization='globex').status_code == 401


@pytest.mark.django_db
def test_a_user_of_one_organization_cannot_sign_in_to_another(client):
    create_member('ada', 'ada@example.com', organization='acme')
    make_organization('globex')

    response = signin(client, organization='globex')

    assert response.status_code == 401
    assert 'token' not in response.data


@pytest.mark.django_db
def test_every_failure_mode_matches_a_wrong_password(client):
    create_member('ada', 'ada@example.com', organization='acme')
    create_member('gone', 'gone@example.com', organization='acme', is_active=False)
    dormant = make_organization('dormant', is_active=False)
    create_member('eve', 'eve@example.com', organization=dormant)
    make_organization('globex')
    baseline = signin(client, password='wrongpassword')

    failures = [
        signin(client, organization='nowhere'),  # unknown organization
        signin(client, organization='globex'),  # right credentials, wrong organization
        signin(client, 'gone@example.com'),  # inactive account
        signin(client, 'eve@example.com', organization='dormant'),  # inactive organization
        signin(client, 'nobody@example.com'),  # unregistered
    ]

    assert baseline.status_code == 401
    for failure in failures:
        assert failure.status_code == 401
        assert failure.data == baseline.data


@pytest.mark.django_db
def test_lockout_in_one_organization_does_not_lock_out_the_same_email_in_another(client):
    create_member('ada', 'ada@example.com', organization='acme')
    create_member('ada', 'ada@example.com', organization='globex')

    for _ in range(3):
        signin(client, password='wrongpassword', organization='acme')

    assert signin(client, organization='acme').status_code == 401
    assert signin(client, organization='globex').status_code == 200


@pytest.mark.django_db
def test_lockout_of_a_name_that_matches_no_account_is_kept_per_organization(client):
    """Failures against an unknown identifier count per organization, not globally."""
    from api.models import SigninAttempt

    for _ in range(3):
        signin(client, 'ghost@example.com', organization='acme')
    signin(client, 'ghost@example.com', organization='globex')

    assert SigninAttempt.objects.get(email_or_username='acme|ghost@example.com').failed_count == 3
    assert SigninAttempt.objects.get(email_or_username='globex|ghost@example.com').failed_count == 1


@pytest.mark.django_db
def test_a_token_from_signin_acts_only_in_its_own_organization(client):
    create_member('boss', 'boss@acme.com', organization='acme', is_staff=True)
    create_member('alice', 'alice@acme.com', organization='acme')
    create_member('bob', 'bob@globex.com', organization='globex')
    token = signin(client, 'boss', organization='acme').data['token']

    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f'Token {token}')
    response = authed.get('/api/users/')

    assert sorted(row['username'] for row in response.data) == ['alice', 'boss']


# --- Password reset ----------------------------------------------------------------


@pytest.mark.django_db
def test_reset_without_an_organization_names_the_organization_field(client):
    response = client.post('/api/password-reset/', {'email': 'ada@example.com'}, format='json')

    assert response.status_code == 400
    assert 'organization' in response.data


@pytest.mark.django_db
def test_a_shared_address_is_reset_only_in_the_named_organization(client, mailoutbox):
    acme = create_member('ada', 'ada@example.com', organization='acme')
    globex = create_member('ada', 'ada@example.com', organization='globex')
    globex_code = PasswordResetCode.issue_for(globex)

    request_reset(client, organization='acme')

    assert len(mailoutbox) == 1
    assert PasswordResetCode.resolve(code_from(mailoutbox[0])).user == acme
    # The other organization's earlier code was not superseded.
    assert PasswordResetCode.resolve(globex_code) is not None


@pytest.mark.django_db
def test_an_address_registered_only_elsewhere_gets_the_unregistered_response_and_no_mail(
    client, mailoutbox
):
    create_member('ada', 'ada@example.com', organization='acme')
    make_organization('globex')

    elsewhere = request_reset(client, organization='globex')
    unregistered = request_reset(client, 'nobody@example.com', organization='acme')

    assert elsewhere.status_code == unregistered.status_code == 200
    assert elsewhere.data == unregistered.data
    assert mailoutbox == []


@pytest.mark.django_db
def test_an_unknown_or_inactive_organization_gets_the_unregistered_response(client, mailoutbox):
    dormant = make_organization('dormant', is_active=False)
    create_member('ada', 'ada@example.com', organization=dormant)
    baseline = request_reset(client, 'nobody@example.com', organization='acme')

    unknown = request_reset(client, organization='nowhere')
    inactive = request_reset(client, organization='dormant')

    assert unknown.status_code == inactive.status_code == baseline.status_code == 200
    assert unknown.data == inactive.data == baseline.data
    assert mailoutbox == []


@pytest.mark.django_db
def test_an_inactive_account_receives_no_reset_code(client, mailoutbox):
    create_member('ada', 'ada@example.com', organization='acme', is_active=False)

    request_reset(client)

    assert mailoutbox == []
    assert not PasswordResetCode.objects.exists()


@pytest.mark.django_db
def test_one_organizations_flood_does_not_throttle_the_same_address_in_another(
    client, mailoutbox
):
    create_member('ada', 'ada@example.com', organization='acme')
    create_member('ada', 'ada@example.com', organization='globex')
    for _ in range(6):
        request_reset(client, organization='acme')
    assert request_reset(client, organization='acme').status_code == 429
    before = len(mailoutbox)

    response = request_reset(client, organization='globex')

    assert response.status_code == 200
    assert len(mailoutbox) == before + 1


# Deliver the reset link as an absolute address: the host is the organization's domain


def link_host(mail):
    from urllib.parse import urlsplit

    return urlsplit(next(w for w in mail.body.split() if w.startswith('http'))).netloc


@pytest.mark.django_db
def test_the_reset_link_points_at_the_accounts_organization_domain(client, mailoutbox):
    organization = make_organization('acme')
    organization.site.domain = 'acme.example.com'
    organization.site.save()
    create_member('ada', 'ada@example.com', organization=organization)

    request_reset(client)

    assert link_host(mailoutbox[0]) == 'acme.example.com'


@pytest.mark.django_db
def test_two_organizations_get_links_with_their_own_hosts(client, mailoutbox):
    for slug, domain in (('acme', 'acme.example.com'), ('globex', 'globex.example.org:8443')):
        organization = make_organization(slug)
        organization.site.domain = domain
        organization.site.save()
        create_member('ada', 'ada@example.com', organization=organization)

    request_reset(client, organization='acme')
    request_reset(client, organization='globex')

    assert [link_host(m) for m in mailoutbox] == ['acme.example.com', 'globex.example.org:8443']


@pytest.mark.django_db
def test_a_forged_host_header_does_not_change_the_link_host(client, mailoutbox, settings):
    settings.ALLOWED_HOSTS = ['*']
    organization = make_organization('acme')
    organization.site.domain = 'acme.example.com'
    organization.site.save()
    create_member('ada', 'ada@example.com', organization=organization)

    client.post(
        '/api/password-reset/',
        {'organization': 'acme', 'email': 'ada@example.com'},
        format='json',
        HTTP_HOST='evil.example.net',
    )

    assert link_host(mailoutbox[0]) == 'acme.example.com'
    assert 'evil.example.net' not in mailoutbox[0].body


@pytest.mark.django_db
def test_the_link_keeps_the_scheme_and_path_prefix_from_the_configured_base(
    client, mailoutbox, settings
):
    settings.RESET_LINK_BASE_URL = 'https://ignored.example.com/app/'
    create_member('ada', 'ada@example.com', organization='acme')

    request_reset(client)

    link = next(w for w in mailoutbox[0].body.split() if w.startswith('http'))
    assert link.startswith('https://acme.example.test/app/reset-password/')


# Public endpoints take no credential: a stale token header must not change their answer


STALE = {'HTTP_AUTHORIZATION': 'Token deadbeef-a-token-that-was-deleted'}


@pytest.mark.django_db
@pytest.mark.parametrize(
    'method, path, body',
    [
        ('get', '/api/health/', None),
        ('post', '/api/signin/', {'organization': 'acme', 'email_or_username': 'ada',
                                  'password': 'lovelace1'}),
        ('post', '/api/password-reset/', {'organization': 'acme', 'email': 'ada@example.com'}),
        ('post', '/api/password-reset/confirm/', {'code': 'nope', 'password': 'lovelace1'}),
        ('post', '/api/auth/google/', {'access_token': 'x'}),
    ],
    ids=['health', 'signin', 'reset-request', 'reset-confirm', 'google'],
)
def test_a_stale_token_header_does_not_change_a_public_endpoints_answer(method, path, body):
    create_member('ada', 'ada@example.com', 'lovelace1', organization='acme')

    def call(**extra):
        client = APIClient()
        return getattr(client, method)(path, body, format='json', **extra)

    plain, stale = call(), call(**STALE)

    assert stale.status_code == plain.status_code
    assert stale.data == plain.data


@pytest.mark.django_db
def test_signup_still_works_with_a_stale_token_header(client, acme_code):
    client.credentials(**STALE)

    assert signup(client, join_code=acme_code).status_code == 200


@pytest.mark.django_db
def test_signin_with_correct_credentials_succeeds_despite_a_stale_token_header(client):
    """A client whose token was deleted (password change, deactivation) must be able to sign in."""
    create_member('ada', 'ada@example.com', organization='acme')
    client.credentials(**STALE)

    response = signin(client)

    assert response.status_code == 200
    assert response.data['token']


# The join-code check costs the same whether or not the organization is real


@pytest.mark.django_db
def test_an_unknown_organization_still_pays_for_a_hash(client, acme_code):
    from unittest.mock import patch

    with patch('api.serializers.make_password') as hashed:
        signup(client, organization='nowhere', join_code='whatever')

    hashed.assert_called_once()


@pytest.mark.django_db
def test_a_closed_organization_still_pays_for_a_hash(client):
    from unittest.mock import patch

    make_organization('closed')  # no join code issued

    with patch('api.models.make_password') as hashed:
        signup(client, organization='closed', join_code='whatever')

    hashed.assert_called_once()


# Signin failures cost the same as a real check: response time must not reveal who exists


def signin_hashes(client, **kwargs):
    """How many times signin paid for a stand-in hash (a real member's check is Django's own)."""
    from unittest.mock import patch

    with patch('api.views.make_password') as hashed:
        response = signin(client, **kwargs)
    return response, hashed.call_count


@pytest.mark.django_db
def test_signin_for_an_unknown_organization_pays_for_a_hash(client):
    response, hashes = signin_hashes(client, organization='nowhere')

    assert response.status_code == 401
    assert hashes == 1


@pytest.mark.django_db
def test_signin_for_an_unknown_user_pays_for_a_hash(client):
    create_member('ada', 'ada@example.com', organization='acme')

    response, hashes = signin_hashes(client, identifier='ghost@example.com')

    assert response.status_code == 401
    assert hashes == 1


@pytest.mark.django_db
def test_signin_for_an_inactive_organization_pays_for_a_hash(client):
    dormant = make_organization('dormant', is_active=False)
    create_member('eve', 'eve@example.com', organization=dormant)

    response, hashes = signin_hashes(client, identifier='eve@example.com', organization='dormant')

    assert response.status_code == 401
    assert hashes == 1


@pytest.mark.django_db
def test_signin_for_a_locked_out_account_pays_for_a_hash(client):
    create_member('ada', 'ada@example.com', organization='acme')
    for _ in range(3):
        signin(client, password='wrongpassword')

    response, hashes = signin_hashes(client)

    assert response.status_code == 401
    assert hashes == 1


@pytest.mark.django_db
def test_a_real_members_check_is_not_hashed_twice(client):
    create_member('ada', 'ada@example.com', organization='acme')

    wrong, wrong_hashes = signin_hashes(client, password='wrongpassword')
    right, right_hashes = signin_hashes(client)

    assert (wrong.status_code, right.status_code) == (401, 200)
    assert wrong_hashes == right_hashes == 0


# Closed by default: an endpoint that declares no permissions refuses anonymous callers


def test_a_view_that_declares_no_permissions_refuses_an_anonymous_caller():
    from rest_framework.response import Response
    from rest_framework.test import APIRequestFactory
    from rest_framework.views import APIView

    class Forgetful(APIView):
        def get(self, request):
            return Response({'secret': 'data'})

    response = Forgetful.as_view()(APIRequestFactory().get('/anything/'))

    assert response.status_code in (401, 403)
    assert 'secret' not in getattr(response, 'data', {})


@pytest.mark.django_db
@pytest.mark.parametrize('path', ['/api/schema/', '/api/docs/'])
def test_the_public_api_docs_ignore_a_stale_token_header(path):
    client = APIClient()

    plain = client.get(path)
    stale = client.get(path, **STALE)

    assert plain.status_code == stale.status_code == 200
