from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import Announcement
from .tasks import add


@receiver(pre_save, sender=Announcement)
def save_announcements_signal(sender, **kwargs):
    # print("Saving announcement: {}".format(sender))
    add.apply_async(args=[4, 4], queue='default')
