from django.core.management.base import BaseCommand, CommandError

from api.models import Organization


class Command(BaseCommand):
    help = "Replace an organization's join code and print the new one. The old code stops working."

    def add_arguments(self, parser):
        parser.add_argument('slug')

    def handle(self, *args, slug, **options):
        organization = Organization.objects.filter(slug=slug).first()
        if organization is None:
            raise CommandError(f'No organization with slug {slug!r}.')
        self.stdout.write(f'New join code for {slug!r} (shown once):')
        self.stdout.write(organization.issue_join_code())
