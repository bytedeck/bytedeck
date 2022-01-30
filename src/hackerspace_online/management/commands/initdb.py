from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connections, transaction
from django.db.models.signals import post_save
from django.db.utils import OperationalError

from django_tenants.models import TenantMixin
from django_tenants.signals import post_schema_sync

from tenant.models import Tenant
from tenant.signals import initialize_tenant_with_data, tenant_save_callback

User = get_user_model()


class Command(BaseCommand):

    help = 'Used to initialize the database, creates a Sites object, creates the public Tenant object, and creates a superuser for the public schema/tenant. \
        This should only be run on a fresh db'

    @transaction.atomic
    def handle(self, *args, **options):

        # Check if we are connected to the database
        try:
            connections['default'].cursor()
        except OperationalError:
            self.stdout.write("I can't connect to the database.  Are you sure it's running?")
            self.stdout.write("Try `docker-compose up -d db` then give it a few seconds to boot up")
            self.stdout.write(self.style.NOTICE("Bailing..."))
            return

        self.stdout.write('\n** Running initial migrations on the public schema...')
        call_command("migrate_schemas", "--shared")

        # Create super user on the public schema ###############################################
        self.stdout.write('\n** Creating superuser...')
        if User.objects.filter(username=settings.DEFAULT_SUPERUSER_USERNAME).exists():
            self.stdout.write(self.style.NOTICE(f'A superuser with username `{settings.DEFAULT_SUPERUSER_USERNAME}` already exists'))
            self.stdout.write(self.style.NOTICE("Bailing..."))
            return

        User.objects.create_superuser(
            username=settings.DEFAULT_SUPERUSER_USERNAME,
            email=settings.DEFAULT_SUPERUSER_EMAIL,
            password=settings.DEFAULT_SUPERUSER_PASSWORD
        )

        self.stdout.write("Superuser")
        self.stdout.write(f" username: {settings.DEFAULT_SUPERUSER_USERNAME}")
        self.stdout.write(f" password: {settings.DEFAULT_SUPERUSER_PASSWORD}")
        self.stdout.write(f" email: {settings.DEFAULT_SUPERUSER_EMAIL}")

        # Create the `public` Tenant object ###############################################

        # Disconnect from the post_schema_sync when creating public tenant since this will
        # be the `public` schema and we don't want to initialize tenant specific data
        post_schema_sync.disconnect(initialize_tenant_with_data, sender=TenantMixin)

        # Also disconnect from the tenant_save_callback so it wont create unnecessary domains
        post_save.disconnect(tenant_save_callback, sender=Tenant)

        self.stdout.write(self.style.SUCCESS('\n** Creating `public` Tenant object...'))
        public_tenant, created = Tenant.objects.get_or_create(
            schema_name='public',
            name='public'
        )

        public_tenant.domains.create(
            domain=settings.ROOT_DOMAIN,
            is_primary=True
        )

        if not created:
            self.stdout.write(self.style.NOTICE('\nA schema with the name `public` already existed.  A new one was not created.'))

        self.stdout.write(self.style.SUCCESS('\nPublic Tenant object'))
        self.stdout.write(f" tenant.domain_url: {public_tenant.get_primary_domain().domain}")
        self.stdout.write(f" tenant.schema_name: {public_tenant.schema_name}")
        self.stdout.write(f" tenant.name: {public_tenant.name}")

        self.stdout.write(self.style.SUCCESS('\n** Updating Sites object...'))
        site = Site.objects.first()
        site.domain = settings.ROOT_DOMAIN
        site.name = settings.ROOT_DOMAIN[:45]  # Can be too long if using an AWS public DNS
        site.save()

        self.stdout.write("\nSites object")
        self.stdout.write(f" site.domain: {site.domain}")
        self.stdout.write(f" site.name: {site.name}")
        self.stdout.write(f" site.id: {site.id}")

        # Connect again
        post_schema_sync.connect(initialize_tenant_with_data, sender=TenantMixin)
        post_save.connect(tenant_save_callback, sender=Tenant)
