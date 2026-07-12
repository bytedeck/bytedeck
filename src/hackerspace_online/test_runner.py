"""Custom test runner that installs model_bakery safety patches for the suite.

The only customization over Django's default ``DiscoverRunner`` is that it
applies :func:`patch_baker_make_for_prereq` once, before any tests run, to keep
``baker.make(Prereq)`` from producing the flaky ``Rank.DoesNotExist`` failure
described in that function's docstring.
"""

import functools

from django.test.runner import DiscoverRunner


# (generic-fk field, content-type field, object-id field) for each *non-nullable*
# GenericForeignKey on Prereq. ``or_prereq_*`` is nullable, so model_bakery leaves
# it None by default (no dangling relation) and it is intentionally omitted here.
_PREREQ_GFK_FIELDS = (
    ("parent_object", "parent_content_type", "parent_object_id"),
    ("prereq_object", "prereq_content_type", "prereq_object_id"),
)

_patched = False


def patch_baker_make_for_prereq():
    """Wrap ``baker.make`` so Prereqs are built with *real* GenericForeignKey targets.

    Why this is needed
    ------------------
    ``Prereq`` links to other objects through GenericForeignKeys
    (``parent_object``, ``prereq_object``, ``or_prereq_object``). When a test
    calls ``baker.make(Prereq)`` without specifying those, model_bakery fills each
    GFK's ``content_type`` with a *random* installed model (it ignores the field's
    ``limit_choices_to``) and its ``object_id`` with a *random* integer, so the
    generic relation points at an object that does not exist.

    Saving such a Prereq fires the prerequisite ``post_save`` signals. When the
    random ``prereq_content_type`` happens to be ``Rank`` *and* the parent is a
    ``HasPrereqsMixin`` model, ``on_quest_badge_save_with_rank_prereq`` runs
    ``Rank.objects.get(id=<random id>)`` and raises ``Rank.DoesNotExist`` — a test
    failure that only appears on the unlucky random draws (see PRs #1897 / #1903).

    What this patch does
    --------------------
    It wraps ``baker.make`` so that, for ``Prereq``, any GenericForeignKey the
    caller did not specify is pointed at a real, saved ``Badge`` instance. ``Badge``
    is chosen deliberately:

    * it is a registered ``IsAPrereqMixin`` model, so it is a valid prerequisite;
    * it is not a ``Rank``, so the rank-map signal short-circuits without a DB
      lookup; and
    * its own save signals do not enqueue ``update_conditions_for_quest``, so it
      will not perturb the signal-call-count assertions in the prerequisites tests.

    Using a deterministic ``Badge`` (rather than a random registered model) makes
    the suite reproducible instead of merely "less flaky". Callers that pass an
    explicit ``prereq_object`` / ``parent_object`` (or the underlying
    ``*_content_type`` / ``*_object_id``) are left completely untouched.

    The patch is idempotent and is installed once by :class:`BytedeckTestRunner`.
    """
    global _patched
    if _patched:
        return
    _patched = True

    from model_bakery import baker

    original_make = baker.make

    @functools.wraps(original_make)
    def make(model, *args, **kwargs):
        if _is_prereq_model(model):
            _fill_prereq_generic_targets(original_make, kwargs)
        return original_make(model, *args, **kwargs)

    baker.make = make


def _is_prereq_model(model):
    """Return True if ``model`` refers to the Prereq model (class or "app.Model" str)."""
    from prerequisites.models import Prereq

    if isinstance(model, str):
        # baker accepts "app_label.ModelName" or "ModelName"
        return model.split(".")[-1].lower() == "prereq"
    return model is Prereq


def _fill_prereq_generic_targets(original_make, kwargs):
    """Point each unspecified non-null Prereq GFK at a real Badge instance."""
    from badges.models import Badge

    for gfk_field, ct_field, oid_field in _PREREQ_GFK_FIELDS:
        if gfk_field in kwargs or ct_field in kwargs or oid_field in kwargs:
            continue  # caller specified this relation explicitly; leave it alone
        # original_make (not the wrapped make) avoids re-entering this function.
        kwargs[gfk_field] = original_make(Badge)


class BytedeckTestRunner(DiscoverRunner):
    """Django's default runner plus the model_bakery Prereq safety patch."""

    def setup_test_environment(self, **kwargs):
        """Set up the default test environment, then install the baker patch."""
        super().setup_test_environment(**kwargs)
        patch_baker_make_for_prereq()
