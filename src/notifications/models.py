from django.db import models

from .signals import notify
# Create your models here.

def new_notification(*args, **kwargs):
    print(args)
    print(kwargs)


notify.connect(new_notification)
