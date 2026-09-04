from django.core.cache import cache
from django.dispatch import receiver
from django.db.models.signals import post_save, post_delete

from djcytoscape.models import CytoScape
from siteconfig.models import SiteConfig
from badges.models import Badge
from quest_manager.models import Quest
from courses.models import Rank
from prerequisites.models import Prereq

from djcytoscape.tasks import MAP_REGENERATION_DELAY, MAP_REGENERATION_PENDING_TIMEOUT, pending_regeneration_key, regenerate_map
from utilities.signals import disable_for_loaddata


def regenerate_related_maps(instance):
    """ Helper function for models that can exist as CytoElements.
    Attach to a models [post_save, pre_delete] signal to regenerate all related maps when
    said model is updated or deleted.

    A map that already has a regeneration waiting to run is left to it instead of being
    given a second one. One edit fires this several times over (the quest, then each of
    its prereqs) and a bulk operation such as a library import fires it a great many
    times, and each of those rebuilds the whole map from scratch (#2658).

    Args:
        instance: the Quest, Badge or Rank that was saved or deleted, or for a Prereq,
            the parent object it belongs to.
    """
    if not SiteConfig.get().map_auto_update:
        return

    # get related maps, claiming each one that has no regeneration waiting yet. cache.add
    # writes only where the key is absent, so of several saves arriving together exactly
    # one claims a given map and the rest are collapsed into the rebuild it queues.
    map_ids_to_regenerate = [
        map_id for map_id in CytoScape.objects.get_related_maps(instance).values_list('id', flat=True)
        if cache.add(pending_regeneration_key(map_id), True, MAP_REGENERATION_PENDING_TIMEOUT)
    ]
    if not map_ids_to_regenerate:
        return

    # run task in background, once the rest of this run of saves has had time to land
    regenerate_map.apply_async(args=[map_ids_to_regenerate], countdown=MAP_REGENERATION_DELAY, queue='default')


@receiver([post_save, post_delete], sender=Badge)
@receiver([post_save, post_delete], sender=Quest)
@receiver([post_save, post_delete], sender=Rank)
@disable_for_loaddata
def badge_regenerate_related_maps(sender, instance, **kwargs):
    """ Regenerates any related map(s) when either a badge, quest, or rank is saved/deleted. """
    regenerate_related_maps(instance)


@receiver([post_save, post_delete], sender=Prereq)
@disable_for_loaddata
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
