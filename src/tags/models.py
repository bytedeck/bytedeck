from django.apps import apps
from django.db import models
from django.db.models import Sum

from taggit.models import Tag
from taggit.managers import TaggableManager

from siteconfig.models import SiteConfig


def get_tags_from_user(user):
    """
    Returns all tags from quest and badges that are linked to user

    Args:
        user (User model): user model

    Returns:
        list[Tag] : list of Tag models
    """
    # get models through here to prevent circular imports
    QuestSubmission = apps.get_model("quest_manager", "QuestSubmission")
    BadgeAssertion = apps.get_model("badges", "BadgeAssertion")
    
    # tags related to user's quests
    quest_ids = QuestSubmission.objects.filter(user=user).distinct().values_list('quest', flat=True)
    quest_tags = Tag.objects.filter(quest__id__in=quest_ids)

    # tags related to user's badges
    badge_ids = BadgeAssertion.objects.filter(user=user).distinct().values_list('badge', flat=True)
    badge_tags = Tag.objects.filter(badge__id__in=badge_ids)

    # union + unique only and return
    return (quest_tags | badge_tags).distinct()


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


def get_user_tags_and_xp(user):
    """
    returns a list of tuples containing a tag object and how much xp it has.
    Sorted by total xp in descending order

    tag has to be related to user.
    xp is dependant on how many Quest user has submitted that is related to tag.

    Args:
        user (UserModel): user object

    Returns:
        list[tuple[Tag, int]]: sorted list of tuples containing tag and int objects
    """
    tag_info_tuple = []

    # append tag object and tag xp to tag_info_tuple
    user_related_tags = get_tags_from_user(user)
    for tag in user_related_tags:
        total_xp = total_xp_by_tags(user, [tag])
        tag_info_tuple.append((tag, total_xp))
    
    # sort by total xp (descending order) then return
    return sorted(tag_info_tuple, key=lambda tag_tuple: tag_tuple[1])[::-1]


class TagsModelMixin(models.Model):
    """And abstract model to implement tags"""

    tags = TaggableManager(blank=True)

    class Meta:
        abstract = True
