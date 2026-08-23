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

    def test_filename__escapes_a_name_containing_markup(self):
        """A file name is escaped by the template, so it cannot inject markup.

        The filter is rendered without ``|safe`` precisely so this stays true of a name that
        reaches storage with markup characters in it.
        """
        file_field_mock = MagicMock()
        file_field_mock.file = MagicMock(spec=File)
        file_field_mock.file.name = 'uploads/<script>bad.png'

        rendered = Template('{% load comment_tags %}{{ value|filename }}').render(Context({'value': file_field_mock}))

        self.assertNotIn('<script>', rendered)
        self.assertEqual(rendered, '&lt;script&gt;bad.png')

    def test_filename__missing_file_marker_keeps_its_icon(self):
        """The "file missing" marker is the one part that renders as markup, for its warning icon."""
        file_field_mock = MagicMock()
        type(file_field_mock).file = PropertyMock(side_effect=FileNotFoundError)

        rendered = Template('{% load comment_tags %}{{ value|filename }}').render(Context({'value': file_field_mock}))

        self.assertEqual(rendered, '<i class="fa fa-exclamation-triangle text-warning"></i> [File Missing]')


class PortfolioButtonTitleTests(TestCase):
    """Tests for the "Add <name> to your portfolio." title comments.html builds from a filename.

    A title is an attribute, so the name has to arrive there as text: the missing-file marker's
    icon would open a tag inside the attribute, and a name carrying quotes would end it early.
    """

    # the filter chain comments.html uses for the portfolio button's tooltip
    TEMPLATE = '{% load comment_tags %}<a title="Add {{ value|filename|striptags }} to your portfolio.">'

    def render(self, file_field_mock):
        """Render the portfolio button's opening tag for the given file.

        Args:
            file_field_mock: stand-in for a Document's ``docfile``.

        Returns:
            str: the rendered anchor tag, with the title attribute as a browser would receive it.
        """
        return Template(self.TEMPLATE).render(Context({'value': file_field_mock}))

    def test_title__names_the_file(self):
        """An ordinary attachment is named in the title, by its basename."""
        file_field_mock = MagicMock()
        file_field_mock.file = MagicMock(spec=File)
        file_field_mock.file.name = 'uploads/my_drawing.png'

        self.assertEqual(self.render(file_field_mock), '<a title="Add my_drawing.png to your portfolio.">')

    def test_title__missing_file_marker_loses_its_icon(self):
        """A row pointing at a file that has gone missing leaves no markup in the attribute.

        The filter marks that marker safe for the icon it renders in the file list, so without
        stripping the tags it would land inside the title attribute as an open tag.
        """
        file_field_mock = MagicMock()
        type(file_field_mock).file = PropertyMock(side_effect=FileNotFoundError)

        rendered = self.render(file_field_mock)

        self.assertNotIn('<i', rendered)
        self.assertEqual(rendered, '<a title="Add  [File Missing] to your portfolio.">')

    def test_title__escapes_a_name_that_would_end_the_attribute(self):
        """A name containing a quote is escaped, so it cannot break out of the title attribute."""
        file_field_mock = MagicMock()
        file_field_mock.file = MagicMock(spec=File)
        file_field_mock.file.name = 'uploads/bad" onmouseover="alert(1).png'

        rendered = self.render(file_field_mock)

        self.assertEqual(rendered, '<a title="Add bad&quot; onmouseover=&quot;alert(1).png to your portfolio.">')
