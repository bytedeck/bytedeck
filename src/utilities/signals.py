"""Helpers shared by the signal receivers registered across the project's apps."""
from functools import wraps


def disable_for_loaddata(signal_handler):
    """Skip a save receiver while a fixture is being deserialized.

    Django sends pre_save and post_save with ``raw=True`` for every row `loaddata`
    deserializes, and [its documentation](https://docs.djangoproject.com/en/5.2/ref/signals/)
    is explicit that a receiver must not query or modify other records then: the instance
    carries only its own local fields, and the rows it points at may not have been loaded
    yet. A receiver that ignores this reads a half-built database, and either fails outright
    or, worse, succeeds with the wrong answer and persists it (issue #2548).

    Wrap every save receiver that reads or writes anything besides the instance being saved,
    or that queues work which will. Two kinds are deliberately left unwrapped, so that the
    split between them is a rule rather than an accident:

    * those that only clear a cache. A fixture load is exactly when a cached list of ranks,
      rarities or site config should be thrown away, so skipping it would leave the deck
      serving values the load has already replaced.
    * those that only adjust the instance on its way to the database. That is what pre_save
      is for, it touches nothing else, and a raw load wants it applied the same as any
      other save.

    ``raw`` reaches pre_save and post_save only, so a receiver connected to post_delete or
    pre_delete has nothing to skip: loaddata never deletes. A receiver connected to both
    (several are) still wraps safely, because the delete half never sets ``raw``.

    Apply it *below* ``@receiver``, so that the wrapper is the thing connected to the signal:

        @receiver(post_save, sender=Thing)
        @disable_for_loaddata
        def thing_saved(instance, **kwargs):
            ...

    Args:
        signal_handler: the receiver to wrap.

    Returns:
        The receiver, wrapped so that it returns immediately on a raw save. The wrapper
        carries `disabled_for_loaddata = True`, which is what the audit in
        `utilities.tests.test_signals` reads to check the rule has been applied everywhere
        it should be.
    """
    @wraps(signal_handler)
    def wrapper(*args, **kwargs):
        if kwargs.get('raw'):
            return None
        return signal_handler(*args, **kwargs)

    wrapper.disabled_for_loaddata = True
    return wrapper
