from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.models import Case, F, Value, When

from tenant_schemas.utils import schema_context

from tenant.models import Tenant


def group_by_sql(schema, table, column):
    sql = f"""
        SELECT {column} FROM {schema}.{table}
        GROUP BY {column}
    """
    print(sql)
    return sql


class Command(BaseCommand):

    help = "One time management command execution to update tenant's content_type_ids"

    def handle(self, *args, **options):

        has_gfk_models = [
            {
                'app_label': 'comments',
                'model': 'comment',
                'col': 'target_content_type_id'
            },
            {
                'app_label': 'notifications',
                'model': 'notification',
                'col': 'target_content_type_id'
            },
            {
                'app_label': 'notifications',
                'model': 'notification',
                'col': 'action_content_type_id',
            },
            {
                'app_label': 'prerequisites',
                'model': 'prereq',
                'col': 'parent_content_type_id',
            },
            {
                'app_label': 'prerequisites',
                'model': 'prereq',
                'col': 'prereq_content_type_id',
            },
            {
                'app_label': 'prerequisites',
                'model': 'prereq',
                'col': 'or_prereq_content_type_id',
            },
            {
                'app_label': 'djcytoscape',
                'model': 'cytoscape',
                'col': 'initial_content_type_id',
            }
        ]

        for tenant in Tenant.objects.exclude(schema_name='public'):
            for has_gfk_model in has_gfk_models:
                app_label, model, col = has_gfk_model.values()

                with connection.cursor() as cursor:
                    cursor.execute(group_by_sql(
                        schema=tenant.schema_name,
                        table=f"{app_label}_{model}",
                        column=col))

                    # Remove null ids
                    tenant_target_content_type_ids = [_id[0] for _id in cursor.fetchall() if _id[0]]
                    # print(tenant_target_content_type_ids)

                    # tenant content_type_id : public content_type_id
                    ct_ids_map = {}
                    for ct_id in tenant_target_content_type_ids:
                        # Get what kinf of model the given ID is
                        with schema_context(tenant.schema_name):
                            ct_tenant_app = ContentType.objects.get(id=ct_id)
                        # ... then fetch its equivalent in the public tenant
                        try:
                            ct_public = ContentType.objects.get(app_label=ct_tenant_app.app_label, model=ct_tenant_app.model)
                            ct_ids_map[ct_id] = ct_public.id
                        except ContentType.DoesNotExist:
                            # Just skip the apps that aren't installed anymore
                            print(f'{ct_tenant_app} has been removed from settings.APPS')
                            continue

                    Model = apps.get_model(app_label, model)
                    with schema_context(tenant.schema_name):
                        # Using CASE..WHEN is much faster compared to bulk_update in this case
                        # https://docs.djangoproject.com/en/dev/ref/models/conditional-expressions/#conditional-update
                        whens = []

                        for tenant_ct_id, public_ct_id in ct_ids_map.items():
                            # Build query
                            # When(target_content_type_id={tenant_ct_id}, then=Value({public_ct_id}))
                            when = {
                                col: tenant_ct_id,
                                'then': Value(public_ct_id),
                            }
                            whens.append(When(**when))

                        # If we are currently updating comments, the query would look something like
                        # Comment.objects.update(
                        #   target_content_type_id=Case(
                        #       When(target_content_type_id=17, then=Value(25)),
                        #       When(...),
                        #       default=F(target_content_type_id)))
                        # )
                        case_when = {
                            col: Case(*whens, default=F(col)),
                        }

                        # Filter out the queryset so we don't bother updating other target ids
                        qs = Model.objects.filter(**{f'{col}__in': ct_ids_map.keys()})
                        qs.update(**case_when)
                        print(connection.queries)

            # Drop the table so it only uses public.django_content_type
            drop_contenttype_table = f"DROP TABLE IF EXISTS {tenant.schema_name}.django_content_type CASCADE"
            with connection.cursor() as cursor:
                cursor.execute(drop_contenttype_table)
