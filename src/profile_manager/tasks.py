from hackerspace_online.celery import app

from django_tenants.utils import tenant_context, get_tenant_model
from .models import Profile


@app.task(name="profile_manager.tasks.invalidate_profile_cache_in_all_schemas")
def invalidate_profile_cache_in_all_schemas():
    """
    Recalculate the xp of all profiles for all schemas
    """
    for tenant in get_tenant_model().objects.exclude(schema_name="public"):
        with tenant_context(tenant):
            invalidate_profile_cache_on_schema.delay()


@app.task(name="profile_manager.tasks.invalidate_profile_cache_on_schema")
def invalidate_profile_cache_on_schema():
    """
    Recalculate the xp of all profiles for a schema
    """

    profiles_qs = Profile.objects.all_for_active_semester()
    for profile in profiles_qs:
        profile.xp_invalidate_cache()
