"""The serialization the Shared Library uses to move quests between decks.

Sharing a quest to the Library, and importing one back down into a deck, both work by
serializing the quest in one schema and deserializing it in another. That contract is
the Library's, and it lives here so that improving it is a change to the Library rather
than a change to the Django admin (#2378).

The two features that serialize quests want different things:

* The **admin's** CSV export is a table dump for a human to read, so it deliberately
  drops the bulky summernote HTML columns (`QuestAdminExportResource`, for the
  per-request memory reasons in #2081).
* The **Library** is copying the quest itself, so those same columns are the point: a
  quest that arrives without its instructions is not the quest.

Keeping them apart means the fidelity work queued up for the Library (tags, #1792;
submission questions, #2162; competency links, #1915) lands in the library app instead
of in `quest_manager.admin`, where it would be coupled to a feature that wants the
opposite.
"""

from quest_manager.admin import QuestResource


class LibraryQuestResource(QuestResource):
    """Full-fidelity quest serialization for cross-deck sharing.

    Subclasses the admin's `QuestResource` because the base contract (match rows on
    `import_id`, exclude the local-only foreign keys `editor`,
    `specific_teacher_to_notify` and `common_data`, carry the campaign and simple
    prerequisites as import_ids) is genuinely shared, and duplicating it would leave two
    definitions to keep in step.

    What this class exists for is the *other* direction: it is the seam the Library's own
    fidelity requirements attach to. Anything the Library needs to carry that the admin's
    CSV round-trip does not (or must not) belongs here rather than on the base class.

    Every quest field this resource exports must survive the round trip, so it never
    inherits from `QuestAdminExportResource`, whose whole purpose is to leave fields out.
    """
