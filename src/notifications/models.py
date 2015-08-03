from django.db import models

from .signals import notify
# Create your models here.

def new_notification(sender, recipient, action, *args, **kwargs):
    print(sender)
    print(recipient)
    print(action)
    
    print(args)
    print(kwargs)


notify.connect(new_notification)
