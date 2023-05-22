import logging

from xml.dom import DOMException
from cssutils import CSSParser

from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import ugettext_lazy as _

from crispy_forms.bootstrap import Accordion, AccordionGroup
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Layout

from .models import SiteConfig

User = get_user_model()


class SiteConfigForm(forms.ModelForm):

    class Meta:
        model = SiteConfig
        # active_semester setting moved to Semester views.
        exclude = ["active_semester"]

    def __init__(self, *args, **kwargs):
        is_deck_owner = kwargs.pop('is_deck_owner', False)

        super().__init__(*args, **kwargs)

        if not is_deck_owner:
            self.fields['custom_stylesheet'].disabled = True
            self.fields['custom_javascript'].disabled = True
            self.fields['deck_owner'].disabled = True

        self.fields['enable_google_signin'].disabled = True

        submit_btn = '<input type="submit" value="{{ submit_btn_value }}" class="btn btn-success"/> '

        self.helper = FormHelper()
        self.helper.layout = Layout(
            HTML(submit_btn),
            Div(
                "site_name",
                "site_name_short",
                "access_code",
                "banner_image",
                "banner_image_dark",
                "site_logo",
                "default_icon",
                "favicon",
                "submission_quick_text",
                "blank_approval_text",
                "blank_return_text",
                "outgoing_email_signature",
                "deck_ai",
                "color_headers_by_mark",
                "enable_google_signin",
                "approve_oldest_first",
                "display_marks_calculation",
                "cap_marks_at_100_percent",
                "custom_name_for_group",
                "custom_name_for_tag",
                Accordion(
                    AccordionGroup(
                        "Advanced",
                        "custom_stylesheet",
                        "custom_javascript",
                        "deck_owner",
                        active=False,
                        template="crispy_forms/bootstrap3/accordion-group.html",
                    ),
                ),
                HTML(submit_btn),
                style="margin-top: 10px;",
            ),
        )

    def clean_custom_stylesheet(self):
        """Check and/or validate uploaded stylesheet content"""
        if self.cleaned_data.get("custom_stylesheet") or self.files.get("custom_stylesheet"):
            css = self.cleaned_data["custom_stylesheet"] or self.files["custom_stylesheet"]
            # using "cssutils" library to check / validate stylesheet content
            parser = CSSParser(
                validate=True, raiseExceptions=True, loglevel=logging.ERROR
            )
            try:
                stylesheet = parser.parseString(css.read(), validate=True)
            except DOMException as e:
                raise forms.ValidationError(e)

            if not stylesheet.valid:
                raise forms.ValidationError(_("This stylesheet is not valid CSS."))

            return css

        return None

    def clean_custom_javascript(self):
        """Check and/or validate uploaded javascript content"""
        if self.cleaned_data.get("custom_javascript") or self.files.get("custom_javascript"):
            # TODO: implement javascript validation here
            return self.cleaned_data["custom_javascript"] or self.files["custom_javascript"]
        return None
