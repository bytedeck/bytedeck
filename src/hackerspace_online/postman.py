# Project customizations for django-postman

from django import forms
from django.contrib.auth import get_user_model

from postman.forms import WriteForm, AnonymousWriteForm
from postman.views import WriteView
from postman.fields import BasicCommaSeparatedUserField
from django_select2.forms import ModelSelect2MultipleWidget
from django_summernote.widgets import SummernoteInplaceWidget
from attachments.models import Attachment

from djconfig import config

from utilities.fields import RestrictedFileFormField

from comments.models import clean_html
# from django_summernote.widgets import SummernoteInplaceWidget


User = get_user_model()


class UserCustomTitleWidget(ModelSelect2MultipleWidget):
    model = User

    search_fields = [
        'profile__first_name__istartswith',
        'profile__last_name__istartswith',
        'profile__preferred_name__istartswith',
        'username__istartswith',
    ]

    def label_from_instance(self, obj):
        return str(obj.profile)


class CustomPostmanUserField(BasicCommaSeparatedUserField):
    """
    Postname field that works with ModelSelect2MultipleWidget
    postman needs a comma seperated string of user.id
    This assumes:
        POSTMAN_NAME_USER_AS = 'id'
    """

    widget = UserCustomTitleWidget

    def clean(self, value):
        """Convert user.id list into comma seperated string"""
        user_ids_comma_seperated_str = ",".join(map(str, value))
        return super().clean(user_ids_comma_seperated_str)


class HackerspaceWriteForm(WriteForm):

    @staticmethod
    def message_exchange_filter(sender, recipient, recipients_list):
        if config.hs_message_teachers_only and not sender.is_staff and not recipient.is_staff:
            return 'Students may only message teachers. Sorry!'

        return None  # comms ok between these two people

    recipients = CustomPostmanUserField()
    exchange_filter = message_exchange_filter
    files = RestrictedFileFormField(
        required=False,
        max_upload_size=16777216,
        widget=forms.ClearableFileInput(attrs={'multiple': True}),
        label="Attach files",
        help_text="Hold Ctrl to select multiple files, 16MB limit per file"
    )

    def __init__(self, *args, **kwargs):
        sender = kwargs.get('sender', None)

        super().__init__(*args, **kwargs)

        if config.hs_message_teachers_only and sender and not sender.is_staff:
            # only allow students to send to staff
            self.fields['recipients'].widget.queryset = User.objects.filter(is_staff=True)

        self.fields['body'].widget = SummernoteInplaceWidget()

    def clean_body(self):
        text = self.cleaned_data['body']
        return clean_html(text)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        files = self.cleaned_data.get('files')
        print("INSTANCE")
        print(self.instance)
        print(self.cleaned_data)
        print(files)


class HackerspaceWriteView(WriteView):
    """
    WriteView modifictions:
    - django-select2 for recipient selection
    - django-summernote for body
    - handles file uploads via django-attachments
    """
    form_classes = (HackerspaceWriteForm, AnonymousWriteForm)

    def post(self, request, *args, **kwargs):
        # https://docs.djangoproject.com/en/2.2/topics/http/file-uploads/
        form_class = self.get_form_class()
        form = self.get_form(form_class)

        # we'll need these later after the message is saved
        print(request.FILES.getlist('files'))

        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if 'sender' not in kwargs:
            kwargs['sender'] = self.request.user  # need for select2 queryset filter
        return kwargs
