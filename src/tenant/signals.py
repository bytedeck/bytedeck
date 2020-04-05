from django.db import connection
from django.contrib.auth.models import User


def create_superuser(sender, tenant, **kwargs):
    print("Creating default super user of the tenant %s - %s." % (tenant.schema_name, tenant.domain_url))
    connection.set_tenant(tenant)
    User.objects.create_superuser(username='admin', email='admin@%s.com' % tenant.schema_name, password='admin1234')
