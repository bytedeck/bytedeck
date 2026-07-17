from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management import call_command
from django.template.loader import get_template

from django_tenants.utils import get_tenant_model, schema_context

from hackerspace_online.celery import app
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
