import logging
import traceback

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from django.db.utils import OperationalError

from tenant_schemas_celery.task import TenantTask

from courses.models import CourseStudent
from hackerspace_online.celery import app
from prerequisites.models import Prereq, PrereqAllConditionsMet
from quest_manager.models import Quest

logger = logging.getLogger(__name__)


User = get_user_model()


class TransactionAwareTask(TenantTask):
    abstract = True

    def apply_async(self, *args, **kwargs):
        try:
            transaction.on_commit(lambda: super(TransactionAwareTask, self).apply_async(*args, **kwargs))
        except OperationalError:
            logger.info(traceback.format_exc())
            countdown = kwargs.get('countdown', 60)
            kwargs['countdown'] = countdown * 2
            return super(TransactionAwareTask, self).apply_async(*args, **kwargs)
        except Exception:
            logger.error(traceback.format_exc())


@app.task(base=TransactionAwareTask, bind=True, name='prerequisites.tasks.update_conditions_for_quest', max_retries=settings.CELERY_TASK_MAX_RETRIES)  # noqa
def update_conditions_for_quest(self, quest_id, start_from_user_id):
    """Cycles through all relevant users and adds this quest to their cache of available quests (PrereqAllConditionsMet), if they meet the prereqs,
    or removes it if they don't. This is done in bunches of users (CELERY_TASKS_BUNCH_SIZE), recursively.

    If the quest is available outside a course, it will update the cache for ALL users, otherwise it will only update
    students who are currently registered in a course.

    Args:
        quest_id (int): The quest with updated prerequisites (i.e this quest is the parent_object of an updated Prereq),
        start_from_user_id (int): user_id to start with for the next bunch of calculations
    """
    quest = Quest.objects.filter(id=quest_id).first()
    if not quest:
        # If the quest is deleted while this task is running.
        return f"Quest {quest_id} no longer exists."

    # check if this already started recently, if so, don't need to start a new one.
    cache_key = f'update_conditions_for_quest_{quest_id}_wait'
    if start_from_user_id == 1 and cache.get(cache_key):
        return f"Skipping task for quest {quest_id}, already started."

    # Set a 1 second cache to prevent this task from running multiple times concurrently for the same quest
    # for example, when prereqs are updated, one might be deleted and two more added, that will result in 3 signals!
    cache.set(cache_key, True, 1)

    if quest.available_outside_course:
        users = User.objects.all()
    else:
        users = CourseStudent.objects.all_users_for_active_semester()

    users = users.order_by('id').filter(id__gte=start_from_user_id)[:settings.CELERY_TASKS_BUNCH_SIZE]
    user = None

    for user in users:
        try:
            quest_prereq_cache, created = PrereqAllConditionsMet.objects.get_or_create(
                user=user,
                model_name=Quest.get_model_name(),
            )
        except PrereqAllConditionsMet.MultipleObjectsReturned:
            # why are there multiple?  Delete cache and regenerate new for this user
            caches = PrereqAllConditionsMet.objects.filter(user=user, model_name=Quest.get_model_name())
            caches.delete()
            # do full recalc for the user:
            update_quest_conditions_for_user.apply_async(args=[user.id], queue='default')
            # carry on with the next user
            continue

        if Prereq.objects.all_conditions_met(quest, user):
            quest_prereq_cache.add_id(quest.id)
        else:
            quest_prereq_cache.remove_id(quest.id)

    else:
        # finished the previous bunch, call the next bunch recursively
        # or maybe there were no users in the bunch... check that too
        if user:
            # user is the last user that was updated, increment by 1
            minimum_user_id = user.id + 1
            user = User.objects.filter(id__gte=minimum_user_id).values('id').first()
            if user:
                # there are more users, so keep going.
                self.apply_async(
                    queue='default',
                    # doesn't seem necessary, each group of 10 only takes about 0.1 seconds?
                    countdown=1,  # delay a bit to give some time for the last group to finish, so we don't hog all the resources.
                    kwargs={'quest_id': quest.id, 'start_from_user_id': minimum_user_id}
                )
    # Return value is displayed at the end of the celery log
    return quest.name


@app.task(base=TransactionAwareTask, bind=True, name='prerequisites.tasks.update_quest_conditions_for_user', max_retries=settings.CELERY_TASK_MAX_RETRIES)  # noqa
def update_quest_conditions_for_user(self, user_id):
    user = User.objects.filter(id=user_id).first()
    if not user:
        return None
    pk_met_list = [obj.pk for obj in Quest.objects.all() if Prereq.objects.all_conditions_met(obj, user)]
    met_list, created = PrereqAllConditionsMet.objects.update_or_create(
        user=user, model_name=Quest.get_model_name(), defaults={'ids': str(pk_met_list)})

    logger.info(f"Task prerequisites.tasks.update_quest_conditions_for_user: Cache of available quests udpated for {user.username}")
    # Return value is displayed at the end of the celery log
    # This return value is used to assign new quest cache, so don't change it, print useful info instead for celery log
    return met_list.id


@app.task(base=TransactionAwareTask, bind=True, name='prerequisites.tasks.update_quest_conditions_all_users', max_retries=settings.CELERY_TASK_MAX_RETRIES)  # noqa
def update_quest_conditions_all_users(self, start_from_user_id):
    """Cycles through all quests for all users to update the cache of available quests (PreqAllConditionsMet)
    This is done in bunches of users (CELERY_TASKS_BUNCH_SIZE), recursively.

    Args:
        user_id to start with for the next bunch of calculations
    """

    if start_from_user_id == 1 and cache.get('update_conditions_all_task_waiting'):
        # Return value is displayed at the end of the celery log
        return "Skipping task, already running."

    cache.set('update_conditions_all_task_waiting', True, settings.CONDITIONS_UPDATE_COUNTDOWN)

    # only cycle through users currently in a course
    users = CourseStudent.objects.all_users_for_active_semester()
    users = users.order_by('id').filter(id__gte=start_from_user_id)

    users = list(users.values_list('id', flat=True)[:settings.CELERY_TASKS_BUNCH_SIZE])  # noqa
    for uid in users:
        update_quest_conditions_for_user.apply_async(args=[uid], queue='default')

    if users:
        user = User.objects.filter(id__gte=users[-1] + 1).values('id').first()
        user and self.apply_async(args=[user['id']], queue='default', countdown=5)
