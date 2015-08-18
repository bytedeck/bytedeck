from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.urlresolvers import reverse
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .signals import notify
# Create your models here.

class NotificationQuerySet(models.query.QuerySet):
    def get_user(self, recipient):
        return self.filter(recipient=recipient)

    #object matching sender, target or action object
    def get_object_anywhere(self, object):
        object_type = ContentType.objects.get_for_model(object)
        qs = self.filter(Q(target_content_type__pk = object_type.id,
                        target_object_id = object.id)
                        | Q(sender_content_type__pk = object_type.id,
                                        sender_object_id = object.id)
                        | Q(action_content_type__pk = object_type.id,
                                        action_object_id = object.id)
                        )
        qs.delete()

    def mark_targetless(self, recipient):
        qs = self.unread().get_user(recipient)
        qs_no_target = qs.filter(target_object_id = None)
        if qs_no_target:
            qs_no_target.update(unread=False)

    def mark_all_read(self, recipient):
        qs = self.unread().get_user(recipient)
        qs.update(unread=False)
        qs.update(time_read=timezone.now())

    def mark_all_unread(self, recipient):
        qs = self.read().get_user(recipient)
        qs.update(unread=True)
        qs.update(time_read=None)

    def unread(self):
        return self.filter(unread=True)

    def read(self):
        return self.filter(unread=False)

    def recent(self):
        return self.unread()[:5] #last five

class NotificationManager(models.Manager):
    def get_queryset(self):
        return NotificationQuerySet(self.model, using=self._db).order_by('-timestamp')

    def all_unread(self, user):
        return self.get_queryset().get_user(user).unread()

    def all_read(self, user):
        return self.get_queryset().get_user(user).read()

    def all_for_user(self, user):
        self.get_queryset().mark_targetless(user)
        return self.get_queryset().get_user(user)

class Notification(models.Model):

    sender_content_type = models.ForeignKey(ContentType, related_name='notify_sender')
    sender_object_id = models.PositiveIntegerField()
    sender_object = GenericForeignKey("sender_content_type", "sender_object_id")

    verb = models.CharField(max_length=255)

    action_content_type = models.ForeignKey(ContentType, related_name='notify_action',
        null=True, blank=True)
    action_object_id = models.PositiveIntegerField(null=True, blank=True)
    action_object = GenericForeignKey("action_content_type", "action_object_id")

    target_content_type = models.ForeignKey(ContentType, related_name='notify_target',
        null=True, blank=True)
    target_object_id = models.PositiveIntegerField(null=True, blank=True)
    target_object = GenericForeignKey("target_content_type", "target_object_id")

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='notifications')

    timestamp = models.DateTimeField(auto_now_add=True, auto_now=False)

    unread = models.BooleanField(default=True)
    time_read = models.DateTimeField(null=True, blank = True)


    objects = NotificationManager()


    def __str__(self):
        try:
            target_url = self.target_object.get_absolute_url()
        except:
            target_url = None
        context = {
            "sender":self.sender_object,
            "verb":self.verb,
            "action":self.action_object,
            "target": self.target_object,
            "verify_read": reverse('notifications:read', kwargs={"id":self.id}),
            "target_url": target_url,
        }

        if self.target_object:
            if self.action_object and target_url:
                return "%(sender)s %(verb)s <a href='%(verify_read)s?next=%(target_url)s'>%(target)s</a> with %(action)s" % context
            if self.action_object and not target_url:
                return "%(sender)s %(verb)s %(target)s with %(action)s" % context
            return "%(sender)s %(verb)s %(target)s" % context
        return "%(sender)s %(verb)s" % context

    def get_link(self):
        try:
            target_url = self.target_object.get_absolute_url()
        except:
            target_url = reverse('notifications:list')

        act = str(self.action_object)[:30]
        context = {
            "sender":self.sender_object,
            "verb":self.verb,
            "action":act,
            "target": self.target_object,
            "verify_read": reverse('notifications:read', kwargs={"id":self.id}),
            "target_url": target_url,
        }

        url_common_part = "<a href='%(verify_read)s?next=%(target_url)s'>%(sender)s %(verb)s" % context
        if self.target_object:
            if self.action_object:
                url = url_common_part + "%(target)s with %(action)s</a>" % context
            else:
                url = url_common_part + "%(target)s</a>" % context
        else:
            url = url_common_part + "</a>"
        return url

def new_notification(sender, **kwargs):
    signal = kwargs.pop('signal', None)
    recipient = kwargs.pop('recipient')
    verb = kwargs.pop('verb')

    try:
        affected_users = kwargs.pop('affected_users')
    except:
        affected_users = [recipient,]

    if affected_users is None:
        affected_users = [recipient,]

    for u in affected_users:
        if u == sender:
            pass
        else:
            new_note = Notification(
                recipient = u,
                verb = verb,
                sender_content_type = ContentType.objects.get_for_model(sender),
                sender_object_id = sender.id,
                )
            for option in ("target", "action"):
                # obj = kwargs.pop(option, None) #don't want to remove option with pop
                try:
                    obj = kwargs[option]
                    if obj is not None:
                        setattr(new_note, "%s_content_type" % option,  ContentType.objects.get_for_model(obj))
                        setattr(new_note, "%s_object_id" % option,  obj.id)
                except:
                    pass
            new_note.save()

notify.connect(new_notification)

from django.db.models.signals import pre_delete
from announcements.models import Announcement
from comments.models import Comment

def deleted_object_receiver(sender, **kwargs):
    print("************delete signal ****************")
    print(sender)
    print(kwargs)
    object = kwargs["instance"]
    print(object)
    Notification.objects.get_queryset().get_object_anywhere(object)

pre_delete.connect(deleted_object_receiver, sender=Announcement)
pre_delete.connect(deleted_object_receiver, sender=Comment)
