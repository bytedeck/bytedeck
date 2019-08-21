from djconfig import config

from comments.models import Comment

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from django.db import models
from django.db.models import Q
from django.utils import timezone

from notifications.models import deleted_object_receiver
from django.db.models.signals import pre_delete


class AnnouncementQuerySet(models.query.QuerySet):
    def sticky(self):
        return self.filter(sticky=True)

    def not_sticky(self):
        return self.filter(sticky=False)

    def released(self):
        # "__lte" appended to the object means less than or equal to
        return self.filter(datetime_released__lte=timezone.now())

    def not_draft(self):
        return self.filter(draft=False)

    def not_expired(self):
        return self.filter(Q(datetime_expires=None) | Q(datetime_expires__gt=timezone.now()))


class AnnouncementManager(models.Manager):
    def get_queryset(self):
        return AnnouncementQuerySet(self.model, using=self._db)

    def get_sticky(self):
        return self.get_active().sticky()

    def get_not_sticky(self):
        return self.get_active().not_sticky()

    def get_active(self):
        return self.get_queryset().order_by('-sticky', '-datetime_released')

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

    def send_by_mail(self):
        subject = "Test email from " + config.hs_site_name
        from_email = (config.hs_site_name + " <" + settings.EMAIL_HOST_USER + ">")
        to_emails = [from_email]
        email_message = "from %s: %s via %s" % ("Dear Bloggins", "sup", from_email)

        html_email_message = "<h1> if this is showing you received an HTML message</h1>"

        send_mail(subject,
                  email_message,
                  from_email,
                  to_emails,
                  html_message=html_email_message,
                  fail_silently=False)


pre_delete.connect(deleted_object_receiver, sender=Announcement)
