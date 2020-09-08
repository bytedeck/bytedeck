from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connections
from django.db.utils import OperationalError

from tenant.models import Tenant
from tenant.signals import initialize_tenant_with_data
from tenant_schemas.models import TenantMixin
from tenant_schemas.signals import post_schema_sync

User = get_user_model()


class Command(BaseCommand):

    help = 'Used to initialize the database, creates a Sites object, creates the public Tenant object, and creates a superuser for the public schema/tenant. \
        This should only be run on a fresh db'

    def handle(self, *args, **options):

        # Check if we are connected to the database
        try:
            connections['default'].cursor()
        except OperationalError:
            print("I can't connect to the database.  Are you sure it's running?")
            print("Try `docker-compose up -d db` then give it a few seconds to boot up")
            print("Bailing...")
            return

        print('\n** Running initial migrations on the public schema...')
        call_command("migrate_schemas", "--shared")

        # Create super user on the public schema ###############################################
        print('\n** Creating superuser...')
        if User.objects.filter(username=settings.DEFAULT_SUPERUSER_USERNAME).exists():
            print('A superuser with username `{username}` already exists'.format(username=settings.DEFAULT_SUPERUSER_USERNAME))
            print('Bailing...')
            return

        User.objects.create_superuser(
            username=settings.DEFAULT_SUPERUSER_USERNAME,
            email=settings.DEFAULT_SUPERUSER_EMAIL,
            password=settings.DEFAULT_SUPERUSER_PASSWORD
        )

        print("Superuser")
        print(f" username: {settings.DEFAULT_SUPERUSER_USERNAME}")
        print(f" password: {settings.DEFAULT_SUPERUSER_PASSWORD}")
        print(f" email: {settings.DEFAULT_SUPERUSER_EMAIL}")

        # Create the `public` Tenant object ###############################################

        # Disconnect from the post_schema_sync when creating public tenant since this will 
        # be the `public` schema and we don't want to initialize tenant specific data
        post_schema_sync.disconnect(initialize_tenant_with_data, sender=TenantMixin)

        print('\n** Creating `public` Tenant object...')
        public_tenant, created = Tenant.objects.get_or_create(
            domain_url=settings.ROOT_DOMAIN,
            schema_name='public',
            name='public'
        )

        if not created:
            print("\nA schema with the name `public` already existed.  A new one was not created.")
        print("\nPublic Tenant object")
        print(f" tenant.domain_url: {public_tenant.domain_url}")
        print(f" tenant.schema_name: {public_tenant.schema_name}")
        print(f" tenant.name: {public_tenant.name}")
                    
        print('\n** Updating Sites object...')
        site = Site.objects.first()
        site.domain = settings.ROOT_DOMAIN
        site.name = settings.ROOT_DOMAIN[:45]  # Can be too long if using an AWS public DNS
        site.save()

        print("\nSites object")
        print(f" site.domain: {site.domain}")
        print(f" site.name: {site.name}")
        print(f" site.id: {site.id}")

        # Connect again
        post_schema_sync.connect(initialize_tenant_with_data, sender=TenantMixin)
