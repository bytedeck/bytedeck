# http://docs.celeryproject.org/en/latest/django/first-steps-with-django.html#using-the-shared-task-decorator
from __future__ import absolute_import, unicode_literals
from celery import shared_task

from django_celery_beat.models import CrontabSchedule
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.mail import send_mail, EmailMultiAlternatives

User = get_user_model()

from notifications.models import Notification
from .models import Profile


email_notifications_schedule, _ = CrontabSchedule.objects.get_or_create(
    minute='0',
    hour='5',
)

def get_notification_emails():
    users_to_email = User.objects.filter(profile__get_notifications_by_email=True)
    print("Users to email: {}".format(str(users_to_email)))
    if len(users_to_email) > 95:
        print("Gmail is limited to sending 100 emails per day... gonna trim the list!")
    subject = 'Hackerspace notifications'
    from_email_address = 'timberline.hackerspace@gmail.com'
    notification_emails = []
    for user in users_to_email:
        print("Looking for notifications for user: {}".format(user) )
        to_email_address = user.email
        print("email addy: {}".format(user.email))
        unread_notifications = Notification.objects.all_unread(user)
        print("Notifications: {}".format( str(unread_notifications)))
        # text_content = 'This is an important message.'
        text_content = str(unread_notifications)
        notification_emails.append( EmailMultiAlternatives(subject, text_content, from_email_address, [to_email_address]) )

    return notification_emails


@shared_task
def email_notifications_to_users():
    notification_emails = get_notification_emails()
    connection = mail.get_connection() 
    connection.send_messages(notification_emails)
    print("Emailing sending these: ")
    print(notification_emails)


    # send_mail(
    #     'Test from Django',
    #     'Testing DJango celery beat.',
    #     'timberline.hackerspace@gmail.com',
    #     [to],
    #     fail_silently=False,
    # )
    # print("for reals this time")