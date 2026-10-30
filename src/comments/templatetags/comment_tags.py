import os

from django import template
from django.forms import FileField
from django.utils.safestring import mark_safe

from comments.sanitize import sanitize_comment_html as _sanitize_comment_html

register = template.Library()


@register.filter
def sanitize_comment_html(value):
    """Return ``value`` as comment HTML: its formatting and links kept, anything that could run
    script removed, as a comment's own text is when it is saved (see ``comments.sanitize``).

    The result is not marked safe, so it is escaped where it is output; a page that inserts it as
    HTML reads it back out of an attribute, such as a quick reply button's ``data-quick-reply``.
    """
    return _sanitize_comment_html(value)


# @register.filter
# def content_type(obj):
#     if not obj:
#         return False
#     return ContentType.objects.get_for_model(obj)


@register.filter
def filename(value: FileField):
    """Accepts a FileField object and returns the file's name.

    Callers render this without ``|safe``: the name comes from an uploaded file, so it is left
    for autoescaping, and only the fixed marker shown when the file has gone missing from
    storage is marked safe for its warning icon.
    """
    try:
        return os.path.basename(value.file.name)
    except FileNotFoundError:
        return mark_safe('<i class="fa fa-exclamation-triangle text-warning"></i> [File Missing]')
