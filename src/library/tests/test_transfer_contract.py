"""Characterization tests for what a Shared Library transfer actually moves.

These tests pin the *observable* contract of pushing content to the Library and pulling
it back: which fields arrive with the value the author wrote, which arrive changed, and
which do not arrive at all. They deliberately assert the behaviour as it is today,
including the losses, so that a change to the copy mechanism cannot alter what teachers
receive without a test saying so.

Several assertions below therefore encode known bugs. Each one names the issue tracking
it and says what the assertion should become once that issue is fixed. That is the point
of a characterization test: it fails when behaviour changes, whether the change is a fix
or a regression, and the failure is where the decision gets recorded.

Why this exists: before these tests, the Library suite asserted that transferred content
*existed* and had the right published flag, and compared exactly one field value. A
copier that dropped every field except the name, every prerequisite and every tag passed
65 of the 67 tests in this package.
"""

from django.db import connection
from django_tenants.utils import schema_context
from taggit.models import Tag

from library.exporter import export_campaign_and_copy_quests, export_quest_to_library
from library.importer import import_campaign_to, import_quest_to
from library.tests.test_views import LibraryTenantTestCaseMixin
from library.utils import library_schema_context
from prerequisites.models import Prereq
from quest_manager.models import Category, CommonData, Quest

# The fields a Quest carries into the Library and back, as of today. This is not a wish
# list: it is what the transfer currently moves, verified by `test_quest_field_inventory__every_field_is_classified`.
# Adding a field to Quest or XPItem fails that test until the field is classified here,
# which is the point. Add it to TRANSFERRED if the value belongs to the content and should
# reach other decks, or to NOT_TRANSFERRED with a reason if it does not.
QUEST_FIELDS_TRANSFERRED = frozenset({
    'name', 'xp', 'xp_can_be_entered_by_students', 'short_description', 'archived', 'sort_order',
    'max_repeats', 'max_xp', 'repeat_per_semester', 'hours_between_repeats', 'date_available',
    'time_available', 'date_expired', 'time_expired', 'icon', 'verification_required', 'hideable',
    'available_outside_course', 'instructions', 'submission_details', 'instructor_notes',
    'quick_reply', 'blocking', 'map_transition', 'import_id',
})

QUEST_FIELDS_NOT_TRANSFERRED = {
    'id': 'Primary key. The destination assigns its own.',
    'editor': 'FK to a user on the source deck. A user pk means someone else in another schema.',
    'specific_teacher_to_notify': 'FK to a user on the source deck, same reason as editor.',
    'common_data': 'Dropped. CommonData has no import_id, so there is no cross-schema key for it (#2398).',
    'campaign': 'Not copied as an FK. Rebuilt on the far side from the campaign_* columns.',
    'published': 'Deliberately forced to draft so imported content is reviewed before students see it.',
    'datetime_created': 'auto_now_add. The destination row stamps its own creation time.',
    'datetime_last_edit': 'auto_now. Always the time of the import.',
}

CATEGORY_FIELDS_TRANSFERRED = frozenset({'title', 'icon', 'short_description', 'import_id'})

CATEGORY_FIELDS_NOT_TRANSFERRED = {
    'id': 'Primary key. The destination assigns its own.',
    'published': 'Deliberately forced to draft, same as quests.',
    'map_order': 'Dropped. The campaign travels as four flat columns and this is not one of them (#2396).',
}


class LibraryTransferContractTests(LibraryTenantTestCaseMixin):
    """Pin what a full push-and-pull round trip does to every field of a quest."""

    def _build_populated_quest(self):
        """Create a campaign and a quest with every writable field set to a non-default value.

        Returns:
            tuple[Quest, Category]: The populated quest and the campaign it belongs to.
        """
        campaign = Category(
            title="Contract Campaign",
            short_description="campaign blurb",
            icon="icons/campaign.png",
            map_order=7,
            published=True,
        )
        campaign.save()

        common = CommonData.objects.create(title="Shared Preamble", instructions="<p>common instructions</p>")

        quest = Quest(
            name="Contract Quest",
            xp=42,
            xp_can_be_entered_by_students=True,
            short_description="the short description",
            sort_order=13,
            max_repeats=-1,
            max_xp=99,
            repeat_per_semester=True,
            hours_between_repeats=5,
            icon="icons/quest.png",
            verification_required=False,
            hideable=False,
            available_outside_course=True,
            campaign=campaign,
            common_data=common,
            instructions="<p>do the thing</p>",
            submission_details="<p>submit the thing</p>",
            instructor_notes="<p>the answer is 7</p>",
            quick_reply="Check your units!",
            blocking=True,
            map_transition=True,
        )
        quest.save()
        # Publishing through the manager avoids the post_save map-regeneration signal,
        # which needs a broker that the test environment does not run.
        Quest.objects.filter(pk=quest.pk).update(published=True)
        return Quest.objects.get(pk=quest.pk), campaign

    def _push_and_pull(self, campaign):
        """Push a campaign to the Library, publish it there, then pull it into a virgin deck.

        The local copies are deleted between the two halves so the pull exercises the
        create path a deck that has never seen this content would take.

        Args:
            campaign (Category): The local campaign to push.

        Returns:
            list[UUID]: The import_ids of the quests that made the round trip.
        """
        local_schema = connection.schema_name
        export_campaign_and_copy_quests(source_schema=local_schema, campaign_import_id=campaign.import_id)

        with library_schema_context():
            library_campaign = Category.objects.get(import_id=campaign.import_id)
            library_campaign.published = True
            library_campaign.save()
            Quest.objects.filter(campaign=library_campaign).update(published=True)
            import_ids = list(Quest.objects.filter(campaign=library_campaign).values_list('import_id', flat=True))

        with schema_context(local_schema):
            Quest.objects.all_including_archived().filter(import_id__in=import_ids).delete()
            Category.objects.filter(import_id=campaign.import_id).delete()
            CommonData.objects.all().delete()

        import_campaign_to(
            destination_schema=local_schema,
            quest_import_ids=import_ids,
            campaign_import_id=campaign.import_id,
        )
        return import_ids

    def test_quest_field_inventory__every_field_is_classified(self):
        """Every concrete Quest field is classified as transferred or not.

        Fails when a field is added to Quest or XPItem, which is the only thing that
        makes the transfer's field contract a decision rather than an accident. Two
        fields were added to these models in July 2026: one silently started travelling
        and one silently did not, because nobody was asked.
        """
        concrete = {f.name for f in Quest._meta.concrete_fields}
        classified = QUEST_FIELDS_TRANSFERRED | set(QUEST_FIELDS_NOT_TRANSFERRED)

        self.assertEqual(
            concrete - classified,
            set(),
            "A field was added to Quest or XPItem without deciding whether it should travel to other decks. "
            "Add it to QUEST_FIELDS_TRANSFERRED or to QUEST_FIELDS_NOT_TRANSFERRED with a reason.",
        )
        self.assertEqual(
            classified - concrete,
            set(),
            "A field was removed from Quest but is still classified in this module.",
        )

    def test_category_field_inventory__every_field_is_classified(self):
        """Every concrete Category field is classified as transferred or not.

        The campaign is the weaker half of the contract: it is rebuilt on the far side
        from four hand-listed columns, so a new Category field does not travel unless
        someone adds a fifth. That is how map_order came to be dropped (#2396).
        """
        concrete = {f.name for f in Category._meta.concrete_fields}
        classified = CATEGORY_FIELDS_TRANSFERRED | set(CATEGORY_FIELDS_NOT_TRANSFERRED)

        self.assertEqual(
            concrete - classified,
            set(),
            "A field was added to Category without deciding whether it should travel to other decks. "
            "Add it to CATEGORY_FIELDS_TRANSFERRED or to CATEGORY_FIELDS_NOT_TRANSFERRED with a reason.",
        )
        self.assertEqual(
            classified - concrete,
            set(),
            "A field was removed from Category but is still classified in this module.",
        )

    def test_round_trip__preserves_every_transferred_quest_field(self):
        """Each field listed as transferred arrives with the value the author wrote."""
        quest, campaign = self._build_populated_quest()
        expected = {name: getattr(quest, name) for name in QUEST_FIELDS_TRANSFERRED}

        self._push_and_pull(campaign)

        imported = Quest.objects.all_including_archived().get(import_id=quest.import_id)
        for name in sorted(QUEST_FIELDS_TRANSFERRED):
            with self.subTest(field=name):
                self.assertEqual(
                    str(getattr(imported, name)),
                    str(expected[name]),
                    f"'{name}' did not survive a push to the Library and a pull back into a deck.",
                )

    def test_round_trip__forces_imported_content_to_draft(self):
        """A quest and its campaign arrive unpublished so staff review before students see them."""
        quest, campaign = self._build_populated_quest()
        self.assertTrue(quest.published)

        self._push_and_pull(campaign)

        imported = Quest.objects.all_including_archived().get(import_id=quest.import_id)
        imported_campaign = Category.objects.get(import_id=campaign.import_id)
        self.assertFalse(imported.published)
        self.assertFalse(imported_campaign.published)

    def test_round_trip__drops_common_data(self):
        """A quest's shared 'General Info' block does not travel (#2398).

        CommonData has no import_id, so there is no key to match it across schemas, and
        it is excluded from the transfer entirely. A quest whose instructions refer to a
        shared preamble arrives on the destination deck without that panel.

        When #2398 is fixed this should assert the CommonData arrives instead.
        """
        quest, campaign = self._build_populated_quest()
        self.assertIsNotNone(quest.common_data)

        self._push_and_pull(campaign)

        imported = Quest.objects.all_including_archived().get(import_id=quest.import_id)
        self.assertIsNone(imported.common_data)

    def test_round_trip__drops_campaign_map_order(self):
        """A campaign's quest-map placement resets to the default (#2396).

        When #2396 is fixed this should assert map_order arrives as 7, or the campaign
        should be documented as deliberately deck-relative.
        """
        _, campaign = self._build_populated_quest()
        self.assertEqual(campaign.map_order, 7)

        self._push_and_pull(campaign)

        imported_campaign = Category.objects.get(import_id=campaign.import_id)
        self.assertEqual(imported_campaign.map_order, 0)


class LibraryTransferPrereqContractTests(LibraryTenantTestCaseMixin):
    """Pin which prerequisites survive a transfer and which are silently discarded."""

    def _campaign_with_two_quests(self):
        """Create a published campaign holding a quest and a second quest to depend on.

        Returns:
            tuple[Category, Quest, Quest]: The campaign, the dependent quest, and the
            in-campaign quest it can depend on.
        """
        campaign = Category(title="Prereq Campaign", published=True)
        campaign.save()
        quest = Quest.objects.create(name="Dependent Quest", xp=10, campaign=campaign)
        inside = Quest.objects.create(name="Prereq Inside Campaign", xp=1, campaign=campaign)
        Quest.objects.filter(pk__in=[quest.pk, inside.pk]).update(published=True)
        return campaign, Quest.objects.get(pk=quest.pk), Quest.objects.get(pk=inside.pk)

    def test_push__keeps_a_prereq_whose_target_is_in_the_same_campaign(self):
        """A prerequisite pointing at another quest in the pushed campaign survives."""
        campaign, quest, inside = self._campaign_with_two_quests()
        Prereq.add_simple_prereq(quest, inside)

        export_campaign_and_copy_quests(source_schema=connection.schema_name, campaign_import_id=campaign.import_id)

        with library_schema_context():
            library_quest = Quest.objects.all_including_archived().get(import_id=quest.import_id)
            names = [p.get_prereq().name for p in library_quest.prereqs()]
        self.assertEqual(names, ["Prereq Inside Campaign"])

    def test_push__discards_a_prereq_whose_target_is_outside_the_campaign(self):
        """A prerequisite pointing outside the pushed campaign is destroyed on the push (#2399).

        The Library never receives the target, so the link cannot be rebuilt there, and a
        deck pulling this campaign cannot recover it either. The quest arrives with weaker
        gating than its author wrote and nothing reports the loss, even when the importing
        deck happens to have the prerequisite quest itself.

        When this is fixed the sharer should be told which prerequisites will not travel.
        """
        campaign, quest, _ = self._campaign_with_two_quests()
        outside = Quest.objects.create(name="Prereq Outside Campaign", xp=1)
        Prereq.add_simple_prereq(quest, outside)

        export_campaign_and_copy_quests(source_schema=connection.schema_name, campaign_import_id=campaign.import_id)

        with library_schema_context():
            library_quest = Quest.objects.all_including_archived().get(import_id=quest.import_id)
            self.assertEqual(list(library_quest.prereqs()), [])


class LibraryTransferTagContractTests(LibraryTenantTestCaseMixin):
    """Pin how tags cross a schema boundary."""

    def test_push__carries_tags_by_primary_key_not_by_name(self):
        """Tags are transported as raw primary keys, so a quest can arrive mistagged (#1792).

        Tag rows are per-schema, so the pk that means 'photography' on one deck means
        whatever happens to hold that pk in the destination. django-import-export builds a
        ManyToManyWidget(model=Tag, field='pk') for taggit's manager, and the destination
        re-resolves the incoming pks against its own tag table.

        When #1792 is fixed this should assert the tags arrive by name.
        """
        local_tags = {}
        for name in ("photography", "darkroom"):
            tag = Tag.objects.create(name=name, slug=name)
            local_tags[tag.pk] = tag.name

        with library_schema_context():
            for pk in local_tags:
                Tag(pk=pk, name=f"library-tag-{pk}", slug=f"library-tag-{pk}").save(force_insert=True)

        quest = Quest.objects.create(name="Tagged Quest", xp=10)
        quest.tags.set(list(local_tags.values()))

        export_quest_to_library(source_schema=connection.schema_name, quest_import_id=quest.import_id)

        with library_schema_context():
            library_quest = Quest.objects.all_including_archived().get(import_id=quest.import_id)
            arrived = sorted(tag.name for tag in library_quest.tags.all())

        self.assertEqual(arrived, sorted(f"library-tag-{pk}" for pk in local_tags))
        self.assertNotEqual(arrived, sorted(local_tags.values()))


class LibraryTransferCollisionContractTests(LibraryTenantTestCaseMixin):
    """Pin what a teacher gets when imported content collides with a name they already use."""

    def _publish_quests_in_library(self, campaign_import_id):
        """Publish a pushed campaign and its quests in the Library, as a Library admin would.

        Args:
            campaign_import_id (UUID): The import ID of the campaign to publish.

        Returns:
            list[UUID]: The import_ids of the campaign's quests in the Library.
        """
        with library_schema_context():
            library_campaign = Category.objects.get(import_id=campaign_import_id)
            library_campaign.published = True
            library_campaign.save()
            Quest.objects.filter(campaign=library_campaign).update(published=True)
            return list(Quest.objects.filter(campaign=library_campaign).values_list('import_id', flat=True))

    def _push_campaign(self, title, quest_names):
        """Create a campaign with the named quests and push it into the Library.

        Args:
            title (str): Title for the new campaign.
            quest_names (list[str]): Names of the quests to create in it.

        Returns:
            tuple[Category, list[UUID]]: The local campaign and its quests' import_ids in the Library.
        """
        campaign = Category(title=title, published=True)
        campaign.save()
        for name in quest_names:
            quest = Quest.objects.create(name=name, xp=5, campaign=campaign)
            Quest.objects.filter(pk=quest.pk).update(published=True)
        export_campaign_and_copy_quests(source_schema=connection.schema_name, campaign_import_id=campaign.import_id)
        return campaign, self._publish_quests_in_library(campaign.import_id)

    def _clear_locally(self, campaign, import_ids):
        """Delete the local originals so a later import behaves like a deck seeing them fresh.

        Args:
            campaign (Category): The local campaign to remove.
            import_ids (list[UUID]): The quests to remove.
        """
        Quest.objects.all_including_archived().filter(import_id__in=import_ids).delete()
        Category.objects.filter(import_id=campaign.import_id).delete()

    def test_import_quest__raises_when_the_name_is_already_taken_locally(self):
        """Importing a quest whose name a different local quest holds raises (#2364).

        Quest.name is unique per deck, and the view guards only on import_id, so this
        reaches the database. The exception is django-import-export's own ImportError,
        which is neither ValidationError nor IntegrityError, so the exporter's handler
        does not catch it and the teacher gets a 500 page carrying the raw constraint
        name. This test pins the exception type, because that type is exactly why the
        existing error handling misses it.

        When #2364 is fixed this should assert the teacher gets a message naming the clash.
        """
        from import_export.exceptions import ImportError as ImportExportError

        campaign, import_ids = self._push_campaign("Collision Campaign", ["Photoshop Basics"])
        self._clear_locally(campaign, import_ids)
        Quest.objects.create(name="Photoshop Basics", xp=999)

        with self.assertRaises(ImportExportError):
            import_quest_to(destination_schema=connection.schema_name, quest_import_id=import_ids[0])

        self.assertFalse(Quest.objects.all_including_archived().filter(import_id=import_ids[0]).exists())

    def test_import_campaign__one_colliding_name_discards_the_whole_import(self):
        """One taken quest name rolls back an entire campaign import, silently (#2397).

        The importable quests do not land, the campaign is not created, and the call
        returns normally with the failure recorded in a result object that no caller
        reads, so the view falls through to get_object_or_404 and the teacher gets a
        bare 404.

        When #2397 is fixed this should assert the teacher is told which quest collided.
        """
        campaign, import_ids = self._push_campaign(
            "Partial Campaign", ["Good Quest One", "Bad Quest Two", "Good Quest Three"],
        )
        self._clear_locally(campaign, import_ids)
        Quest.objects.create(name="Bad Quest Two", xp=999)

        result = import_campaign_to(
            destination_schema=connection.schema_name,
            quest_import_ids=import_ids,
            campaign_import_id=campaign.import_id,
        )

        self.assertTrue(result.has_errors())
        self.assertEqual(list(Quest.objects.all_including_archived().filter(import_id__in=import_ids)), [])
        self.assertFalse(Category.objects.filter(import_id=campaign.import_id).exists())
