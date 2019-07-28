# http://docs.celeryproject.org/en/latest/django/first-steps-with-django.html#using-the-shared-task-decorator
from __future__ import absolute_import, unicode_literals
from celery import shared_task

from django.core.mail import send_mail


@shared_task
def printadd(x, y):
    print("testing")
    print(x+y)


@shared_task
def email(to="tylerecouture@gmail.com", message="Beat test"):
    print("Sending Email to ...")
    send_mail(
        'Test from Django',
        'Testing DJango celery beat.',
        'timberline.hackerspace@gmail.com',
        [to],
        fail_silently=False,
    )
    print("for reals this time")
