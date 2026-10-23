from django import template

from siteconfig.models import SiteConfig

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


@register.simple_tag(takes_context=True)
def can_export_to_library(context):
    """Whether the current user may export quests/campaigns to the Shared Library.

    Single source of truth for the export buttons (issue #2536): the templates that
    render one ask this tag themselves, so every page that includes a button bar
    offers the button correctly by default, with nothing for its view to pass.

    Args:
        context (django.template.Context): the rendering context; the request is
            read from it, so the tag needs no arguments.

    Returns:
        bool: True if this user may export to the Shared Library from this page.
    """
    request = context.get('request')
    if request is None:
        # Rendered without a request (no RequestContext): there is no user to
        # allow, so offer no export button rather than raise.
        return False
    return SiteConfig.get().can_user_export_to_library(request.user)
