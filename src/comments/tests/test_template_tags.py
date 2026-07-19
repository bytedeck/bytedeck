from django.test import TestCase
from django.core.files import File
from django.template import Context, Template
from unittest.mock import MagicMock, PropertyMock


class FilenameFilterTests(TestCase):
    """Tests for the comment_tags.filename template filter."""

    def test_filename__returns_basename_for_existing_file(self):
        """The filter renders just the basename of the file's path."""
        file_field_mock = MagicMock()
        file_field_mock.file = MagicMock(spec=File)
        file_field_mock.file.name = 'path/to/existing/file.txt'

        # Render the template with the filename filter
        context = Context({'value': file_field_mock})
        template = Template('{% load comment_tags %}{{ value|filename }}')
        rendered = template.render(context)

        # Assert that the rendered output matches the expected filename
        self.assertEqual(rendered, "file.txt")

    def test_filename__returns_warning_for_missing_file(self):
        """When accessing the underlying file raises FileNotFoundError, the filter
        returns a "File Missing" warning instead of blowing up."""
        from comments.templatetags.comment_tags import filename

        # A FieldFile whose `.file` attribute raises FileNotFoundError when accessed,
        # mirroring a database row that points at a file no longer on disk. The filter
        # is called directly (not through a template) so its raw HTML isn't autoescaped.
        file_field_mock = MagicMock()
        type(file_field_mock).file = PropertyMock(side_effect=FileNotFoundError)

        expected_output = '<i class="fa fa-exclamation-triangle text-warning"></i> [File Missing]'
        self.assertEqual(filename(file_field_mock), expected_output)
