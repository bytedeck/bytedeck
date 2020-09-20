from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.signals import pre_delete
from django.urls import reverse
from django.utils import timezone

from comments.models import Comment
from notifications.models import deleted_object_receiver


class AnnouncementQuerySet(models.query.QuerySet):
    def released(self):
        # "__lte" appended to the object means less than or equal to
        return self.filter(datetime_released__lte=timezone.now())

    def not_archived(self):
        return self.filter(archived=False)

    def not_draft(self):
        return self.filter(draft=False)

    def not_expired(self):
        return self.filter(Q(datetime_expires=None) | Q(datetime_expires__gt=timezone.now()))


class AnnouncementManager(models.Manager):
    def get_queryset(self):
        return AnnouncementQuerySet(self.model, using=self._db)

    def get_active(self):
        return self.get_queryset().not_archived().order_by('-sticky', '-datetime_released')

    def get_for_students(self):
        return self.get_active().not_draft().not_expired().released()


class Announcement(models.Model):
    title = models.CharField(max_length=80)
    datetime_released = models.DateTimeField(
        default=timezone.now,
        help_text="The time the announcement was published.  If auto_publish is True, then the announcement will automatically \
        be published at this time."
    )
    auto_publish = models.BooleanField(
        default=False,
        help_text="When set to true, the announcement will publish itself on the date and time indicated."
    )
    content = models.TextField()
    datetime_created = models.DateTimeField(auto_now_add=True, auto_now=False)
    datetime_last_edit = models.DateTimeField(auto_now_add=False, auto_now=True)
    sticky = models.BooleanField(default=False)
    sticky_until = models.DateTimeField(null=True, blank=True, help_text='blank = sticky never expires')
    icon = models.ImageField(upload_to='announcement_icons/', null=True, blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    datetime_expires = models.DateTimeField(null=True, blank=True, help_text='blank = never')
    draft = models.BooleanField(default=True,
                                help_text="note that announcements previously saved as drafts will only send out a  \
                                notification if they are published using the Publish button on the Announcements main \
                                page")
    archived = models.BooleanField(default=False)

    objects = AnnouncementManager()

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        # return reverse('announcements:list')
        return reverse('announcements:list', kwargs={'ann_id': self.id})

    def get_comments(self):
        return Comment.objects.all_with_target_object(self)

    def not_yet_released(self):
        return self.datetime_released > timezone.now()


pre_delete.connect(deleted_object_receiver, sender=Announcement)
