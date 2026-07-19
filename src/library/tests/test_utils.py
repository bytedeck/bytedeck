from django.db import connection
from django.test import SimpleTestCase
from library.utils import library_schema_context


class QuestLibraryUtilsTestCase(SimpleTestCase):

    def test_library_schema_context__switches_and_restores_schema(self):
        """The context manager switches to the library schema and restores the previous one on exit."""
        previous_schema = connection.schema_name

        with library_schema_context():
            self.assertEqual(connection.schema_name, 'library')

        self.assertEqual(connection.schema_name, previous_schema)
