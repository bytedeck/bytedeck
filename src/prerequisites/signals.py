from django.conf import settings
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from badges.models import Badge
from prerequisites.models import Prereq
from prerequisites.tasks import (
    update_conditions_for_quest,
    update_quest_conditions_for_user,
    update_quest_conditions_all
)
from quest_manager.models import Quest


@receiver([post_save, post_delete])
def update_conditions_met_for_user(sender, instance, *args, **kwargs):
    list_of_models = ('BadgeAssertion', 'QuestSubmission', 'CourseStudent')
    if sender.__name__ in list_of_models:
        update_quest_conditions_for_user.apply_async(args=[instance.user_id], queue='default')


# Don't need post_delete, it doesn't affect on reesult and will be updated on next all conditions update
@receiver([post_save], sender=Quest)
def update_conditions_met_for_quest(sender, instance, *args, **kwargs):
    update_conditions_for_quest.apply_async(kwargs={'quest_id': instance.id, 'start_from_user_id': 1}, queue='default')


@receiver([post_save, post_delete], sender=Badge)
@receiver([post_save, post_delete], sender=Prereq)
def update_conditions_met(sender, instance, *args, **kwargs):
    update_quest_conditions_all.apply_async(args=[1], queue='default', countdown=settings.CONDITIONS_UPDATE_COUNTDOWN)
