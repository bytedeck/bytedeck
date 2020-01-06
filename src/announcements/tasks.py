from __future__ import absolute_import, unicode_literals
from celery import shared_task

from django.core.mail import EmailMultiAlternatives
from django.template.loader import get_template
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
import djconfig
from courses.models import CourseStudent
from notifications.signals import notify

from .models import Announcement

User = get_user_model()


@shared_task(name='announcements.tasks.send_notifications')
def send_notifications(user_id, announcement_id):
    djconfig.reload_maybe()  # needed for automated user: hs_hackerspace_ai
    announcement = get_object_or_404(Announcement, pk=announcement_id)
    sending_user = User.objects.get(id=user_id)
    affected_users = CourseStudent.objects.all_users_for_active_semester()
    notify.send(
        sending_user,
        # action=new_announcement,
        target=announcement,
        recipient=sending_user,
        affected_users=affected_users,
        icon="<i class='fa fa-lg fa-fw fa-newspaper-o text-info'></i>",
        verb='posted'
    )


@shared_task(name='announcements.tasks.send_announcement_emails')
def send_announcement_emails(content, url):
    users_to_email = User.objects.filter(
        is_active=True,
        profile__get_announcements_by_email=True
    ).exclude(email='').values_list('email', flat=True)

    subject = 'Hackerspace Announcement'
    text_content = content
    html_template = get_template('announcements/email_announcement.html')
    html_content = html_template.render({'content': content, 'url': url})
    email_msg = EmailMultiAlternatives(
        subject,
        body=text_content,
        to=['timberline.hackerspace@gmail.com'],
        bcc=users_to_email
    )
    email_msg.attach_alternative(html_content, "text/html")
    email_msg.send()
    # print("Sending {} announcement emails.".format(len(users_to_email)))


@shared_task(name='announcements.tasks.publish_announcement')
def publish_announcement(user_id, announcement_id, absolute_url):
    """ Publish the announcement, including:
            - edit model instance
            - push notifications
            - send announcement emails
    """
    # update model instance
    announcement = get_object_or_404(Announcement, pk=announcement_id)
    announcement.draft = False
    announcement.save()

    # push notifications
    send_notifications.apply_async(args=[user_id, announcement_id], queue='default')

    # Send the announcements by email to those who have ask for them, using celery
    send_announcement_emails.apply_async(args=[announcement.content, absolute_url], queue='default')
