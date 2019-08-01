from __future__ import absolute_import, unicode_literals
from celery import shared_task

from django.core.mail import EmailMultiAlternatives
from django.template.loader import get_template

from django.contrib.auth import get_user_model

User = get_user_model()


@shared_task
def add(x, y):
    return x + y


@shared_task
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
    print("Sending {} announcement emails.".format(len(users_to_email)))
