from django.apps import apps
from django.db import models
from django.db.models import Sum

from taggit.managers import TaggableManager

from siteconfig.models import SiteConfig


def total_xp_by_tags(user, tags):
    """
    Returns user's total xp over active_semester filtered by tags

    Args:
        tags (list[str], Queryset<Tag>): a queryset or list of Tag objects

    Returns:
        int : total xp of user related to tag
    """
    # get models through here to prevent circular imports
    QuestSubmission = apps.get_model("quest_manager", "QuestSubmission")
    BadgeAssertion = apps.get_model("badges", "BadgeAssertion")

    # get all objects with xp that is related to user and tag
    # sum can be none since aggregate() will always return a dictionary of keys of whatever arg you put in.
    # if there are no badges or quests linked to the user, aggregate will return a dictionary like: { 'badge__xp__sum': None }
    xp_list = [
        # QuestSubmission xp sum  
        QuestSubmission.objects.all_approved(user, active_semester_only=True).filter(
            is_completed=True, 
            quest__tags__name__in=list(tags)
        ).exclude(do_not_grant_xp=True).distinct().aggregate(Sum("quest__xp"))['quest__xp__sum'],
        
        # BadgeAssertion xp sum 
        BadgeAssertion.objects.all_for_user(user).filter(
            semester=SiteConfig.get().active_semester, 
            badge__tags__name__in=list(tags)
        ).exclude(do_not_grant_xp=True).distinct().aggregate(Sum("badge__xp"))['badge__xp__sum'],
    ]
    return sum(xp for xp in xp_list if xp is not None)


class TagsModelMixin(models.Model):
    """And abstract model to implement tags"""

    tags = TaggableManager(blank=True)

    class Meta:
        abstract = True
