"""Helpers shared by the map tests."""
from django.core.cache import cache

from djcytoscape.tasks import pending_regeneration_key


def simulate_regeneration_starting(map_id):
    """Clear the marker that keeps a second regeneration off the queue for this map.

    `regenerate_map` clears it itself, as the first thing it does for each map, so
    that a save landing from then on queues its own rebuild instead of relying on
    one that may already have read past it.

    Tests that count queued regenerations mock `apply_async`, so no task ever runs
    to clear the marker: without this, everything saved after the first save is
    collapsed into a regeneration that is forever pending, and nothing else is
    queued. Calling this between two saves puts a test in the state a real deck is
    in once the first save's task has started.

    Args:
        map_id (int): id of the Cytoscape map whose regeneration has notionally begun.
    """
    cache.delete(pending_regeneration_key(map_id))
