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
                "banned_from_comments_text",
                "outgoing_email_signature",
                "deck_ai",
                "color_headers_by_mark",
                "enable_google_signin",
                "approve_oldest_first",
                "display_marks_calculation",
                "cap_marks_at_100_percent",
                "simplified_course_registration",
                "custom_name_for_badge",
                "custom_name_for_announcement",
                "custom_name_for_group",
                "custom_name_for_student",
                "custom_name_for_tag",
                Accordion(
                    AccordionGroup(
                        "Advanced",
                        HTML(
                            "<div class='help-block'><p class='text-danger'>"
                            "<b>Warning: </b> These features are only editable by the deck owner."
                            "</p></div>"
                        ),
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
        """
        Check if stylesheet file is uploaded, if not raise validation error.

        This method overrides default `clean_<fieldname>` method and parse <fieldname> upload
        using `cssutils` library to determine whether it is "valid" stylesheet or not.
        """
        # get data from form upload or do nothing if there is no uploads
        value = self.cleaned_data.get("custom_stylesheet", False)
        if value or self.files.get("custom_stylesheet"):
            css = value or self.files["custom_stylesheet"]

            # using CSS parser (from cssutils) to validate form upload,
            # for reference: https://pythonhosted.org/cssutils/docs/parse.html#cssparser
            parser = CSSParser(
                validate=True, raiseExceptions=True, loglevel=logging.ERROR
            )
            try:
                # call `parseString` method and parse uploaded file as string,
                # errors may be raised
                stylesheet = parser.parseString(css.read(), validate=True)
            except DOMException as e:
                # something wrong, render exception as validation error
                raise forms.ValidationError(e)

            # check if parsed stylesheet is a "valid" CSS file (according to `cssutils`),
            # if not raise validation error
            if not stylesheet.valid:
                raise forms.ValidationError(_("This stylesheet is not valid CSS."))

            # returns form upload as is
            return css

        # do nothing and return everything as is
        return value

    def clean_deck_owner(self):
        """
        Ensure deck owner is given superuser permissions.
        """
        super().clean()
        deck_owner = self.cleaned_data.get("deck_owner")
        if not deck_owner.is_superuser:
            deck_owner.is_superuser = True
            deck_owner.save()
        return deck_owner
