from __future__ import absolute_import, unicode_literals

from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.template.loader import get_template

from tenant_schemas.utils import get_public_schema_name

from hackerspace_online.celery import app
# from celery import shared_task


from siteconfig.models import SiteConfig

from .models import Notification

User = get_user_model()


def get_notification_emails(scheme_and_domain):
    users_to_email = User.objects.filter(profile__get_notifications_by_email=True)
    # If testing with a gmail account, might want this:
    # if len(users_to_email) > 90:
    #     print("Gmail is limited to sending 100 emails per day... gonna trim the list!")
    subject = '{} Notifications'.format(SiteConfig.get().site_name_short)
    html_template = get_template('notifications/email_notifications.html')

    notification_emails = []

    for user in users_to_email:

        to_email_address = user.email
        unread_notifications = Notification.objects.all_unread(user)

        if unread_notifications:
            text_content = str(unread_notifications)
            
            html_content = html_template.render({
                'user': user,
                'notifications': unread_notifications,
                'scheme_and_domain': scheme_and_domain,
                'profile_edit_url': reverse('profiles:profile_edit_own')
            })
            email_msg = EmailMultiAlternatives(subject, text_content, to=[to_email_address])
            email_msg.attach_alternative(html_content, "text/html")
            notification_emails.append(email_msg)

    return notification_emails


# Not an @app.task with tenant-schemas-celery because this is not a tenant aware task, i.e. we're doing it manually.
# @app.task(name='notifications.tasks.send_email_notification_tenant')
# def send_email_notification_tenant(scheme_and_domain):
#     notification_emails = get_notification_emails(scheme_and_domain)
#     connection = mail.get_connection()
#     connection.send_messages(notification_emails)


@app.task(name='notifications.tasks.email_notifications_to_users')
def email_notifications_to_users(tenant_domain_url):

    # can't use the obvious request.build_absolute_uri() cus there is no request!  So hack it together...
    # this won't be accurate in development because it doesn't include the port `:8000`
    scheme_and_domain = "https://{}".format(tenant_domain_url)
    # add port for development:
    if get_public_schema_name() == 'localhost':
        scheme_and_domain += ":8000"

    notification_emails = get_notification_emails(scheme_and_domain)
    connection = mail.get_connection()
    connection.send_messages(notification_emails)
    # send_email_notification_tenant.delay(scheme_and_domain)
