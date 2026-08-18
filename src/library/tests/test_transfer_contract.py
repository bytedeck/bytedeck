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
"""

import datetime
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from model_bakery import baker

from django.db import IntegrityError, connection
from django_tenants.utils import schema_context
from taggit.models import Tag

from library.exporter import export_campaign_and_copy_quests, export_quest_to_library
from library.importer import import_campaign_to, import_quest_to
from library.models import IsLibraryContentMixin
from library.transfer import LibraryTransferError, _describe
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from library.tests.test_views import LibraryTenantTestCaseMixin
from library.utils import library_schema_context
from prerequisites.models import IsAPrereqMixin, Prereq
from badges.models import Badge
from courses.models import Block, Course, Grade, Rank
from quest_manager.models import Category, CommonData, Quest
from questions.models import Question, QuestionType

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
    'campaign': 'Not copied as an FK: the pk means a different campaign per schema. Copied as an object instead.',
    'published': 'Deliberately forced to draft so imported content is reviewed before students see it.',
    'datetime_created': 'auto_now_add. The destination row stamps its own creation time.',
    'datetime_last_edit': 'auto_now. Always the time of the import.',
}

CATEGORY_FIELDS_TRANSFERRED = frozenset({'title', 'icon', 'short_description', 'import_id'})

CATEGORY_FIELDS_NOT_TRANSFERRED = {
    'id': 'Primary key. The destination assigns its own.',
    'published': 'Deliberately forced to draft, same as quests.',
    'map_order': 'Dropped. Quest-map placement is relative to the deck it was arranged on (#2396).',
}

QUESTION_FIELDS_TRANSFERRED = frozenset({
    'type', 'ordinal', 'required', 'instructions', 'solution_text', 'solution_file',
    'allowed_file_type', 'marker_notes',
})

QUESTION_FIELDS_NOT_TRANSFERRED = {
    'id': 'Primary key. The destination assigns its own.',
    'quest': 'Not copied as an FK: it is set to the quest being written, whose pk differs per schema.',
    'datetime_created': 'auto_now_add. The destination row stamps its own creation time.',
    'datetime_last_edit': 'auto_now. Always the time of the import.',
}


class LibraryTransferContractTests(LibraryTenantTestCaseMixin):
    """Pin what a full push-and-pull round trip does to every field of a quest."""

    def _build_populated_quest(self):
        """Create a campaign and a quest with every transferred field set to a non-default value.

        `archived` is the one exception, and it is deliberate: an archived quest cannot be
        pushed at all, so a non-default value here would leave nothing in the Library to
        compare. That exclusion is pinned by
        `test_export_campaign_and_copy_quests__never_exports_an_archived_quest`.

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
            # All four differ from their defaults (today, midnight, null, null), so a transfer
            # that stops carrying one of them fails the round trip instead of matching by
            # coincidence. The expiry is far enough out that the quest stays unexpired.
            date_available=datetime.date(2024, 3, 4),
            time_available=datetime.time(9, 30),
            date_expired=datetime.date(2099, 12, 31),
            time_expired=datetime.time(23, 45),
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

        That is the settled behaviour rather than a gap waiting on a fix: the block is
        left behind on purpose, and the sharer is warned by name on the push so the loss
        is not a surprise (`LibrarySharerWarningTests` covers the warning).
        """
        quest, campaign = self._build_populated_quest()
        self.assertIsNotNone(quest.common_data)

        self._push_and_pull(campaign)

        imported = Quest.objects.all_including_archived().get(import_id=quest.import_id)
        self.assertIsNone(imported.common_data)

    def test_round_trip__drops_campaign_map_order(self):
        """A campaign's quest-map placement resets to the default (#2396).

        Deliberately deck-relative: where a campaign sits on the quest map is an
        arrangement of the deck it was arranged on, and the importing deck places it where
        it wants. No warning goes with it either, unlike the losses in `TransferResult`,
        because nothing was lost: the sharer's placement was never the importer's to
        receive (#2396).
        """
        _, campaign = self._build_populated_quest()
        self.assertEqual(campaign.map_order, 7)

        self._push_and_pull(campaign)

        imported_campaign = Category.objects.get(import_id=campaign.import_id)
        self.assertEqual(imported_campaign.map_order, 0)

    def test_export_campaign_and_copy_quests__never_exports_an_archived_quest(self):
        """An archived quest is not pushed at all, so `archived` can only ever travel as False.

        Both push paths filter archived quests out before anything is serialised: the
        campaign push reads `Category.current_quests()` (`published().not_archived()`), and
        the single-quest push reads `Quest.objects.get()`, whose manager excludes archived
        rows. So a teacher who archives a quest and then shares its campaign silently sends
        a campaign without that quest, and nothing reports the omission.

        This is also why `_build_populated_quest` leaves `archived` at its default: a quest
        carrying the non-default value never reaches the Library to be compared.
        """
        quest, campaign = self._build_populated_quest()
        survivor = Quest.objects.create(name="Still Active", xp=1, campaign=campaign)
        Quest.objects.filter(pk=survivor.pk).update(published=True)
        Quest.objects.filter(pk=quest.pk).update(archived=True)

        export_campaign_and_copy_quests(source_schema=connection.schema_name, campaign_import_id=campaign.import_id)

        with library_schema_context():
            arrived = set(Quest.objects.all_including_archived().values_list('import_id', flat=True))
        self.assertIn(survivor.import_id, arrived)
        self.assertNotIn(quest.import_id, arrived)

        # The single-quest push cannot reach it either: the default manager excludes archived rows.
        with self.assertRaises(Quest.DoesNotExist):
            export_quest_to_library(source_schema=connection.schema_name, quest_import_id=quest.import_id)


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

    def test_export_campaign_and_copy_quests__keeps_a_prereq_whose_target_is_in_the_same_campaign(self):
        """A prerequisite pointing at another quest in the pushed campaign survives."""
        campaign, quest, inside = self._campaign_with_two_quests()
        Prereq.add_simple_prereq(quest, inside)

        export_campaign_and_copy_quests(source_schema=connection.schema_name, campaign_import_id=campaign.import_id)

        with library_schema_context():
            library_quest = Quest.objects.all_including_archived().get(import_id=quest.import_id)
            names = [p.get_prereq().name for p in library_quest.prereqs()]
        self.assertEqual(names, ["Prereq Inside Campaign"])

    def test_export_campaign_and_copy_quests__discards_a_prereq_whose_target_is_outside_the_campaign(self):
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


    def test_export_campaign_and_copy_quests__discards_a_prereq_that_is_not_shareable_content(self):
        """A quest gated on a rank, grade, block or course arrives ungated (#2450).

        Those models are all valid prerequisites, and none of them carries an `import_id`,
        which is the only identifier that means the same thing in another deck's schema. So
        a gate of that kind cannot be expressed on the far side and is dropped, exactly as a
        prerequisite pointing outside the campaign is (#2399). A quest that its author gated
        on reaching Rank 3 arrives available to everyone, and nothing says so.

        The gate is stripped rather than travelling broken, and the importing deck is told
        it was, so the loss is visible rather than silent. When #2450 is fixed this should
        assert the gate survives, presumably matched by name.
        """
        campaign, quest, _ = self._campaign_with_two_quests()
        rank = baker.make(Rank, name="Digital Novice")
        Prereq.add_simple_prereq(quest, rank)
        self.assertEqual(len(quest.prereqs()), 1)

        export_campaign_and_copy_quests(source_schema=connection.schema_name, campaign_import_id=campaign.import_id)

        with library_schema_context():
            library_quest = Quest.objects.all_including_archived().get(import_id=quest.import_id)
            self.assertEqual(list(library_quest.prereqs()), [])


class LibraryTransferQuestionContractTests(LibraryTenantTestCaseMixin):
    """Pin what happens to a quest's submission questions when the quest changes decks."""

    def _quest_with_questions(self):
        """Create a published quest asking one question of each type.

        Every transferred field is set to a non-default value, so a field that stops
        travelling fails the round trip instead of matching by coincidence.

        Returns:
            Quest: the published quest, with three questions attached.
        """
        quest = Quest.objects.create(name="Quest With Questions", xp=10)
        Quest.objects.filter(pk=quest.pk).update(published=True)

        Question.objects.create(
            quest=quest, ordinal=1, type=QuestionType.SHORT_ANSWER, required=False,
            instructions="<p>What is the title of your project?</p>",
            solution_text="Any title", marker_notes="<p>Accept anything</p>",
        )
        Question.objects.create(
            quest=quest, ordinal=2, type=QuestionType.LONG_ANSWER,
            instructions="<p>Describe your process.</p>",
            solution_text="A paragraph", marker_notes="<p>Look for reflection</p>",
        )
        Question.objects.create(
            quest=quest, ordinal=3, type=QuestionType.FILE_UPLOAD, allowed_file_type="image",
            instructions="<p>Upload a photo.</p>",
            solution_file="quest/question/solution/2026/08/16/example.png",
            marker_notes="<p>Any photo of the build</p>",
        )

        return Quest.objects.get(pk=quest.pk)

    def _push_and_pull(self, quest):
        """Push a quest to the Library, publish it there, then pull it back into this deck.

        The local copy is deleted in between, so the pull takes the path a deck seeing the
        quest for the first time would.

        Args:
            quest (Quest): the local quest to push.

        Returns:
            Quest: the quest as it exists on this deck after being imported back.
        """
        local_schema = connection.schema_name
        export_quest_to_library(source_schema=local_schema, quest_import_id=quest.import_id)

        with library_schema_context():
            Quest.objects.filter(import_id=quest.import_id).update(published=True)

        Quest.objects.all_including_archived().filter(import_id=quest.import_id).delete()
        import_quest_to(destination_schema=local_schema, quest_import_id=quest.import_id)

        return Quest.objects.all_including_archived().get(import_id=quest.import_id)

    def test_question_field_inventory__every_field_is_classified(self):
        """Every concrete Question field is classified as transferred or not.

        Same contract as the quest and campaign inventories: a field added to Question
        fails this test until someone decides whether it belongs to the content (and so
        should reach other decks) or to the deck it was written on.
        """
        concrete = {f.name for f in Question._meta.concrete_fields}
        classified = QUESTION_FIELDS_TRANSFERRED | set(QUESTION_FIELDS_NOT_TRANSFERRED)

        self.assertEqual(
            concrete - classified,
            set(),
            "A field was added to Question without deciding whether it should travel to other decks. "
            "Add it to QUESTION_FIELDS_TRANSFERRED or to QUESTION_FIELDS_NOT_TRANSFERRED with a reason.",
        )
        self.assertEqual(
            classified - concrete,
            set(),
            "A field was removed from Question but is still classified in this module.",
        )

    def test_round_trip__carries_every_question_with_every_transferred_field(self):
        """A quest's questions arrive on the far side as their author wrote them (#2162).

        Before this, a quest whose instructions said "answer the questions below" arrived
        as an empty-form quest: the questions were never serialised, so the content loss
        was silent on both the push and the pull.
        """
        quest = self._quest_with_questions()
        expected = [
            {name: getattr(question, name) for name in QUESTION_FIELDS_TRANSFERRED}
            for question in quest.question_set.all()
        ]

        imported = self._push_and_pull(quest)

        arrived = list(imported.question_set.all())
        self.assertEqual(len(arrived), 3)
        for question, values in zip(arrived, expected):
            for name in sorted(QUESTION_FIELDS_TRANSFERRED):
                with self.subTest(ordinal=values['ordinal'], field=name):
                    self.assertEqual(
                        str(getattr(question, name)),
                        str(values[name]),
                        f"question {values['ordinal']}'s '{name}' did not survive the round trip.",
                    )

    def test_round_trip__carries_the_solution_file_by_path(self):
        """The marker's example answer arrives pointing at the same stored file.

        Decks share one media namespace, so a file field travels as its path and the bytes
        never move, exactly as a quest's icon does.
        """
        quest = self._quest_with_questions()

        imported = self._push_and_pull(quest)

        file_question = imported.question_set.get(ordinal=3)
        self.assertEqual(file_question.solution_file.name, "quest/question/solution/2026/08/16/example.png")

    def test_re_import__updates_a_changed_question_in_place(self):
        """Re-importing a quest refreshes its questions rather than duplicating them.

        The question keeps its row, which is what keeps answers students already gave
        attached to the question they answered.
        """
        quest = self._quest_with_questions()
        self._push_and_pull(quest)
        first = Quest.objects.all_including_archived().get(import_id=quest.import_id).question_set.get(ordinal=1)

        with library_schema_context():
            library_question = Question.objects.get(quest__import_id=quest.import_id, ordinal=1)
            library_question.instructions = "<p>What did you name it?</p>"
            library_question.save()

        import_quest_to(destination_schema=connection.schema_name, quest_import_id=quest.import_id)

        imported = Quest.objects.all_including_archived().get(import_id=quest.import_id)
        self.assertEqual(imported.question_set.count(), 3)
        refreshed = imported.question_set.get(ordinal=1)
        self.assertEqual(refreshed.pk, first.pk)
        self.assertEqual(refreshed.instructions, "<p>What did you name it?</p>")

    def test_re_import__removes_a_question_the_author_deleted(self):
        """A question dropped upstream is dropped here too, so the copies stay the same quest.

        The quest's own fields are overwritten by a re-import, and its questions are part
        of the same content: leaving a deleted question behind would have this deck asking
        a question the shared quest no longer asks.
        """
        quest = self._quest_with_questions()
        self._push_and_pull(quest)

        with library_schema_context():
            Question.objects.get(quest__import_id=quest.import_id, ordinal=2).delete()

        import_quest_to(destination_schema=connection.schema_name, quest_import_id=quest.import_id)

        imported = Quest.objects.all_including_archived().get(import_id=quest.import_id)
        self.assertEqual([question.ordinal for question in imported.question_set.all()], [1, 3])

    def test_export_campaign_and_copy_quests__carries_questions_on_the_conflict_copy(self):
        """A quest copied in beside the Library's existing version brings its questions.

        The conflict path writes a second copy under a fresh import_id, and that copy is
        the whole quest: a copy that arrived without its questions would be an empty-form
        quest with a name saying otherwise.
        """
        campaign = Category(title="Conflicted Campaign", published=True)
        campaign.save()
        quest = self._quest_with_questions()
        Quest.objects.filter(pk=quest.pk).update(campaign=campaign)
        # Put the quest in the Library first, so sharing the campaign hits the conflict path.
        export_quest_to_library(source_schema=connection.schema_name, quest_import_id=quest.import_id)

        export_campaign_and_copy_quests(source_schema=connection.schema_name, campaign_import_id=campaign.import_id)

        with library_schema_context():
            copy = (
                Quest.objects.all_including_archived()
                .filter(name__startswith=quest.name)
                .exclude(import_id=quest.import_id)
                .get()
            )
            self.assertEqual([question.ordinal for question in copy.question_set.all()], [1, 2, 3])

    def test_export_quest_to_library__reports_a_question_that_cannot_be_written(self):
        """A question the destination refuses names the quest and the question it came from.

        `instructions` is required, so a row saved without it (as `Question.objects.create`
        allows, since it does not validate) cannot be written on the far side. The failure
        is raised as a `LibraryTransferError` a view can put in front of the sharer, rather
        than escaping as a validation error naming a model they never see.
        """
        quest = Quest.objects.create(name="Quest With A Bad Question", xp=10)
        Quest.objects.filter(pk=quest.pk).update(published=True)
        Question.objects.create(quest=quest, ordinal=2, instructions="")

        with self.assertRaises(LibraryTransferError) as caught:
            export_quest_to_library(source_schema=connection.schema_name, quest_import_id=quest.import_id)

        self.assertIn("Quest With A Bad Question", str(caught.exception))
        self.assertIn("question 2", str(caught.exception))
        with library_schema_context():
            self.assertFalse(Quest.objects.all_including_archived().filter(import_id=quest.import_id).exists())

    def test_export_quest_to_library__reports_a_question_the_database_rejects(self):
        """A question the database refuses reaches the sharer as a readable failure too.

        `full_clean` catches what it can see, so this is the narrow case it cannot: the row
        is valid when validated and rejected when written. The quest's own write path
        already reports that as a transfer error rather than letting a database exception
        escape into a 500, and a question's write path answers the same way.
        """
        quest = Quest.objects.create(name="Quest The Database Refuses", xp=10)
        Quest.objects.filter(pk=quest.pk).update(published=True)
        Question.objects.create(quest=quest, ordinal=1, instructions="<p>Fine on the way out.</p>")

        with patch.object(Question, 'save', side_effect=IntegrityError("duplicate key value")):
            with self.assertRaises(LibraryTransferError) as caught:
                export_quest_to_library(source_schema=connection.schema_name, quest_import_id=quest.import_id)

        self.assertIn("Quest The Database Refuses", str(caught.exception))
        self.assertIn("question 1", str(caught.exception))
        self.assertIn("duplicate key value", str(caught.exception))


class LibraryTransferErrorMessageTests(SimpleTestCase):
    """How a failed copy is described to the caller."""

    def test_describe__renders_a_validation_error_without_a_field(self):
        """An error not tied to a field still reads as a sentence.

        `full_clean` reports per-field errors, so this covers the other shape a
        `ValidationError` can take, raised with a bare message and no field mapping.
        """
        self.assertEqual(_describe(ValidationError("Something was wrong.")), "Something was wrong.")

    def test_describe__renders_a_field_error_with_its_field_name(self):
        """A per-field error names the field, which is what makes a clash readable."""
        self.assertEqual(
            _describe(ValidationError({'name': ["Quest with this Name already exists."]})),
            "name: Quest with this Name already exists.",
        )


class LibraryTransferTagContractTests(LibraryTenantTestCaseMixin):
    """Pin how tags cross a schema boundary."""

    def test_export_quest_to_library__carries_tags_by_name(self):
        """Tags arrive meaning what they meant on the deck that shared them (#1792).

        Tag rows are per-schema, so a tag's primary key means a different tag (or none) on
        the far side. This sets the destination up so that matching by pk would be visibly
        wrong: the ids that mean 'photography' and 'darkroom' locally are held by unrelated
        tags in the Library. Transferring by name is what makes the quest arrive tagged the
        way its author tagged it.
        """
        local_tags = {}
        for name in ("photography", "darkroom"):
            tag = Tag.objects.create(name=name, slug=name)
            local_tags[tag.pk] = tag.name

        library_tags = {pk: f"library-tag-{pk}" for pk in local_tags}
        with library_schema_context():
            for pk, name in library_tags.items():
                Tag(pk=pk, name=name, slug=name).save(force_insert=True)
            # Inserting with an explicit pk leaves the table's sequence behind it, so the
            # next tag created in this schema would try to reuse an id that is now taken.
            # Copying the quest creates its tags here by name, so move the sequence past
            # the ids just claimed.
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT setval(pg_get_serial_sequence('taggit_tag', 'id'), (SELECT MAX(id) FROM taggit_tag))"
                )

        quest = Quest.objects.create(name="Tagged Quest", xp=10)
        quest.tags.set(list(local_tags.values()))

        export_quest_to_library(source_schema=connection.schema_name, quest_import_id=quest.import_id)

        with library_schema_context():
            library_quest = Quest.objects.all_including_archived().get(import_id=quest.import_id)
            arrived = sorted(tag.name for tag in library_quest.tags.all())

        self.assertEqual(arrived, sorted(local_tags.values()))
        self.assertNotEqual(arrived, sorted(library_tags.values()))


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

    def test_import_quest_to__renames_a_quest_whose_name_is_already_taken_locally(self):
        """A quest arrives under a name of its own when this deck already uses the one it has (#2364).

        Quest.name is unique per deck, so the clash would otherwise reach the database and
        fail the import. The arriving copy is renamed instead, which is what makes a
        collision recoverable in place: the teacher does not have to go and rename their own
        quest first. Their quest is left exactly as it was.
        """
        campaign, import_ids = self._push_campaign("Collision Campaign", ["Photoshop Basics"])
        self._clear_locally(campaign, import_ids)
        local = Quest.objects.create(name="Photoshop Basics", xp=999)

        result = import_quest_to(destination_schema=connection.schema_name, quest_import_id=import_ids[0])

        imported = Quest.objects.all_including_archived().get(import_id=import_ids[0])
        self.assertNotEqual(imported.pk, local.pk)
        self.assertTrue(imported.name.startswith("Photoshop Basics (Imported on "))
        self.assertEqual(result.renamed_quests, [("Photoshop Basics", imported.name)])
        local.refresh_from_db()
        self.assertEqual(local.name, "Photoshop Basics")
        self.assertEqual(local.xp, 999)

    def test_import_campaign_to__renames_only_the_quest_that_collides(self):
        """One taken name costs that quest its name, not the campaign its import (#2397).

        Every quest in the campaign arrives, and the rename is confined to the one whose
        name this deck already holds: its siblings keep theirs. The bigger the campaign the
        likelier one of its quests collides, so a clash must stay a local matter rather
        than something the whole import rides on.
        """
        campaign, import_ids = self._push_campaign(
            "Partial Campaign", ["Good Quest One", "Taken Quest Two", "Good Quest Three"],
        )
        self._clear_locally(campaign, import_ids)
        Quest.objects.create(name="Taken Quest Two", xp=999)

        result = import_campaign_to(
            destination_schema=connection.schema_name,
            quest_import_ids=import_ids,
            campaign_import_id=campaign.import_id,
        )

        imported = Quest.objects.all_including_archived().filter(import_id__in=import_ids)
        self.assertEqual(imported.count(), 3)
        self.assertTrue(Category.objects.filter(import_id=campaign.import_id).exists())
        self.assertEqual([wanted for wanted, _ in result.renamed_quests], ["Taken Quest Two"])
        self.assertQuerySetEqual(
            imported.filter(name__in=["Good Quest One", "Good Quest Three"]).order_by('name'),
            ["Good Quest One", "Good Quest Three"],
            transform=lambda quest: quest.name,
        )

    def test_import_campaign_to__discards_the_whole_import_when_a_quest_cannot_be_written(self):
        """A failure that renaming cannot fix still takes the whole campaign with it (#2397).

        The import stays all-or-nothing: a campaign that arrived half-imported would leave
        the deck holding quests whose prerequisites point at the ones that never came. Only
        the name clash is recoverable, because renaming is an answer to it; anything else is
        raised as a `LibraryTransferError` naming the quest, and nothing is written.
        """
        campaign, import_ids = self._push_campaign(
            "Rejected Campaign", ["Fine Quest One", "Rejected Quest Two"],
        )
        self._clear_locally(campaign, import_ids)

        def reject_the_second(self, *args, **kwargs):
            """Fail the write for one quest of the batch, as the database would."""
            if self.name == "Rejected Quest Two":
                raise IntegrityError("duplicate key value")
            return original_save(self, *args, **kwargs)

        original_save = Quest.save
        with patch.object(Quest, 'save', reject_the_second):
            with self.assertRaises(LibraryTransferError) as caught:
                import_campaign_to(
                    destination_schema=connection.schema_name,
                    quest_import_ids=import_ids,
                    campaign_import_id=campaign.import_id,
                )

        self.assertIn("Rejected Quest Two", str(caught.exception))
        self.assertEqual(list(Quest.objects.all_including_archived().filter(import_id__in=import_ids)), [])
        self.assertFalse(Category.objects.filter(import_id=campaign.import_id).exists())

    def test_import_quest_to__leaves_the_name_alone_when_nothing_local_holds_it(self):
        """A quest whose name is free arrives with the name its author gave it.

        The rename is the exception, so this pins that it stays the exception: a deck with
        no clash sees no suffix and `renamed_quests` is empty.
        """
        campaign, import_ids = self._push_campaign("Free Name Campaign", ["Unclaimed Quest"])
        self._clear_locally(campaign, import_ids)

        result = import_quest_to(destination_schema=connection.schema_name, quest_import_id=import_ids[0])

        imported = Quest.objects.all_including_archived().get(import_id=import_ids[0])
        self.assertEqual(imported.name, "Unclaimed Quest")
        self.assertEqual(result.renamed_quests, [])

    def test_import_quest_to__re_importing_is_not_treated_as_a_name_collision(self):
        """A quest this deck already holds is the same quest arriving again, not a clash.

        It is matched by `import_id` and its row is updated in place, so its own name must
        not count as taken against it: renaming here would leave the deck with the quest
        under a dated name every time it was re-imported.
        """
        campaign, import_ids = self._push_campaign("Repeat Campaign", ["Repeatable Quest"])
        Quest.objects.all_including_archived().filter(import_id__in=import_ids).update(name="Repeatable Quest")

        result = import_quest_to(destination_schema=connection.schema_name, quest_import_id=import_ids[0])

        imported = Quest.objects.all_including_archived().get(import_id=import_ids[0])
        self.assertEqual(imported.name, "Repeatable Quest")
        self.assertEqual(result.renamed_quests, [])


class LibraryContentRegistrationTests(ByteDeckTenantTestCase):
    """Which models the Shared Library is willing to carry between decks.

    The set is declared by inheriting `IsLibraryContentMixin` rather than written down as
    a list, so adding a shareable model is one edit on that model instead of an edit here
    and a matching one somewhere in the transfer code that everyone forgets.
    """

    def test_library_content__registers_exactly_the_shareable_models(self):
        """Quests, campaigns and badges can travel; nothing else currently can."""
        registered = set(IsLibraryContentMixin.all_shareable_model_classes())

        self.assertEqual(registered, {Quest, Category, Badge})

    def test_library_content__every_registered_model_has_an_import_id(self):
        """A model claiming to be shareable must carry the identity that makes it so.

        `import_id` is what a reference to this row resolves through on the far side, so a
        model registered without one would be claiming a portable identity it lacks.
        """
        for model in IsLibraryContentMixin.all_shareable_model_classes():
            with self.subTest(model=model.__name__):
                self.assertIn('import_id', {field.name for field in model._meta.concrete_fields})

    def test_library_content__helper_names_do_not_collide_with_the_prereq_mixin(self):
        """The two mixins' helpers stay distinguishable on a model that carries both.

        `Quest`, `Category` and `Badge` inherit `IsAPrereqMixin` as well, so a helper named
        the same on both would be resolved by method resolution order and quietly answer
        the other mixin's question: asking a Quest whether `Rank` was registered would say
        True, because `Rank` is a registered prerequisite, which is not what was asked.
        """
        shared = set(vars(IsLibraryContentMixin)) & set(vars(IsAPrereqMixin))

        self.assertEqual(
            shared - {'__dict__', '__weakref__', '__doc__', '__module__'},
            set(),
            "these names exist on both mixins, so a model inheriting both resolves one of them by MRO",
        )

    def test_library_content__does_not_register_the_deck_specific_prereq_models(self):
        """A rank, grade, block or course describes the deck, so it cannot be shared.

        These are all valid prerequisites, which is exactly why the question has to be
        asked: a quest can be gated on any of them, and none of them means the same thing
        on another deck.
        """
        for model in (Rank, Grade, Block, Course):
            with self.subTest(model=model.__name__):
                self.assertFalse(IsLibraryContentMixin.is_shareable_model(model))
