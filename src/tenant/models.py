import re

from django.core.exceptions import ValidationError
from django.db import models
from django_tenants.models import TenantMixin


def check_tenant_name(name):
    if not re.match(re.compile(r'^([a-zA-Z][a-zA-Z0-9]*(\-?[a-zA-Z0-9]+)*){,62}$'), name):
        raise ValidationError("Invalid string used for the tenant name.")


class Tenant(TenantMixin):
    # tenant = Tenant(domain_url='test.localhost', schema_name='test', name='Test')
    name = models.CharField(max_length=100, unique=True, validators=[check_tenant_name])
    desc = models.TextField(blank=True)
    created_on = models.DateField(auto_now_add=True)

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
