"""Tests for the data migration that gives existing decks a default quest prerequisite (#276)."""
import uuid
from importlib import import_module

from django.apps import apps as django_apps
from django.core.cache import cache

from model_bakery import baker

from badges.models import Badge
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from siteconfig.models import SiteConfig

# the function lives in the migration (kept self-contained there), so import it from that module
default_prerequisite_migration = import_module("siteconfig.migrations.0036_set_default_quest_prerequisite")


class SetDefaultQuestPrerequisiteMigrationTest(ByteDeckTenantTestCase):
    """The data migration that sets an existing deck's default quest prerequisite."""

    def setUp(self):
        """Start each test as an existing deck does: with its ByteDeck Proficiency badge and no default."""
        SiteConfig.objects.update(default_quest_prerequisite=None)
        self.proficiency = Badge.objects.get(import_id=default_prerequisite_migration.PROFICIENCY_IMPORT_ID)

    def tearDown(self):
        """Clear the cache, since a cached SiteConfig outlives the test's rollback."""
        cache.clear()

    def _migrate(self):
        """Run the migration's function, and return the deck's default quest prerequisite as stored.

        Returns:
            Badge or None: the default quest prerequisite in the database afterwards.
        """
        default_prerequisite_migration.set_default_quest_prerequisite(django_apps, None)
        return SiteConfig.objects.get().default_quest_prerequisite

    def test_set_default_quest_prerequisite__finds_the_badge_by_its_import_id(self):
        """An existing deck's default becomes its ByteDeck Proficiency badge, found by the import_id a new
        deck's gets, so a deck that renamed the badge still has it found."""
        self.proficiency.name = "Orientation Complete"
        self.proficiency.save()

        self.assertEqual(self._migrate(), self.proficiency)

    def test_set_default_quest_prerequisite__finds_the_badge_by_name(self):
        """A deck made before the badge's import_id was fixed has it under another import_id, so it's
        found by its name."""
        self.proficiency.import_id = uuid.uuid4()
        self.proficiency.save()

        self.assertEqual(self._migrate(), self.proficiency)

    def test_set_default_quest_prerequisite__none_without_the_badge(self):
        """A deck with no badge of that import_id or name keeps no default."""
        self.proficiency.name = "Orientation Complete"
        self.proficiency.import_id = uuid.uuid4()
        self.proficiency.save()

        self.assertIsNone(self._migrate())

    def test_set_default_quest_prerequisite__none_when_the_badge_is_unpublished(self):
        """An unpublished badge isn't awarded automatically, so it isn't made every new quest's
        prerequisite."""
        self.proficiency.published = False
        self.proficiency.save()

        self.assertIsNone(self._migrate())

    def test_set_default_quest_prerequisite__keeps_a_default_already_set(self):
        """A deck that already has a default keeps it."""
        other_badge = baker.make(Badge)
        SiteConfig.objects.update(default_quest_prerequisite=other_badge)

        self.assertEqual(self._migrate(), other_badge)
