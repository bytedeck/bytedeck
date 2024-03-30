from django.db import connection
from django.test import SimpleTestCase
from library.utils import library_schema_context


class QuestLibraryUtilsTestCase(SimpleTestCase):

    def test_library_schema_context(self):

        with library_schema_context():
            self.assertEqual(connection.schema_name, 'library')

        self.assertEqual(connection.schema_name, 'public')
