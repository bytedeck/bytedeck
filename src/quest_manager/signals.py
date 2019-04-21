from bs4 import BeautifulSoup
from django.db.models.signals import pre_save
from django.dispatch import receiver

from quest_manager.models import Quest


@receiver(pre_save, sender=Quest)
def quest_pre_save_callback(sender, instance, **kwargs):
    # print (instance.instructions)

    # Prettify html
    soup = BeautifulSoup(instance.instructions, 'html.parser')
    instance.instructions = soup.prettify()