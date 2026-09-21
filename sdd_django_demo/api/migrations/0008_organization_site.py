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
    Organization = apps.get_model('api', 'Organization')
    default = Organization.objects.filter(slug='default').first()
    if default is None or default.site_id is None:
        return
    site = default.site
    default.site = None
    default.save(update_fields=['site'])
    site.delete()


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
