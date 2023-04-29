from hackerspace_online.celery import app
from quest_manager.models import Quest
# from notifications.tasks import notify
from notifications.signals import notify
from siteconfig.models import SiteConfig


@app.task(name='quest_manager.tasks.remove_quest_submissions_for_hidden_quest')
def remove_quest_submissions_for_hidden_quest(quest_id):
    quest_qs = Quest.objects.filter(id=quest_id)
    quest = quest_qs.first()

    if not quest:
        return

    # This is quite hacky that we need to make it visible again because Quest.objects
    # is overriden to exclude Quests that have visible_to_students value of False.
    # The reason is because when doing a quest.questsubmission_set.all(), it performs an INNER JOIN and uses
    # the model manager for the conditions
    quest_qs.update(visible_to_students=True)

    verb = f'deleted your submission. Quest: {quest} has been removed or hidden'
    for submission in quest.questsubmission_set.all():
        if submission.is_completed and submission.is_approved:
            continue

        notify.send(
            SiteConfig.get().deck_ai,
            recipient=submission.user,
            verb=verb,
            icon="<i class='fa fa-lg fa-fw fa-exclamation-triangle text-info'></i>",
        )
        submission.delete()

    # Make it False again
    quest_qs.update(visible_to_students=False)
