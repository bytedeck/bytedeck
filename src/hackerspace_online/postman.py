# import re

# from djconfig import config
from django.contrib.auth import get_user_model

from postman.forms import WriteForm
from postman.fields import BasicCommaSeparatedUserField
from django_select2.forms import ModelSelect2MultipleWidget

from djconfig import config
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
        POSTMAN_SHOW_USER_AS = lambda u: u.id
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

    def __init__(self, *args, **kwargs):
        sender = kwargs.get('sender', None)
        print("KWARGS:", kwargs)

        super().__init__(*args, **kwargs)

        if config.hs_message_teachers_only and sender and not sender.is_staff:
            # only allow students to send to staff
            self.fields['recipients'].queryset = User.objects.filter(is_staff=True)
