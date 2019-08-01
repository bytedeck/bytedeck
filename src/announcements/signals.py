from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import Announcement
# from .tasks import send_announcement_emails


@receiver(pre_save, sender=Announcement)
def save_announcements_signal(sender, instance, **kwargs):
    # print("Saving announcement: {}".format(sender))
    # send_announcement_emails.apply_async(args=[squeue='default')
    # don't send emails from here, use the publish button
    pass
