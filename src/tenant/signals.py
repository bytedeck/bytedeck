from django.db import connection
from django.conf import settings
from django.contrib.auth.models import User

from .initialization import load_initial_tenant_data


def create_superuser(sender, tenant, **kwargs):
    # print("Creating default super user of the tenant %s - %s." % (tenant.schema_name, tenant.domain_url))
    connection.set_tenant(tenant)
    User.objects.create_superuser(username=settings.TENANT_DEFAULT_SUPERUSER_USERNAME, email='admin@%s.com' %
                                  tenant.schema_name, password=settings.TENANT_DEFAULT_SUPERUSER_PASSWORD)


def initialize_tenant_with_data(sender, tenant, **kwargs):
    connection.set_tenant(tenant)
    load_initial_tenant_data()
