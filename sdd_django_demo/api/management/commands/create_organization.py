from urllib.parse import urlsplit

from django.contrib.sites.models import Site
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.models import Organization


def is_bare_host(domain):
    """Whether `domain` is a bare host[:port] - no scheme, path, query, fragment, or userinfo.

    `Site.full_clean()` does not validate `domain` as a hostname, so `acme.example.com?x=1` or
    `user@host` would otherwise pass through as-is and produce a malformed reset link, or a link
    whose effective host differs from the stored string.
    """
    if not domain or '://' in domain:
        return False
    parsed = urlsplit(f'//{domain}')
    if parsed.path or parsed.query or parsed.fragment:
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    if parsed.netloc != domain:
        return False
    try:
        parsed.port  # a non-numeric port raises ValueError on access
    except ValueError:
        return False
    return parsed.hostname is not None


class Command(BaseCommand):
    help = 'Create an organization and print its join code. The code is shown only once.'

    def add_arguments(self, parser):
        parser.add_argument('name')
        parser.add_argument('slug', help='Lowercase letters, digits and hyphens.')
        parser.add_argument(
            'domain', help='Bare host, optionally with a port, e.g. acme.example.com. No scheme.'
        )

    def handle(self, *args, name, slug, domain, **options):
        domain = domain.strip().lower()
        if not is_bare_host(domain):
            raise CommandError('The domain must be a bare host, with no scheme or path.')
        site = Site(domain=domain, name=name)
        organization = Organization(name=name, slug=slug, site=site)
        try:
            site.full_clean()
            organization.full_clean(exclude=['site'])
        except ValidationError as invalid:
            raise CommandError('; '.join(invalid.messages)) from invalid
        with transaction.atomic():
            site.save()
            organization.site = site
            organization.save()
        self.stdout.write(f'Created organization {slug!r} at {domain}. Join code (shown once):')
        self.stdout.write(organization.issue_join_code())
