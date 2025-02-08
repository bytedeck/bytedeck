from django.apps import apps
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context
from tenant.models import Tenant


class Command(BaseCommand):
    """ Because model.save() does not call full_clean() there might be a couple of integrity issues because of that.
    This command can loop through every single tenant (unless specified) and call full_clean() to check for any issues.
    See "https://github.com/bytedeck/bytedeck/issues/1634" for more details.

    format of full_clean validation error
        # Exception found on cleaning "<Object Name>" (<Model Name>) of type <Error Name>: <Error Log>

    examples of full_clean validation errors:
        (deprecated problem)
        "Profile" object called "admin" with a "custom_profile_field" validation error
        - Exception found on cleaning "admin" (Profile) of type ValidationError: {'grad_year': ['This field cannot be blank.']}

        "CytoElement" object called "5: Badge: ByteDeck Proficiency (2)" with "href" validation error
        - Exception found on cleaning "5: Badge: ByteDeck Proficiency (2)" (CytoElement) of type ValidationError:
            {'href': ['URL is missing a trailing slash.']}

    """
    # colors from https://stackoverflow.com/a/287944
    EXCEPTION_C = '\033[91m'
    MODEL_C = '\033[94m'
    OBJECT_C = '\033[96m'
    TENANT_C = '\033[92m'
    END_C = '\033[0m'

    LOCAL_APPS = (
        'quest_manager',
        'profile_manager',
        'announcements',
        'comments',
        'notifications',
        'courses',
        'prerequisites',
        'badges',
        'djcytoscape',
        'portfolios',
        'utilities',
        'siteconfig',
        'tags',
        'library',
    )

    help = ("Loops through a list of tenants (all by default), and validates each object in the database using full_clean()."
            "Any validation errors are printed to the console.")

    def add_arguments(self, parser):

        # optional arguments
        parser.add_argument(
            '--tenants', action='store', nargs='+',
            help='A space separated list of tenant schemas. Specifies which tenant to loop through. Defaults to all tenants'
        )

    def handle(self, *args, **options):
        tenant_names = options.get('tenants')

        tenants = Tenant.objects.filter(schema_name__in=tenant_names) if tenant_names else Tenant.objects.all()

        # querying models from these gives a relation error
        tenants = tenants.exclude(schema_name__in=['public'])

        # loop through all tenants
        for tenant in tenants:
            # loop through all models inside tenant
            with schema_context(tenant.schema_name):
                print(f"* TENANT: {tenant}")
                # loop through each model
                for app_name in self.LOCAL_APPS:
                    print(f"*** APP: {app_name}")
                    for model in apps.get_app_config(app_name).get_models():
                        print(f"***** MODEL: {model}")
                        # full clean each object in model
                        for object_ in model.objects.all().iterator(chunk_size=100):
                            try:
                                object_.full_clean()
                                # Since we don't actually fix errors here, there is no point in saving.
                                # object_.save()
                            except ValidationError as e:
                                exception_string = self.EXCEPTION_C + "Exception" + self.END_C
                                tenant_string = self.TENANT_C + str(tenant.schema_name) + self.END_C
                                object_string = self.OBJECT_C + str(object_) + self.END_C
                                model_string = self.MODEL_C + model.__name__ + self.END_C
                                error_type = self.EXCEPTION_C + type(e).__name__ + self.END_C

                                # Exception found on <Tenant> cleaning "<Object Name>" (<Model Name>) of type <Error Name>: <Error Log>
                                print(
                                    f'{exception_string} found on {tenant_string} cleaning "{object_string}" ({model_string}) of type {error_type}:',
                                    e
                                )
