from django.db import connection

from .initialization import load_initial_tenant_data


def initialize_tenant_with_data(sender, tenant, **kwargs):
    connection.set_tenant(tenant)
    load_initial_tenant_data()
