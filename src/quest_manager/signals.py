from django.db.models.signals import pre_save
from django.dispatch import receiver
from tidylib import Tidy

from quest_manager.models import Quest


@receiver(pre_save, sender=Quest)
def quest_pre_save_callback(sender, instance, **kwargs):
    instance.instructions = tidy_html(instance.instructions)


def tidy_html(content):

    config = {
        # "break-before-br": True,
        # "doctype": "omit",
        # "output-html": True,
        # "wrap": 0,
    }
    result, errors = Tidy().tidy_fragment(content, options=config)
    return result
