"""Give each existing deck the default quest prerequisite a new deck starts with (#276).

A new deck's default is its ByteDeck Proficiency badge, which tenant initialization creates with
a fixed import_id. A deck made before that import_id was fixed can still have the badge under its
original name, so the name is the fallback. A deck with no such badge keeps none, and so does one
that has unpublished it: an unpublished badge isn't awarded automatically, so its new students
could never earn it, and every new quest would stay closed to them.
"""
from django.db import migrations

# the import_id tenant initialization gives the ByteDeck Proficiency badge
PROFICIENCY_IMPORT_ID = 'fa3b0518-cf9c-443c-8fe4-f4a887b495a7'
PROFICIENCY_NAME = 'ByteDeck Proficiency'


def set_default_quest_prerequisite(apps, schema_editor):
    """Set this deck's default quest prerequisite to its published ByteDeck Proficiency badge.

    Runs once for each deck's schema. A deck that already has a default keeps it.

    Args:
        apps: the app registry as of this migration.
        schema_editor: the schema editor running it (unused).
    """
    Badge = apps.get_model('badges', 'Badge')
    SiteConfig = apps.get_model('siteconfig', 'SiteConfig')

    published = Badge.objects.filter(published=True)
    badge = published.filter(import_id=PROFICIENCY_IMPORT_ID).first() or published.filter(name=PROFICIENCY_NAME).first()
    if badge:
        SiteConfig.objects.filter(default_quest_prerequisite__isnull=True).update(default_quest_prerequisite=badge)


class Migration(migrations.Migration):

    dependencies = [
        ('badges', '0018_normalize_badge_fa_icon_names'),
        ('siteconfig', '0035_siteconfig_default_quest_prerequisite'),
    ]

    operations = [
        migrations.RunPython(set_default_quest_prerequisite, migrations.RunPython.noop),
    ]
