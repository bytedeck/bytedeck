import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management import call_command
from django.db import connection
from django.template.loader import get_template

from django_tenants.utils import get_public_schema_name, get_tenant_model, schema_context, tenant_context

from hackerspace_online.celery import app
from library.utils import get_library_schema_name
from utilities.html import textify

logger = logging.getLogger(__name__)


@app.task(name="tenant.tasks.send_email_message")
def send_email_message(subject, message, recipient_list, **kwargs):
    """
    Simple task that's intended to handle mass emailing.
    """
    # load and render base template with message content
    msg = get_template("admin/tenant/email/message.txt").render(context={
        "message": message,
    })
    # sending a text and HTML content combination
    email = EmailMultiAlternatives(
        subject,
        body=textify(msg),  # convert msg to plain text, using textify utility
        to=[settings.DEFAULT_FROM_EMAIL],
        bcc=recipient_list,
    )
    email.attach_alternative(msg, "text/html")
    email.send()


@app.task(name="tenant.tasks.clear_expired_sessions_in_all_schemas")
def clear_expired_sessions_in_all_schemas():
    """Run Django's `clearsessions` in the public schema and every tenant schema.

    Sessions are database-backed and `django.contrib.sessions` is in both
    SHARED_APPS and TENANT_APPS, so a django_session table exists per schema and
    each one accumulates expired rows (8-week SESSION_COOKIE_AGE) until purged.
    Nothing else cleans them up, so this runs daily via celery beat. The purge
    is a single DELETE per schema, so looping inline is fine even with many
    tenants.

    Takes no arguments and returns None; it is invoked by celery beat, which
    ignores the return value.
    """
    schema_names = ['public'] + list(
        get_tenant_model().objects.exclude(schema_name='public').values_list('schema_name', flat=True)
    )
    for schema_name in schema_names:
        with schema_context(schema_name):
            call_command('clearsessions')


@app.task(name="tenant.tasks.daily_deck_status_check_for_all_tenants")
def daily_deck_status_check_for_all_tenants():
    """Dispatcher: fan a per-schema `deck_status_check` out to every billable deck.

    Runs daily via celery beat. Excludes the public schema (not a deck) and the
    shared-library schema (not billable -- the epic #1729 rule for all lifecycle
    machinery). tenant-schemas-celery stamps each apply_async with the active
    connection's schema, so entering tenant_context() before dispatching is what
    routes each subtask to its own schema.

    Takes no arguments; returns a short summary string for the worker log
    (celery beat ignores it).
    """
    tenants = get_tenant_model().objects.exclude(
        schema_name__in=[get_public_schema_name(), get_library_schema_name()]
    )
    count = 0
    for tenant in tenants:
        with tenant_context(tenant):
            deck_status_check.apply_async(queue='default')
        count += 1
    return f"Scheduled tenant.tasks.deck_status_check for {count} deck(s)"


@app.task(name="tenant.tasks.poll_release_announcement")
def poll_release_announcement():
    """Notify every deck's staff when a new ByteDeck release reaches production.

    Runs hourly via celery beat. Queries GitHub for the latest changelog
    announcement (``tenant.github.get_latest_release_announcement``); if it names a
    version newer than any this project has recorded, creates one in-app
    notification per deck for all of that deck's active staff, linking to the
    GitHub announcement, then records the version so it is never re-notified.

    Two safety layers keep a rollout quiet: the task no-ops unless
    ``settings.RELEASE_NOTIFICATIONS_ENABLED`` is on (and a GitHub token is set,
    else the query returns nothing), and the first successful poll only records a
    baseline (no notifications), so the version that shipped before this feature
    existed can't trigger a mass notification. Later polls only ever move forward:
    a version at or below the newest recorded one is recorded silently, never
    re-announced.

    The version bookkeeping lives in the public schema (where ReleaseNotification
    lives); the fan-out enters each deck's schema. Takes no arguments; returns a
    short summary string for the worker log (celery beat ignores it).
    """
    from tenant.github import get_latest_release_announcement, version_key
    from tenant.models import ReleaseNotification

    if not settings.RELEASE_NOTIFICATIONS_ENABLED:
        return "Release notifications disabled; skipped"

    latest = get_latest_release_announcement()
    if latest is None:
        return "No release announcement found; skipped"
    version, url = latest

    with schema_context(get_public_schema_name()):
        if ReleaseNotification.objects.filter(version=version).exists():
            return f"Release {version} already handled; skipped"

        # First poll ever: record a baseline without notifying, so enabling the
        # feature doesn't blast staff about a release they already run.
        if not ReleaseNotification.objects.exists():
            ReleaseNotification.objects.create(version=version, discussion_url=url, notified=False)
            return f"Recorded baseline release {version}; no notification sent"

        # Only move forward: a version at or below the newest recorded one (e.g. an
        # older announcement discussion re-created after a delete) is recorded but
        # not re-announced.
        highest = max((rn.version for rn in ReleaseNotification.objects.all()), key=version_key)
        if version_key(version) <= version_key(highest):
            ReleaseNotification.objects.create(version=version, discussion_url=url, notified=False)
            return f"Release {version} not newer than {highest}; recorded, no notification"

        ReleaseNotification.objects.create(version=version, discussion_url=url, notified=True)

    deck_count, staff_count = notify_all_decks_of_release(version, url)
    return f"Notified {staff_count} staff across {deck_count} deck(s) about release {version}"


def notify_all_decks_of_release(version, url):
    """Create the release notification for every active staff user on every deck.

    Iterates each deck schema (excluding the public and shared-library schemas,
    which aren't decks) and sends a single ``notify.send`` per deck to all of its
    active staff, from the deck's ByteDeck support account (displayed as
    "Bytedeck"). Best-effort per deck: a failure on one deck is logged and skipped
    so the rest still get notified. Returns ``(deck_count, staff_count)``.
    """
    from django.contrib.auth import get_user_model

    from notifications.signals import notify
    from siteconfig.models import SiteConfig

    User = get_user_model()
    tenants = get_tenant_model().objects.exclude(
        schema_name__in=[get_public_schema_name(), get_library_schema_name()]
    )
    deck_count = 0
    staff_count = 0
    for tenant in tenants:
        with tenant_context(tenant):
            try:
                staff = User.objects.filter(is_staff=True, is_active=True).exclude(
                    username=settings.TENANT_DEFAULT_ADMIN_USERNAME
                )
                if not staff.exists():
                    continue
                config = SiteConfig.get()
                sender = User.objects.filter(
                    username=settings.TENANT_DEFAULT_ADMIN_USERNAME, is_active=True
                ).first() or config.deck_ai
                notify.send(
                    sender,
                    recipient=staff.first(),
                    affected_users=list(staff),
                    verb=f'released a new version of ByteDeck ({version}). See',
                    icon="<i class='fa fa-lg fa-fw fa-bullhorn text-info'></i>",
                    url=url,
                    link_text="what's new.",
                )
                deck_count += 1
                staff_count += staff.count()
            # One malformed deck (e.g. a missing SiteConfig on the public tenant if the
            # exclusions ever regressed) must not abort the fan-out to every other deck.
            except Exception as error:  # noqa: BLE001
                logger.warning("Release notification failed for deck '%s': %s", tenant.schema_name, error)
    return deck_count, staff_count


@app.task(name="tenant.tasks.deck_status_check")
def deck_status_check():
    """Refresh the current deck's cached Tenant fields (counts, owner info, last login).

    Dispatched per-schema by daily_deck_status_check_for_all_tenants, making the
    nightly beat run the canonical refresher for the Tenant cached fields -- the
    tenant admin changelist no longer refreshes them on every page load (that
    was an acknowledged N+1 across all decks). Later phases of epic #1729 extend
    this task with the expiry-reminder cadence and limit warnings (#1733).

    After the refresh, three steps run in a deliberate order. First the nightly
    Stripe reconcile (plan §5.3) re-syncs a linked deck's subscription, so a
    renewal Stripe knows about lifts the deck out of suspension before anything
    acts on it. Then a fresh suspension closes the deck's open semester exactly
    once per episode (#1734 redesign B2, see
    tenant.notices.close_semester_on_new_suspension): enforcement, not
    communication, so it is NOT gated by DECK_NOTICES_ENABLED. Then the deck
    reminder engine (#1733) runs: expiry cadence, current-student limit
    warnings, and the suspension notice -- report-only until
    settings.DECK_NOTICES_ENABLED is turned on (see tenant/notices.py).

    Takes no arguments (the schema comes from the task's tenant context);
    returns a short summary string for the worker log.
    """
    import stripe as stripe_lib

    from tenant.notices import close_semester_on_new_suspension, process_deck_notices

    # Defensive mirror of the dispatcher's exclusions: the public and shared-library
    # schemas aren't billable decks and SiteConfig.get() returns None on the public
    # schema, so an ad-hoc invocation (e.g. a shell loop over Tenant.objects.all(),
    # which includes the public tenant) or a mis-routed message must report and
    # bail, not crash mid-refresh (staging ops find, 2026-07-25).
    schema_name = connection.schema_name
    if schema_name in (get_public_schema_name(), get_library_schema_name()):
        return f"'{schema_name}' is not a billable deck schema; skipped"

    tenant = get_tenant_model().objects.get(schema_name=connection.schema_name)
    tenant.update_cached_fields()

    # Nightly Stripe reconcile (plan §5.3, PR 7): webhooks are an optimization,
    # not the source of truth -- re-fetching every linked deck's subscription
    # means a webhook outage shorter than the 30-day grace can never suspend a
    # paying deck. Stripe errors are reported, not raised: the semester close
    # and the notices below must still run. Runs FIRST so a renewal Stripe
    # knows about lifts the deck out of suspension before anything closes
    # (the sync updates this instance in place, so the close reads the
    # post-reconcile billing state; suspension never touches the admin-set
    # cap: #2210).
    stripe_summary = 'not linked'
    if tenant.stripe_subscription_id and settings.STRIPE_SECRET_KEY:
        from tenant.billing import _sync_deck_from_subscription_id
        try:
            stripe_summary = _sync_deck_from_subscription_id(tenant, tenant.stripe_subscription_id)
        except stripe_lib.StripeError as e:
            stripe_summary = f'stripe error: {e}'

    # enforcement before communication (#1734 redesign B2): a fresh suspension
    # closes the open semester exactly once, so the suspended notice below (and
    # the refreshed counts) describe the deck's actual post-suspension state
    semester_summary = close_semester_on_new_suspension(tenant)
    tenant.update_cached_fields()  # the close empties the current-student count
    notices_summary = process_deck_notices(tenant)
    return (
        f"Refreshed cached Tenant fields for deck '{tenant.schema_name}'; "
        f"stripe: {stripe_summary}; semester: {semester_summary}; notices: {notices_summary}"
    )
