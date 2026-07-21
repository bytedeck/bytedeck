from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management import call_command
from django.db import connection
from django.template.loader import get_template

from django_tenants.utils import get_public_schema_name, get_tenant_model, schema_context, tenant_context

from hackerspace_online.celery import app
from library.utils import get_library_schema_name
from utilities.html import textify


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


@app.task(name="tenant.tasks.deck_status_check")
def deck_status_check():
    """Refresh the current deck's cached Tenant fields (counts, owner info, last login).

    Dispatched per-schema by daily_deck_status_check_for_all_tenants, making the
    nightly beat run the canonical refresher for the Tenant cached fields -- the
    tenant admin changelist no longer refreshes them on every page load (that
    was an acknowledged N+1 across all decks). Later phases of epic #1729 extend
    this task with the expiry-reminder cadence and limit warnings (#1733).

    Takes no arguments (the schema comes from the task's tenant context);
    returns a short summary string for the worker log.
    """
    tenant = get_tenant_model().objects.get(schema_name=connection.schema_name)
    tenant.update_cached_fields()
    return f"Refreshed cached Tenant fields for deck '{tenant.schema_name}'"
