from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from api.models import Organization


class Command(BaseCommand):
    help = 'Create an organization and print its join code. The code is shown only once.'

    def add_arguments(self, parser):
        parser.add_argument('name')
        parser.add_argument('slug', help='Lowercase letters, digits and hyphens.')

    def handle(self, *args, name, slug, **options):
        organization = Organization(name=name, slug=slug)
        try:
            organization.full_clean()
        except ValidationError as invalid:
            raise CommandError('; '.join(invalid.messages)) from invalid
        organization.save()
        self.stdout.write(f'Created organization {slug!r}. Join code (shown once):')
        self.stdout.write(organization.issue_join_code())
