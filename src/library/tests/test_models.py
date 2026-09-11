import uuid

from django.test import SimpleTestCase
from freezegun import freeze_time

from library.models import ContentOrigin
from library.tests.test_views import LibraryTenantTestCaseMixin
from library.utils import library_schema_context


class ContentOriginStrTest(SimpleTestCase):
    """How an origin describes itself, e.g. in the admin or a shell."""

    def test_ContentOrigin_str__reads_as_the_attribution_it_records(self):
        """The string names the content, the person who shared it, and their deck."""
        import_id = uuid.uuid4()
        origin = ContentOrigin(
            import_id=import_id,
            content_type=ContentOrigin.QUEST,
            deck_name='Hackerspace',
            deck_url='http://hackerspace.example.com',
            shared_by='mr.thomas',
        )

        self.assertEqual(str(origin), f'Quest {import_id} shared by mr.thomas of Hackerspace')


class ContentOriginRecordTest(LibraryTenantTestCaseMixin):
    """Recording where content came from, including when it is shared more than once."""

    def test_ContentOrigin_record__re_sharing_updates_the_row_and_its_date(self):
        """Re-sharing refreshes the whole attribution, date included.

        The row names the most recent sharer, so leaving `shared_on` at the first push
        would date one person's share to another person's day.
        """
        import_id = uuid.uuid4()

        with library_schema_context():
            with freeze_time('2026-01-01 12:00:00'):
                first = ContentOrigin.record(
                    import_id=import_id,
                    content_type=ContentOrigin.QUEST,
                    deck_name='First Deck',
                    deck_url='http://first.example.com',
                    shared_by='first_teacher',
                )
                first_shared_on = first.shared_on

            with freeze_time('2026-06-01 12:00:00'):
                second = ContentOrigin.record(
                    import_id=import_id,
                    content_type=ContentOrigin.QUEST,
                    deck_name='Second Deck',
                    deck_url='http://second.example.com',
                    shared_by='second_teacher',
                )

            # still one row for this content, not a second one beside it
            self.assertEqual(
                ContentOrigin.objects.filter(import_id=import_id, content_type=ContentOrigin.QUEST).count(), 1
            )
            stored = ContentOrigin.objects.get(import_id=import_id, content_type=ContentOrigin.QUEST)

        self.assertEqual(second.pk, first.pk)
        self.assertEqual(stored.shared_by, 'second_teacher')
        self.assertEqual(stored.deck_name, 'Second Deck')
        self.assertGreater(stored.shared_on, first_shared_on)
        self.assertEqual(stored.shared_on.date().isoformat(), '2026-06-01')
