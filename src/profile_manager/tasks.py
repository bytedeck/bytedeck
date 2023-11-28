from hackerspace_online.celery import app

from django_tenants.utils import tenant_context, get_tenant_model
from .models import Profile


@app.task(name="profile_manager.tasks.invalidate_profile_xp_cache_in_all_schemas")
def invalidate_profile_xp_cache_in_all_schemas():
    """
    Dispatcher task that calls invalidate_xp_cache_on_schema for each schema
    """
    for tenant in get_tenant_model().objects.exclude(schema_name="public"):
        with tenant_context(tenant):
            invalidate_profile_xp_cache_on_schema.delay()


@app.task(name="profile_manager.tasks.invalidate_profile_xp_cache_on_schema")
def invalidate_profile_xp_cache_on_schema():
    """
    Invalidate xp cache of all profiles for a schema to recalculate xp
    """

    profiles_qs = Profile.objects.all_for_active_semester()
    for profile in profiles_qs:
        profile.xp_invalidate_cache()
