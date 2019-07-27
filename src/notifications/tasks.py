from celery import Celery

from django.core.mail import send_mail

app = Celery()

@app.task
def printadd(x, y):
    print("testing")
    print(x+y)

@app.task
def email(to="tylerecouture@gmail.com", message="Beat test"):
    print("Sending Email to ...")
    # send_mail(
    #     'Test from Django',
    #     'Testing DJango celery beat.',
    #     'timberline.hackerspace@gmail.com',
    #     [to],
    #     fail_silently=False,
    # )
