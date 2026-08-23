from django.db import migrations, models

# Delete duplicates in bounded batches so a deck with a pathological number of
# duplicate rows can't produce an unbounded pk__in list in a single query.
DEDUP_BATCH_SIZE = 500


def remove_duplicate_unstamped_in_progress_submissions(apps, schema_editor):
    """Delete duplicate never-yet-completed in-progress submissions that belong to
    no semester, before adding the unique constraint covering them (issue #2413).

    Migration 0049 added the same rule for submissions that name a semester, and
    deliberately left the NULL-semester rows alone: Postgres treats NULLs as
    distinct, so its partial index could never see two of them as duplicates. Those
    rows are reachable on any deck (``QuestSubmission.semester`` is
    ``on_delete=SET_NULL``, and work handed in while the student is in no semester
    is stamped with none), so dedup them the same way here: keep the earliest
    (lowest pk) of each ``(user, quest)`` group and delete the rest.

    Untouched, exactly as in 0049 (they can't violate the partial index):
    - completed submissions;
    - *returned* submissions (``is_completed=False`` but ``first_time_completed``
      set), which are a legitimate state alongside a new in-progress attempt;
    - rows that name a semester, which 0049's constraint already covers.
    """
    QuestSubmission = apps.get_model("quest_manager", "QuestSubmission")
    db_alias = schema_editor.connection.alias

    # ``seen`` is bounded by the number of distinct never-completed in-progress
    # (user, quest) groups with no semester, which is small in practice; deletes are
    # flushed in DEDUP_BATCH_SIZE chunks so no single query gets an unbounded
    # pk__in list.
    seen = set()
    duplicate_pks = []
    unstamped_in_progress = (
        QuestSubmission.objects.using(db_alias)
        .filter(is_completed=False, first_time_completed__isnull=True, semester__isnull=True)
        .order_by("pk")
        .values_list("pk", "user_id", "quest_id")
        # Clear any prefetch the active manager may have added (QuestSubmission's
        # default manager prefetches quest__tags): this scan only reads scalar
        # tuples, and since Django 5.1 iterator() raises if the queryset carries
        # a prefetch_related() without an explicit chunk_size. A real migration
        # uses the historical (plain) manager and has nothing to clear; this keeps
        # the scan correct if the concrete manager is ever used instead.
        .prefetch_related(None)
    )
    for pk, user_id, quest_id in unstamped_in_progress.iterator():
        key = (user_id, quest_id)
        if key in seen:
            duplicate_pks.append(pk)
            if len(duplicate_pks) >= DEDUP_BATCH_SIZE:
                QuestSubmission.objects.using(db_alias).filter(pk__in=duplicate_pks).delete()
                duplicate_pks = []
        else:
            seen.add(key)

    if duplicate_pks:
        QuestSubmission.objects.using(db_alias).filter(pk__in=duplicate_pks).delete()


class Migration(migrations.Migration):
    """Add the partial unique constraint that blocks concurrent double-starts of a quest
    handed in outside any semester (issue #2413), first deduplicating the existing
    unstamped in-progress rows so the constraint can be installed on existing decks."""

    dependencies = [
        ("quest_manager", "0053_questsubmission_course"),
    ]

    operations = [
        migrations.RunPython(
            remove_duplicate_unstamped_in_progress_submissions,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="questsubmission",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("is_completed", False),
                    ("first_time_completed__isnull", True),
                    ("semester__isnull", True),
                ),
                fields=("user", "quest"),
                name="unique_inprogress_submission_per_quest_no_semester",
            ),
        ),
    ]
