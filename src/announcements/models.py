from django.conf import settings
from django.db import models
from django.utils import timezone
# Create your models here.

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

    def __str__(self):
        return str(self.id) + ": " + str(self.title)
