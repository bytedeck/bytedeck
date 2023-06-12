import html2text

from django.core.mail import get_connection, EmailMultiAlternatives
from django.utils.safestring import mark_safe
from django.conf import settings

from hackerspace_online.celery import app


def textify(html):
    """
    Generate a plain text version of an html content using html2text library.
    """
    # html2text is a python script that converts a page of HTML into clean, easy-to-read plain ASCII text
    h = html2text.HTML2Text()
    # don't ignore links anymore, I like links
    h.ignore_links = False
    return h.handle(html)


# That's `django.core.mail.send_mass_mail` rewritten to use `EmailMultiAlternatives`
def send_mass_html_mail(datatuple, fail_silently=False, auth_user=None, auth_password=None, connection=None):
    """
    Given a datatuple of (subject, text_content, html_content, from_email,recipient_list),
    sends each message to each recipient list. Returns the number of emails sent.

    If from_email is None, the DEFAULT_FROM_EMAIL setting is used.
    If auth_user and auth_password are set, they're used to log in.
    If auth_user is None, the EMAIL_HOST_USER setting is used.
    If auth_password is None, the EMAIL_HOST_PASSWORD setting is used.
    """
    connection = connection or get_connection(
        username=auth_user, password=auth_password, fail_silently=fail_silently)
    messages = []
    for subject, text, html, from_email, recipient in datatuple:
        message = EmailMultiAlternatives(subject, text, from_email, recipient)
        message.attach_alternative(html, 'text/html')
        messages.append(message)
    return connection.send_messages(messages)


@app.task(name="tenant.tasks.send_email_message")
def send_email_message(subject, message, recipient_list, **kwargs):
    # the subject, text, html, from_email and recipient_list parameters are required.
    send_mass_html_mail([
        (subject, textify(message), mark_safe(message), settings.DEFAULT_FROM_EMAIL, recipient_list)
    ], fail_silently=True)
