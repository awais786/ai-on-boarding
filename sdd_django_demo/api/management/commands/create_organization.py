from django.contrib.sites.models import Site
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.models import Organization


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
        if '://' in domain or '/' in domain or not domain:
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
