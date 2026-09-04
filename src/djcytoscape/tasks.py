from functools import partial

from django.contrib.auth import get_user_model
from django.core.cache import cache

from hackerspace_online.celery import app

from notifications.signals import notify
from siteconfig.models import SiteConfig

from .models import CytoScape

User = get_user_model()

# Seconds a regeneration queued by a signal waits before it runs. While one is
# waiting, the signal will not queue a second for the same map, so a run of
# saves costs one rebuild rather than one each. The wait is also what makes
# collapsing them sound: it gives the rest of the run time to land, so the one
# rebuild that does happen reads a database that already holds all of it.
MAP_REGENERATION_DELAY = 10

# How long the "already queued" marker survives on its own. `regenerate_map`
# clears it as it starts, so this only decides how long a map keeps deduplicating
# against a regeneration that never arrives (a worker lost, the queue purged, the
# map deleted before the task reached it): shortly after the task was due, the
# next save queues a fresh one instead.
MAP_REGENERATION_PENDING_TIMEOUT = MAP_REGENERATION_DELAY * 2


def pending_regeneration_key(map_id):
    """Cache key marking that a regeneration of this map is queued and has not begun.

    The cache namespaces keys by schema (`django_tenants.cache.make_key`), so the
    same map id on two decks gets a marker each.

    Args:
        map_id (int): id of the Cytoscape map.

    Returns:
        str: the cache key for that map's pending regeneration.
    """
    return f'djcytoscape.pending_regeneration.{map_id}'


@app.task(name='djcytoscape.tasks.regenerate_all_maps')
def regenerate_all_maps(requesting_user_id):
    requesting_user = User.objects.get(id=requesting_user_id)
    for scape in CytoScape.objects.all():
        try:
            scape.regenerate()
        except scape.InitialObjectDoesNotExist:
            notify.send(
                SiteConfig.get().deck_ai,
                recipient=requesting_user,
                icon="<i class='fa fa-lg fa-fw fa-map-signs text-warning'></i>",
                verb=f"failed to regenerate '{scape.name} Map', the intial object no longer exists.  This map has been deleted."
            )

    notify.send(
        SiteConfig.get().deck_ai,
        target=None,
        recipient=requesting_user,
        affected_users=[requesting_user],
        icon="<i class='fa fa-lg fa-fw fa-map-signs text-success'></i>",
        verb="completed regeneration of all valid maps."
    )


@app.task(name='djcytoscape.tasks.regenerate_map')
def regenerate_map(map_ids):
    """ Regenerates each map in map_ids.
    Since this function will be mainly used by post signals, notifications to a user wont be functional
    Unlike `regenerate_all_maps`

    ARGS:
        map_ids (list[int]): list of ids belonging to Cytoscape maps
    """
    for scape in CytoScape.objects.filter(id__in=map_ids):
        # Give up the claim from inside the rebuild, once this map's row is held and just
        # before it reads. Waiting for that row can take as long as the rebuild ahead of
        # it, and a rebuild that has read nothing still covers every save made while it
        # waits, so releasing there rather than on the way in keeps the whole wait
        # deduplicated. Past that point it may have read over a change already, so a save
        # landing then has to queue a regeneration of its own rather than be lost in this.
        release_claim = partial(cache.delete, pending_regeneration_key(scape.id))

        try:
            scape.regenerate(on_lock_acquired=release_claim)
        except scape.InitialObjectDoesNotExist:
            # The map deleted itself before reaching its row, so the claim was never
            # released. Nothing can ask for a deleted map again, so it just expires.
            pass
