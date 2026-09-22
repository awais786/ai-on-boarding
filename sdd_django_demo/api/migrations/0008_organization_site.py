from urllib.parse import urlsplit

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def give_organizations_a_site(apps, schema_editor):
    Organization = apps.get_model('api', 'Organization')
    Site = apps.get_model('sites', 'Site')
    default = Organization.objects.filter(slug='default').first()
    if default is not None:
        # The host reset links already pointed at, so the default organization's links do not move.
        domain = urlsplit(settings.RESET_LINK_BASE_URL).netloc.lower()
        default.site, _ = Site.objects.get_or_create(domain=domain, defaults={'name': default.name})
        default.save(update_fields=['site'])
    # Only reachable when re-applying after a rollback, which drops every organization's link.
    # A reserved `.invalid` host is safe (mail to it goes nowhere) and obviously wrong, so an
    # operator fixes the domain in the admin rather than the migration failing half-way.
    for organization in Organization.objects.filter(site__isnull=True):
        organization.site = Site.objects.create(
            domain=f'{organization.slug}.invalid', name=organization.name
        )
        organization.save(update_fields=['site'])


def remove_default_organizations_site(apps, schema_editor):
    """Detach the default organization's Site, but never delete it.

    `get_or_create` above may have created a fresh row, or reused a pre-existing one (the sites
    app's own seeded example.com row, or one an operator made by hand) - and there is nothing
    durable to record "we created this" between the forward and reverse halves of a data
    migration, so the two cases cannot be told apart here. Deleting in the "reused" case would
    destroy a row this migration does not own, which is worse than leaving one small, harmless,
    unreferenced Site row behind: nothing in this project sets SITE_ID or reads Site.objects
    other than through Organization, so an orphaned row changes nothing.
    """
    Organization = apps.get_model('api', 'Organization')
    default = Organization.objects.filter(slug='default').first()
    if default is None or default.site_id is None:
        return
    default.site = None
    default.save(update_fields=['site'])


class Migration(migrations.Migration):
    """Each organization gets a Site, used for its domain.

    Added nullable so the existing `default` organization can be given one, then made required.
    """

    dependencies = [
        ('api', '0007_drop_global_email_unique_index'),
        ('sites', '0002_alter_domain_unique'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='site',
            field=models.OneToOneField(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='organization',
                to='sites.site',
            ),
        ),
        migrations.RunPython(give_organizations_a_site, remove_default_organizations_site),
        migrations.AlterField(
            model_name='organization',
            name='site',
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='organization',
                to='sites.site',
            ),
        ),
    ]
