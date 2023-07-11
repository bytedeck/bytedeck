from django.test import TestCase
from django.core.files import File
from django.template import Context, Template
from unittest.mock import MagicMock


class FilenameFilterTests(TestCase):

    def test_filename_existing_file(self):
        file_field_mock = MagicMock()
        file_field_mock.file = MagicMock(spec=File)
        file_field_mock.file.name = 'path/to/existing/file.txt'

        # Render the template with the filename filter
        context = Context({'value': file_field_mock})
        template = Template('{% load comment_tags %}{{ value|filename }}')
        rendered = template.render(context)

        # Assert that the rendered output matches the expected filename
        self.assertEqual(rendered, "file.txt")

    # TODO: Can't figure out how to get the method to raise the FileNotFoundError
    # Does that piece fo code do anything?
    # def test_filename_missing_file(self):
    #    # Mock the FileField object with a missing file
    #     file_field_mock = MagicMock()
    #     file_field_mock.file = MagicMock(spec=File)
    #     file_field_mock.file.name = ""

    #     # Render the template with the mocked FileField object
    #     context = Context({'value': file_field_mock})
    #     template = Template('{% load comment_tags %}{{ value|filename }}')
    #     rendered = template.render(context)

    #     # Assert that the rendered output includes the expected HTML string
    #     expected_output = '<i class="fa fa-exclamation-triangle text-warning"></i> [File Missing]'
    #     self.assertIn(expected_output, rendered)
