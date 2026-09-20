"""Test helpers: accounts that live in an organization, the way signup makes them."""

import uuid

from django.contrib.auth.models import User

from api.models import Membership, Organization

DEFAULT_SLUG = 'acme'


def make_organization(slug=DEFAULT_SLUG, is_active=True):
    """Get or create an organization; call `.issue_join_code()` on it to open signup."""
    organization, _ = Organization.objects.get_or_create(
        slug=slug, defaults={'name': slug.title(), 'is_active': is_active}
    )
    return organization


def create_member(
    username='ada',
    email=None,
    password='lovelace1',
    organization=DEFAULT_SLUG,
    is_staff=False,
    is_active=True,
):
    """A user with a Membership in `organization` (a slug or an Organization)."""
    if isinstance(organization, str):
        organization = make_organization(organization)
    email = (email or '').lower()
    user = User.objects.create_user(
        username=uuid.uuid4().hex,
        email=email,
        password=password,
        is_staff=is_staff,
        is_active=is_active,
    )
    Membership.objects.create(
        user=user, organization=organization, email=email, username=username.lower()
    )
    return user
