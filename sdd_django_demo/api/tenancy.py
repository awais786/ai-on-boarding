"""The one place organization filtering is written.

Views never filter on an organization by hand: they obtain the organization from
`organization_of(request)` (never from client input) and build scoped querysets through
`for_organization` / `users_in`. See the change's design.md, decision D4.
"""

from django.contrib.auth.models import User
from django.db import models


class TenantQuerySet(models.QuerySet):
    """For any model with an `organization` foreign key."""

    def for_organization(self, organization):
        return self.filter(organization=organization)


def users_in(organization):
    return User.objects.filter(membership__organization=organization)


def organization_of(request):
    """The organization of the signed-in caller, from their credential alone."""
    return request.user.membership.organization
