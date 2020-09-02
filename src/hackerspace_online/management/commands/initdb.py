from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand
from tenant.models import Tenant
from tenant.signals import initialize_tenant_with_data
from tenant_schemas.models import TenantMixin
from tenant_schemas.signals import post_schema_sync

User = get_user_model()

SUCCESS_MESSAGE = """
Successfully created superuser account!
Username: {username}
Password: {password}
"""


class Command(BaseCommand):

    help = 'Used to initialize admin, public tenant, and sites model. Should only be ran on a fresh db'

    def handle(self, *args, **options):

        if User.objects.filter(username=settings.DEFAULT_SUPERUSER_USERNAME).exists():
            print('A superuser with username `{username}` already exists'.format(username=settings.DEFAULT_SUPERUSER_USERNAME))
            print('Will not proceed with initializing the database.')
            return

        # Disconnect from the post_schema_sync when creating public tenant
        # since this will be the `public` schema and we don't want to initialize
        # tenant specific data
        post_schema_sync.disconnect(initialize_tenant_with_data, sender=TenantMixin)

        User.objects.create_superuser(username=settings.DEFAULT_SUPERUSER_USERNAME,
                                      email=settings.DEFAULT_SUPERUSER_EMAIL,
                                      password=settings.DEFAULT_SUPERUSER_PASSWORD)

        print(SUCCESS_MESSAGE.format(username=settings.DEFAULT_SUPERUSER_USERNAME,
                                     password=settings.DEFAULT_SUPERUSER_PASSWORD))

        print('Creating public tenant ...')
        Tenant.objects.get_or_create(domain_url='localhost',
                                     schema_name='public',
                                     name='public')

        print('Updating sites ...')
        site = Site.objects.first()
        site.domain = 'localhost'
        site.name = 'localhost'
        site.save()

        # Connect again
        post_schema_sync.connect(initialize_tenant_with_data, sender=TenantMixin)
