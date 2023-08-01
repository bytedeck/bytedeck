from django.conf import settings
from django.core.mail import EmailMultiAlternatives
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
    # sending a text and HTML content combination
    email = EmailMultiAlternatives(
        subject,
        body=textify(msg),  # convert msg to plain text, using textify utility
        to=[settings.DEFAULT_FROM_EMAIL],
        bcc=recipient_list,
    )
    email.attach_alternative(msg, "text/html")
    email.send()
