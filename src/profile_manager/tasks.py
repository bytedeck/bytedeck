import logging

from hackerspace_online.celery import app

from django_tenants.utils import tenant_context, get_tenant_model
from .models import Profile

logger = logging.getLogger(__name__)


@app.task(name="profile_manager.tasks.invalidate_profile_xp_cache_in_all_schemas")
def invalidate_profile_xp_cache_in_all_schemas():
    """
    Dispatcher task that calls invalidate_xp_cache_on_schema for each schema
    """
    for tenant in get_tenant_model().objects.exclude(schema_name="public"):
        with tenant_context(tenant):
            invalidate_profile_xp_cache_on_schema.apply_async(queue='default')

    return "Scheduled invalidate_profile_xp_cache_on_schema for all schemas"


@app.task(name="profile_manager.tasks.invalidate_profile_xp_cache_on_schema")
def invalidate_profile_xp_cache_on_schema():
    """
    Invalidate xp cache of all profiles for a schema to recalculate xp.

    Each profile is invalidated independently: one profile that raises (e.g. a
    DB error while saving) is logged and skipped rather than aborting the whole
    schema's refresh, so a single bad row can't leave every later profile stale.
    """
    profiles_qs = Profile.objects.all_for_active_semester()

    invalidated = 0
    failed = 0
    for profile in profiles_qs:
        try:
            profile.xp_invalidate_cache()
            invalidated += 1
        except Exception:
            # Log with traceback and carry on with the remaining profiles. The
            # celery task_failure alert only fires on an uncaught exception, so
            # surface it here instead of losing it (and the rest of the run).
            failed += 1
            logger.exception("xp_invalidate_cache failed for profile id=%s (user=%s)", profile.pk, profile.user_id)

    if failed:
        return f"Invalidated {invalidated} profiles; {failed} failed (see logs)."
    return f"Successfully invalidated {invalidated} profiles."
