import bleach
import html as htmllib
import json

from django.conf import settings as django_settings
from django.forms.utils import flatatt
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.safestring import mark_safe

from bleach.css_sanitizer import CSSSanitizer
from django_summernote.utils import get_config
from django_summernote.widgets import SummernoteInplaceWidget, SummernoteWidget


class ByteDeckSummernoteWidget(SummernoteWidget):
    """
    Simplify upgrading to a newer `django_summernote.widgets.SummernoteWidget` class in a future.

    """
    def render(self, name, value, attrs=None, **kwargs):
        """Override default `render` method to use customized template file"""
        summernote_settings = self.summernote_settings()
        summernote_settings.update(self.attrs.get("summernote", {}))

        html = super(SummernoteWidget, self).render(name, value, attrs=attrs, **kwargs)
        context = {
            "id": attrs["id"],
            "id_safe": attrs["id"].replace("-", "_"),
            "flat_attrs": flatatt(self.final_attr(attrs)),
            "settings": json.dumps(summernote_settings),
            # using customized url here (mandatory for ByteDeck project)
            "src": reverse("bytedeck_summernote-editor", kwargs={"id": attrs["id"]}),
            # width and height have to be pulled out to create an iframe with correct size
            "width": summernote_settings["width"],
            "height": summernote_settings["height"],
        }

        # using customized template here (mandatory for ByteDeck project)
        html += render_to_string("bytedeck_summernote/widget_iframe.html", context)
        return mark_safe(html)


class ByteDeckSummernoteInplaceWidget(SummernoteInplaceWidget):
    """
    Simplify upgrading to a newer `django_summernote.widgets.SummernoteInplaceWidget` class in a future.

    """
    def render(self, name, value, attrs=None, **kwargs):
        """Override default `render` method to use customized template file"""
        summernote_settings = self.summernote_settings()
        summernote_settings.update(self.attrs.get("summernote", {}))

        html = super(SummernoteInplaceWidget, self).render(name, value, attrs=attrs, **kwargs)
        context = {
            "id": attrs["id"],
            "id_safe": attrs["id"].replace("-", "_"),
            "attrs": self.final_attr(attrs),
            "config": get_config(),
            "settings": json.dumps(summernote_settings),
            "CSRF_COOKIE_NAME": django_settings.CSRF_COOKIE_NAME,
        }

        # using customized template here (mandatory for ByteDeck project)
        html += render_to_string("bytedeck_summernote/widget_inplace.html", context)
        return mark_safe(html)


class ByteDeckSummernoteSafeWidgetMixin:
    """ByteDeck's Summernote implementation, so called 'Safe' variant"""

    def summernote_settings(self):
        """Override default `summernote_settings` method to inject mandatory settings"""
        summernote_settings = super().summernote_settings()

        # enable XSS protection for CodeView (mandatory for ByteDeck project)
        summernote_settings.update(
            {
                "codeviewFilter": True,  # set this to true to filter entities (tags, attributes or styles).
            }
        )
        return summernote_settings

    def value_from_datadict(self, data, files, name):
        """Override default `value_from_datadict` method to fix injection vulnerability"""
        from django_summernote.settings import ALLOWED_TAGS, ATTRIBUTES, STYLES

        value = super().value_from_datadict(data, files, name)
        # HTML escaping done with "bleach" library
        return bleach.clean(
            htmllib.unescape(value) if value else "",
            tags=ALLOWED_TAGS,
            attributes=ATTRIBUTES,
            css_sanitizer=CSSSanitizer(allowed_css_properties=STYLES),
        )


class ByteDeckSummernoteAdvancedWidgetMixin:
    """ByteDeck's Summernote implementation, so called 'Advanced' variant"""

    def summernote_settings(self):
        """Override default `summernote_settings` method to inject mandatory settings"""
        summernote_settings = super().summernote_settings()

        # disable XSS protection for CodeView (mandatory for ByteDeck project)
        summernote_settings.update(
            {
                "codeviewFilter": False,  # set this to false to skip filtering entities (tags, attributes or styles).
            }
        )
        return summernote_settings


class ByteDeckSummernoteSafeWidget(ByteDeckSummernoteSafeWidgetMixin, ByteDeckSummernoteWidget):
    """
    ByteDeck's Summernote implementation, so called 'Safe' variant.

    'Safe' widget (iframe variant) that escapes content entered in the text view
    (e.g. < are converted in the code to &lt;) and also strips script tags entered in the HTML/code view.
    """


class ByteDeckSummernoteSafeInplaceWidget(ByteDeckSummernoteSafeWidgetMixin, ByteDeckSummernoteInplaceWidget):
    """
    ByteDeck's Summernote implementation, so called 'Safe' variant.

    'Safe' widget (non-iframe aka inplace variant) that escapes content entered in the text view
    (e.g. < are converted in the code to &lt;) and also strips script tags entered in the HTML/code view.
    """


class ByteDeckSummernoteAdvancedWidget(ByteDeckSummernoteAdvancedWidgetMixin, ByteDeckSummernoteWidget):
    """
    ByteDeck's Summernote implementation, so called 'Advanced' variant.

    An 'Advanced' widget (iframe variant) that still escapes content entered in the text view
    (e.g. < are converted in the code to &lt;) but does *NOT* escape or strip code that is entered
    into HTML/code view, including <script> tags.
    """


class ByteDeckSummernoteAdvancedInplaceWidget(ByteDeckSummernoteAdvancedWidgetMixin, ByteDeckSummernoteInplaceWidget):
    """
    ByteDeck's Summernote implementation, so called 'Advanced' variant.

    An 'Advanced' widget (non-iframe aka inplace variant) that still escapes content entered in the text view
    (e.g. < are converted in the code to &lt;) but does *NOT* escape or strip code that is entered
    into HTML/code view, including <script> tags.
    """
