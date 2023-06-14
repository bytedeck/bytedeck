from django.conf import settings
from django.utils.safestring import mark_safe

from hackerspace_online.celery import app
from utilities.mail import send_mass_mail
from utilities.html import textify


@app.task(name="tenant.tasks.send_email_message")
def send_email_message(subject, message, recipient_list, **kwargs):
    """
    Simple task that's intended to handle mass emailing.
    """
    # the subject, text, html, from_email and recipient_list parameters are required.
    send_mass_mail([
        (subject, textify(message), mark_safe(message), settings.DEFAULT_FROM_EMAIL, recipient_list)
    ], fail_silently=True)
