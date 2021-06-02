from django.apps import apps
# from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.models.base import Model
from django.db.models.expressions import Value
from django.db.models.fields import CharField, Field, TextField
from django.db.models.functions import Replace
# from django.db.models import Case, F, Value, When

from tenant_schemas.utils import schema_context

from tenant.models import Tenant


class Command(BaseCommand):
    help = 'Within the specified tenant (or "all") replace all occurances of text="replace-me" with replacement="" '

    # app name, model name as dictionary key and field name as values
    apps_to_check = ["quest_manager"]
    field_types_to_check = [CharField, TextField]

    def add_arguments(self, parser):
        parser.add_argument('tenants', nargs='+', help='A space separated list of tenants, or all')

    def handle(self, *args, **options):

        tenant_names = options['tenants']

        if tenant_names[0].lower() == "all":
            tenants = Tenant.objects.exclude(name="public")
        else:
            tenants = Tenant.objects.filter(name__in=tenant_names)

        for tenant in tenants:
            print(f"Running replacement on tenant: {tenant}")

            with schema_context(tenant.schema_name):
                print("Schema: ", connection.schema_name)

                # loop through the listed apps
                for app_label in self.apps_to_check:
                    app_config = apps.get_app_config(app_label)
                    # print("App: ", app_config)

                    # loop through all models in the app
                    model: Model
                    for model in app_config.get_models():
                        # print("Model: ", model)

                        # loop through all fields in the model
                        field: Field
                        for field in model._meta.get_fields():
                            if type(field) in self.field_types_to_check:
                                # https://docs.djangoproject.com/en/2.2/ref/models/database-functions/#replace
                                model.objects.update(**{field.name: Replace(field.name, Value("https://hackerspace.sd72.bc.ca/"), Value("/"))})
                                # print("Updated: ", num_updates)
                                print("Field: ", field)

        else:  # no tenants found to loop through
            print(f"No tenants recognized in the list provided: {tenant_names}")
