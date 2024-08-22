from django.dispatch import receiver
from django.db.models.signals import post_save, post_delete

from djcytoscape.models import CytoScape
from siteconfig.models import SiteConfig
from badges.models import Badge
from quest_manager.models import Quest
from courses.models import Rank
from prerequisites.models import Prereq

from djcytoscape.tasks import regenerate_map


def regenerate_related_maps(instance):
    """ Helper function for models that can exist as CytoElements.
    Attach to a models [post_save, pre_delete] signal to regenerate all related maps when
    said model is updated or deleted.
    """
    if not SiteConfig.get().map_auto_update:
        return

    # get related maps
    related_map_ids = list(CytoScape.objects.get_related_maps(instance).values_list('id', flat=True))
    if not related_map_ids:
        return

    # run task in background
    regenerate_map.apply_async(args=[related_map_ids], queue='default')


@receiver([post_save, post_delete], sender=Badge)
@receiver([post_save, post_delete], sender=Quest)
@receiver([post_save, post_delete], sender=Rank)
def badge_regenerate_related_maps(sender, instance, **kwargs):
    """ Regenerates any related map(s) when either a badge, quest, or rank is saved/deleted. """
    regenerate_related_maps(instance)


@receiver([post_save, post_delete], sender=Prereq)
def prereq_regenerate_related_maps(sender, instance, **kwargs):
    """ Regenerates any related map(s) when a prereq is saved or deleted. """

    # get parent object of prereq
    model_class = instance.parent_content_type.model_class()

    try:
        object_ = model_class.objects.get(id=instance.parent_object_id)

    # means this signal was called when object_ was deleted
    except model_class.DoesNotExist:
        return

    regenerate_related_maps(object_)
