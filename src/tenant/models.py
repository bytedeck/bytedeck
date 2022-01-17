import re

from django.core.exceptions import ValidationError
from django.db import models

from tenant_schemas.models import TenantMixin


def check_tenant_name(name):
    """ A tenant's name is used for both the schema_name and as the subdomain in the 
    tenant's domain_url field, so {name} it must be valid for a schema and a url.
    """
    if not re.match(re.compile(r'^[a-z]'), name):
        raise ValidationError("The name must begin with a lower-case letter.")

    if re.search(re.compile(r'[A-Z]'), name):
        raise ValidationError("The name cannot contain capital letters.")

    if re.search(re.compile(r'-$'), name):
        raise ValidationError("The name cannot end in a dash.")

    if re.search(re.compile(r'--'), name):
        raise ValidationError("The name cannot have two consecutive dashes.")

    if not re.match(re.compile(r'^([a-z][a-z0-9]*(\-?[a-z0-9]+)*)$'), name):
        raise ValidationError("Invalid string used for the tenant name.")


class Tenant(TenantMixin):
    # tenant = Tenant(domain_url='test.localhost', schema_name='test', name='Test')
    name = models.CharField(
        max_length=62,  # max length of a postgres schema name is 62
        unique=True, 
        validators=[check_tenant_name],
        help_text="The name of your deck, for example the name `example` would give you the site: `example.bytedeck.com` \n\
        The name may only include lowercase letters, numbers, and dashes. \
        It must start with a letter, and may not end in a dash nor include consecutive dashes"
    )
    desc = models.TextField(blank=True)
    created_on = models.DateField(auto_now_add=True)
    owner_full_name = models.CharField(
        max_length=255, blank=True, null=True, 
        help_text="The owner of this deck."
    )
    owner_email = models.EmailField(null=True, blank=True)
    max_active_users = models.SmallIntegerField(
        default=40,
        help_text="The maximum number of users that can be active on this deck; -1 = unlimited."
    )
    max_quests = models.SmallIntegerField(
        default=100,
        help_text="The maximum number of quests that can be active on this deck (archived quests are considered inactive); -1 = unlimited."
    )
    trial_end_date = models.DateField(
        blank=True, null=True,
        help_text="The date when the trial period ends. Blank or a date in the past means the deck is not in trial mode."
    )
    paid_until = models.DateField(
        blank=True, null=True,
        help_text="If the deck is not in trial mode, then the deck will become inaccessable to students after this date."
    )

    def __str__(self):
        return '%s - %s' % (self.schema_name, self.domain_url)  

    def get_root_url(self):
        """ 
        Returns the root url of the tenant in the form of:
        scheme://[subdomain.]domain[.topleveldomain][:port]

        Port 8000 is hard coded for development

        Examples:
        - "hackerspace.bytedeck.com"
        - "hackerspace.localhost:8000"
        """
        if 'localhost' in self.domain_url:  # Development
            return "http://{}:8000".format(self.domain_url)
        else:  # Production
            return "https://{}".format(self.domain_url)

    @classmethod
    def get(cls):
        """ Used to access the Tenant object for the current connection """
        from django.db import connection
        return Tenant.objects.get(schema_name=connection.schema_name)
