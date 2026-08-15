from django.db import models
from django.utils import timezone


class ContentOrigin(models.Model):
    """Where a piece of Shared Library content came from.

    Content is shared to the Library under CC BY-SA 4.0 (the sharer agrees to that on the
    export confirmation page), and attribution is the one thing that licence actually asks
    for. Nothing recorded who had pushed a quest or campaign, so there was nothing to
    attribute it to (#2377). This is that record.

    Rows live in the **library schema**, alongside the quests and campaigns they describe.
    The library app is a tenant app, so the table exists in every schema, but only the
    Library's copy is ever written to.

    Content is identified by `import_id` rather than by a foreign key because that is how
    the Library addresses content everywhere else: `import_id` is the one identifier that
    means the same thing in every deck's schema, and it survives the export/import round
    trip. The cost is that deleting a Library quest leaves its origin row behind; a stale
    row is harmless (nothing reads it without the matching content) and a later re-push of
    the same `import_id` overwrites it.
    """

    QUEST = 'quest'
    CAMPAIGN = 'campaign'
    CONTENT_TYPE_CHOICES = [
        (QUEST, 'Quest'),
        (CAMPAIGN, 'Campaign'),
    ]

    import_id = models.UUIDField(
        help_text="The import_id of the Library quest or campaign this describes."
    )
    content_type = models.CharField(
        max_length=10,
        choices=CONTENT_TYPE_CHOICES,
        help_text="Whether the import_id names a quest or a campaign. A quest and a campaign "
                  "could in principle carry the same import_id, so this is part of the identity."
    )
    deck_name = models.CharField(
        max_length=100,
        help_text="Name of the deck the content was shared from, as it was at the time of sharing."
    )
    deck_url = models.URLField(
        help_text="Root URL of the deck the content was shared from, so the attribution can link back."
    )
    shared_by = models.CharField(
        max_length=150,
        help_text="Username of the person who shared the content, on their own deck. Stored as text "
                  "rather than a User foreign key: the sharer is a user of another deck's schema, so "
                  "there is no row here to point at."
    )
    shared_on = models.DateTimeField(
        default=timezone.now,
        help_text="When the content was most recently shared to the Library. Re-sharing "
                  "refreshes it, so the date always belongs to the sharer named beside it."
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['import_id', 'content_type'],
                name='unique_origin_per_library_content',
            ),
        ]
        verbose_name = 'content origin'

    def __str__(self):
        """Describe the origin the way it reads as attribution.

        Returns:
            str: the content type, its import_id, and who shared it from where.
        """
        return f'{self.get_content_type_display()} {self.import_id} shared by {self.shared_by} of {self.deck_name}'

    @classmethod
    def record(cls, *, import_id, content_type, deck_name, deck_url, shared_by):
        """Record (or refresh) where a piece of Library content came from.

        Must be called from within the library schema context, since that is where the row
        belongs. Re-sharing the same content updates the existing row rather than adding a
        second one, so the attribution (including its date) always names the most recent push.

        Args:
            import_id (UUID): the import_id of the content in the Library.
            content_type (str): `ContentOrigin.QUEST` or `ContentOrigin.CAMPAIGN`.
            deck_name (str): name of the deck the content came from.
            deck_url (str): root URL of that deck.
            shared_by (str): username of the person who shared it.

        Returns:
            ContentOrigin: the stored origin.
        """
        origin, _ = cls.objects.update_or_create(
            import_id=import_id,
            content_type=content_type,
            defaults={
                'deck_name': deck_name,
                'deck_url': deck_url,
                'shared_by': shared_by,
                # Refreshed rather than left at the first push: the attribution names the
                # most recent sharer, so the date shown next to it has to be theirs too.
                'shared_on': timezone.now(),
            },
        )
        return origin

    @classmethod
    def for_content(cls, *, import_ids, content_type):
        """Look up the origins of several pieces of content at once.

        Must be called from within the library schema context.

        Args:
            import_ids (Iterable[UUID]): the import_ids to look up.
            content_type (str): `ContentOrigin.QUEST` or `ContentOrigin.CAMPAIGN`.

        Returns:
            dict[UUID, ContentOrigin]: origins keyed by import_id. Content shared before
            this was recorded simply has no entry, so callers show nothing for it rather
            than claiming an unknown author.
        """
        return {
            origin.import_id: origin
            for origin in cls.objects.filter(import_id__in=list(import_ids), content_type=content_type)
        }
