from allauth.account.adapter import DefaultAccountAdapter


class CustomAccountAdapter(DefaultAccountAdapter):

    def clean_username(self, username, shallow=False):
        username = super().clean_username(username, shallow)
        return username.lower()
