from django.conf import settings
from django.template.loader import get_template

from hackerspace_online.celery import app
from utilities.mail import send_mass_mail
from utilities.html import textify


@app.task(name="tenant.tasks.send_email_message")
def send_email_message(subject, message, recipient_list, **kwargs):
    """
    Simple task that's intended to handle mass emailing.
    """
    # load and render "message.txt" template
    msg = get_template("admin/tenant/email/message.txt").render(context={
        "message": message,
    })

    # the subject, text, html, from_email and recipient_list parameters are required.
    send_mass_mail([
        (subject, textify(msg), msg, settings.DEFAULT_FROM_EMAIL, recipient_list)
    ], fail_silently=True)
