from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import get_template

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

    # The subject, text, html, from_email and recipient_list parameters are required.
    for to in recipient_list:
        send_mail(
            subject, textify(msg), settings.DEFAULT_FROM_EMAIL, [to], html_message=msg,
            # The fail_silently argument controls how the backend should handle errors.
            # If fail_silently is True, exceptions during the email sending process
            # will be silently ignored.
            fail_silently=True,
        )
