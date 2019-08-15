# import re

# from djconfig import config
from django.contrib.auth import get_user_model

from postman.forms import WriteForm
from postman.fields import BasicCommaSeparatedUserField
from django_select2.forms import ModelSelect2MultipleWidget
# from django_summernote.widgets import SummernoteInplaceWidget


User = get_user_model()


#################################
#
# FORMS
#
#################################

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


def message_exchange_filter(sender, recipient, recipients_list):
    print("FILTERING!!!")
    if not sender.is_staff and not recipient.is_staff:
        return 'Students may only message teachers. Sorry!'

    return None  # comms ok between these two people


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

        return super(BasicCommaSeparatedUserField, self).clean(user_ids_comma_seperated_str)


class HackerspaceWriteForm(WriteForm):

    # @staticmethod
    # def exchange_filter(sender, recipient, recipients_list):
    #     """At least one of the users has to be a staff member

    #        this method is messed up.  sender and recipient are both supposed to be Users
    #        according to docs, but recipients is a str value of the user.id
    #     """

    #     print("EXCHANGE FILTER")
    #     print("SENDER TYPE: ", type(sender))
    #     print("Sender ID:", sender.id)
    #     print("RCPT TYPE: ", type(recipient))
    #     print(recipient)

    #     # sending_user = get_user_name(sender)
    #     # recipient_user = get_user_name(recipient)

    #     # print(sending_user, type(sending_user))
    #     sending_user = User.objects.get(pk=sender.id)
    #     recipient_user = User.objects.get(pk=recipient)

    #     # sender and recipient are SimpleLazyObjects
    #     sending_user = User.objects.get(username=sender)
    #     if not sending_user.is_staff and not recipient_user.is_staff:
    #         return 'Students may only message teachers. Sorry!'
    #     return None  # comms ok between these two people

    recipients = CustomPostmanUserField()

    def __init__(self, *args, **kwargs):
        super(WriteForm, self).__init__(*args, **kwargs)
        sender = kwargs.get('sender', None)

        print("FORM INIT")
        print("SNEDER")
        print(sender)

        print("KWARGS:", kwargs)
        for arg in kwargs:
            print(arg)

        # if not sender.is_staff:
        #     self.fields['recipients'].queryset = User.objects.filter(is_staff=True)
