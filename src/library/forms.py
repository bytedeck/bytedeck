from django import forms


class ShareLicenceForm(forms.Form):
    """Confirms the sharer agrees to the Shared Library's content licence.

    Content pushed to the Shared Library is published to every other deck under
    CC BY-SA 4.0, and #1546 requires the sharer to agree to that before the push
    goes through. The confirmation templates mark the checkbox `required`, but
    that is a browser-side hint only: this form is what actually holds the push.
    """

    agree_license = forms.BooleanField(
        required=True,
        label="I agree to share this content under the Creative Commons Attribution-ShareAlike 4.0 International License.",
        error_messages={
            "required": "You need to agree to the Creative Commons license before sharing to the Library.",
        },
    )
