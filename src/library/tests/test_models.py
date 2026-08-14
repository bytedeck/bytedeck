import uuid

from django.test import SimpleTestCase

from library.models import ContentOrigin


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
