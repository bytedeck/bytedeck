# Project customizations for django-postman

from django import forms
from django.contrib.auth import get_user_model

from postman.forms import WriteForm, BaseWriteForm, AnonymousWriteForm
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
        self.messages = []  # need this to hack the WriteForm save method, see below

    def clean_body(self):
        text = self.cleaned_data['body']
        return clean_html(text)

    def save(self, recipient=None, parent=None, auto_moderators=[]):
        """
        Need to override WriteForm's save method so that it returns the messages. 
        Otherwise I can't get the message objects so that I can create attachments to the message

        This should match the original as close as possible, except return a list of message objects
        https://bitbucket.org/psam/django-postman/src/default/postman/forms.py
        """

        recipients = self.cleaned_data.get('recipients', [])
        if parent and not parent.thread_id:  # at the very first reply, make it a conversation
            parent.thread = parent
            parent.save()
            # but delay the setting of parent.replied_at to the moderation step
        if parent:
            self.instance.parent = parent
            self.instance.thread_id = parent.thread_id
        initial_moderation = self.instance.get_moderation()
        initial_dates = self.instance.get_dates()
        initial_status = self.instance.moderation_status
        if recipient:
            if isinstance(recipient, get_user_model()) and recipient in recipients:
                recipients.remove(recipient)
            recipients.insert(0, recipient)
        is_successful = True
        for r in recipients:
            if isinstance(r, get_user_model()):
                self.instance.recipient = r
            else:
                self.instance.recipient = None
                self.instance.email = r
            self.instance.pk = None  # force_insert=True is not accessible from here
            self.instance.auto_moderate(auto_moderators)
            self.instance.clean_moderation(initial_status)
            self.instance.clean_for_visitor()
            m = super(BaseWriteForm, self).save()
            self.messages.append(m)  # CHANGE ############################
            if self.instance.is_rejected():
                is_successful = False
            self.instance.update_parent(initial_status)
            self.instance.notify_users(initial_status, self.site)
            # some resets for next reuse
            if not isinstance(r, get_user_model()):
                self.instance.email = ''
            self.instance.set_moderation(*initial_moderation)
            self.instance.set_dates(*initial_dates)
        return is_successful


class HackerspaceWriteView(WriteView):
    """
    WriteView modifictions:
    - django-select2 for recipient selection
    - django-summernote for body
    - handles file uploads via django-attachments
    """
    form_classes = (HackerspaceWriteForm, AnonymousWriteForm)

    # def post(self, request, *args, **kwargs):
    #     # https://docs.djangoproject.com/en/2.2/topics/http/file-uploads/
    #     form_class = self.get_form_class()
    #     form = self.get_form(form_class)

    #     # we'll need these later after the message is saved

    #     if form.is_valid():
    #         form.save()
    #         files = request.FILES.getlist('files')
    #         for f in files:
    #             for message in form.messages:
    #                 Attachment(
    #                     content_object=message,
    #                     creator=request.user,
    #                     attachment_file=f,
    #                 ).save()
    #         return self.form_valid(form)

    #     else:
    #         return self.form_invalid(form)

    def form_valid(self, form):
        """ Save the attachments """
        response = super().form_valid(form)
        files = self.request.FILES.getlist('files')
        for f in files:
            for message in form.messages:
                Attachment(
                    content_object=message,
                    creator=self.request.user,
                    attachment_file=f,
                ).save()

        return response

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if 'sender' not in kwargs:
            kwargs['sender'] = self.request.user  # need for select2 queryset filter
        return kwargs
