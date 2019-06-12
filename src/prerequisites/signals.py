from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from prerequisites.tasks import update_quest_conditions_for_user, update_quest_conditions, update_sigan, update_All


@receiver([post_save, post_delete])
def update_conditions_met_for_user(sender, instance, *args, **kwargs):
    list_of_models = ('BadgeAssertion', 'QuestSubmission', 'CourseStudent')
    if sender.__name__ not in list_of_models:
        return
    user_id = instance.user_id
    update_quest_conditions_for_user.apply_async(args=[user_id], queue='default', countdown=10)


@receiver([post_save, post_delete])
def update_conditions_met(sender, instance, *args, **kwargs):
    list_of_models = ('Badge', 'Quest', 'CourseStudent')
    import ipdb; ipdb.set_trace()
    if sender.__name__ not in list_of_models:
        return
    update_quest_conditions.apply_async(args=[1], queue='default')
