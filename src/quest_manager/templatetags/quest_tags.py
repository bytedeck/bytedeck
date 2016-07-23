from django import template

register = template.Library()


@register.filter
def is_hidden(quest, user):
    """
    Checks if the quest is in the user's list of hidden quests
    :param quest: the Quest
    :param user:
    :return: True if user has hidden the quest
    """
    if not user or not quest:
        return None
    return user.profile.is_quest_hidden(quest)
