from django.conf import settings
from django.core.urlresolvers import reverse
from django.db import models
from django.db.models import Q
from django.utils import timezone

# Create your models here.
class AnnouncementQuerySet(models.query.QuerySet):
    def sticky(self):
        return self.filter(sticky=True)

    def released(self):
        # "__lte" appended to the object means less than or equla to
        return self.filter(datetime_released__lte = timezone.now)

    def not_expired(self):
        return self.filter(Q(datetime_expires = None) | Q(datetime_expires__gt = timezone.now) )

class AnnouncementManager(models.Manager):
    def get_queryset(self):
        return AnnouncementQuerySet(self.model, using=self._db)

    def get_sticky(self):
        #Announcement.objects.filter(condition)
        #return super(AnnouncementManager, self).filter(sticky=True)
        return self.get_active().sticky()

    def get_active(self):
        return self.get_queryset().released().not_expired()

class Announcement(models.Model):
    title = models.CharField(max_length=50, null=False, blank=False)
    content = models.TextField()
    datetime_created = models.DateTimeField(auto_now_add=True, auto_now=False)
    datetime_last_edit = models.DateTimeField(auto_now_add=False, auto_now=True)
    sticky = models.BooleanField(default = False, null=False)
    icon = models.ImageField(upload_to='announcement_icons/', null=True, blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=False)
    datetime_released = models.DateTimeField(default=timezone.now)
    datetime_expires = models.DateTimeField(null=True, blank=True, help_text = 'blank = never')

    # def get_absolute_url(self):
    #     return reverse('profile_detail', kwargs={'pk': self.pk})

    objects = AnnouncementManager()

    def __str__(self):
        return str(self.id) + ": " + str(self.title)

    def get_absolute_url(self):
        return reverse('announcements:list')
