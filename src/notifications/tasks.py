# http://docs.celeryproject.org/en/latest/django/first-steps-with-django.html#using-the-shared-task-decorator
from __future__ import absolute_import, unicode_literals
from celery import shared_task

from django_celery_beat.models import CrontabSchedule, PeriodicTask
from django.utils import timezone
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core import mail
from django.core.mail import EmailMultiAlternatives

from django.template.loader import get_template


from .models import Notification

User = get_user_model()


email_notifications_schedule, _ = CrontabSchedule.objects.get_or_create(
    minute='0',
    hour='5',
    timezone=timezone.get_current_timezone()
)


def get_notification_emails():
    users_to_email = User.objects.filter(profile__get_notifications_by_email=True)
    # print("Users to email: {}".format(str(users_to_email)))
    if len(users_to_email) > 90:
        print("Gmail is limited to sending 100 emails per day... gonna trim the list!")
    subject = 'Hackerspace notifications'
    notification_emails = []
    for user in users_to_email:

        to_email_address = user.email
        unread_notifications = Notification.objects.all_unread(user)

        if unread_notifications:
            text_content = str(unread_notifications)
            html_template = get_template('notifications/email_notifications.html')
            profile_edit_url = "https://{}{}".format(
                Site.objects.get_current(),
                reverse('profiles:profile_update', kwargs={'pk': user.profile.id})
            )

            html_content = html_template.render(
                {
                    'user': user,
                    'notifications': unread_notifications,
                    'profile_edit_url': profile_edit_url,
                }
            )
            # print("Preparing notification email for {} at {}.".format(user, to_email_address))
            email_msg = EmailMultiAlternatives(subject, text_content, to=[to_email_address])
            email_msg.attach_alternative(html_content, "text/html")
            notification_emails.append(email_msg)

    return notification_emails


@shared_task
def email_notifications_to_users():
    notification_emails = get_notification_emails()
    connection = mail.get_connection()
    connection.send_messages(notification_emails)
    print("Sending {} notification emails.".format(len(notification_emails)))


PeriodicTask.objects.get_or_create(
    crontab=email_notifications_schedule,
    name='Send daily email notifications',
    task='notifications.tasks.email_notifications_to_users',
    queue='default'
)

# send_mail(
#     'Test from Django',
#     'Testing DJango celery beat.',
#     'timberline.hackerspace@gmail.com',
#     ['tylere.couture@sd72.bc.ca'],
#     fail_silently=False,
# )
# print("for reals this time")
