from celery import shared_task

from quest_manager.models import Quest
from prerequisites.models import Prereq, PrereqAllConditionsMet

from django.contrib.auth import get_user_model


User = get_user_model()


@shared_task(name='update_quest_conditions_for_user')
def update_quest_conditions_for_user(user_id):
    user = User.objects.filter(id=user_id).first()
    if not user:
        return
    pk_met_list = [obj.pk for obj in Quest.objects.all() if Prereq.objects.all_conditions_met(obj, user)]
    model_name = '{}.{}'.format(Quest._meta.app_label, Quest._meta.model_name)
    met_list, created = PrereqAllConditionsMet.objects.update_or_create(
        user=user, model_name=model_name, defaults={'ids': str(pk_met_list)})
    return met_list.id


@shared_task(name='update_quest_conditions')
def update_quest_conditions(user_id):
    users = User.objects.filter(id__gte=user_id).values_list('id', flat=True)[:25]
    for user_id in users:
        update_quest_conditions_for_user.apply_async(args=[user_id], queue='default')
    else:
        user = User.objects.filter(id__gte=user_id + 1).values('id').first()
        if user:
            update_quest_conditions.apply_async(args=[user_id + 1], queue='default', countdown=20)


@shared_task(name='update_sigan')
def update_sigan(user_id):
    print(user_id)


@shared_task(name='update_sigan')
def update_All(user_id):
    print(user_id)