"""
Tools for sending email, matching `django.core.mail` naming convention.
"""
from django.core.mail import get_connection, EmailMultiAlternatives


def send_mass_mail(datatuple, fail_silently=False, auth_user=None, auth_password=None, connection=None):
    """
    Given a datatuple of (subject, text, html, from_email, recipient_list), send
    each message to each recipient list. Return the number of emails sent.

    If from_email is None, use the DEFAULT_FROM_EMAIL setting.

    The fail_silently argument controls how the backend should handle errors.
    If fail_silently is True, exceptions during the email sending process
    will be silently ignored.

    If auth_user and auth_password are set, use them to log in.
    If auth_user is None, use the EMAIL_HOST_USER setting.
    If auth_password is None, use the EMAIL_HOST_PASSWORD setting.

    Note: This is fork of `django.core.mail.send_mass_mail` rewritten
    to use `django.core.mail.EmailMultiAlternatives` class.
    """
    connection = connection or get_connection(
        username=auth_user,
        password=auth_password,
        fail_silently=fail_silently
    )
    messages = []
    for subject, text, html, from_email, recipient in datatuple:
        message = EmailMultiAlternatives(subject, text, from_email, recipient)
        message.attach_alternative(html, "text/html")
        messages.append(message)
    return connection.send_messages(messages)
