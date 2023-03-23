import html as htmllib
import json
import bleach

from django.urls import reverse
from django.conf import settings as django_settings
from django.forms.utils import flatatt
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

from bleach.css_sanitizer import CSSSanitizer
from django_summernote.widgets import SummernoteWidget, SummernoteInplaceWidget
from django_summernote.utils import get_config


class ByteDeckSummernoteAdvancedWidget(SummernoteWidget):

    def render(self, name, value, attrs=None, **kwargs):
        """Override default `render` method to use customized template file"""
        summernote_settings = self.summernote_settings()
        summernote_settings.update(self.attrs.get('summernote', {}))

        # XSS protection for CodeView (mandatory for ByteDeck project)
        summernote_settings.update({
            'codeviewFilter': True,  # set this to true to filter entities.
            'codeviewIframeFilter': True,
        })

        html = super(SummernoteWidget, self).render(name, value, attrs=attrs, **kwargs)
        context = {
            'id': attrs['id'],
            'id_safe': attrs['id'].replace('-', '_'),
            'flat_attrs': flatatt(self.final_attr(attrs)),
            'settings': json.dumps(summernote_settings),
            # using customized url here...
            'src': reverse('bytedeck_summernote-editor', kwargs={'id': attrs['id']}),

            # Width and height have to be pulled out to create an iframe with correct size
            'width': summernote_settings['width'],
            'height': summernote_settings['height'],
        }

        # using customized template here...
        html += render_to_string('bytedeck_summernote/widget_advanced.html', context)
        return mark_safe(html)


class ByteDeckSummernoteSafeWidget(SummernoteInplaceWidget):

    def render(self, name, value, attrs=None, **kwargs):
        """Override default `render` method to use customized template file"""
        summernote_settings = self.summernote_settings()
        summernote_settings.update(self.attrs.get('summernote', {}))

        # XSS protection for CodeView (mandatory for ByteDeck project)
        summernote_settings.update({
            'codeviewFilter': True,  # set this to true to filter entities.
            'codeviewIframeFilter': True,
        })

        html = super(SummernoteInplaceWidget, self).render(name, value, attrs=attrs, **kwargs)
        context = {
            'id': attrs['id'],
            'id_safe': attrs['id'].replace('-', '_'),
            'attrs': self.final_attr(attrs),
            'config': get_config(),
            'settings': json.dumps(summernote_settings),
            'CSRF_COOKIE_NAME': django_settings.CSRF_COOKIE_NAME,
        }

        # using customized template here...
        html += render_to_string('bytedeck_summernote/widget_safe.html', context)
        return mark_safe(html)

    def value_from_datadict(self, data, files, name):
        """Override default `value_from_datadict` method to fix injection vulnerability"""
        from django_summernote.settings import ALLOWED_TAGS, ATTRIBUTES, STYLES
        from django_summernote.utils import get_config

        config = get_config()
        value = data.get(name, None)

        if value in config['empty']:
            return None

        # HTML escaping done with "bleach" library
        value = bleach.clean(
            htmllib.unescape(value) if value else "",
            tags=ALLOWED_TAGS,
            attributes=ATTRIBUTES,
            css_sanitizer=CSSSanitizer(allowed_css_properties=STYLES),
        )

        return value
