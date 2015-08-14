from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.urlresolvers import reverse
from django.db import models

from .signals import notify
# Create your models here.

class NotificationQuerySet(models.query.QuerySet):
    def get_user(self, recipient):
        return self.filter(recipient=recipient)

    def mark_targetless(self, recipient):
        qs = self.unread().get_user(recipient)
        qs_no_target = qs.filter(target_object_id = None)
        if qs_no_target:
            qs_no_target.update(unread=False)

    def mark_all_read(self, recipient):
        qs = self.unread().get_user(recipient)
        qs.update(unread=False)

    def mark_all_unread(self, recipient):
        qs = self.read().get_user(recipient)
        qs.update(unread=True)

    def unread(self):
        return self.filter(unread=True)

    def read(self):
        return self.filter(unread=False)

    def recent(self):
        return self.unread()[:5] #last five

class NotificationManager(models.Manager):
    def get_queryset(self):
        return NotificationQuerySet(self.model, using=self._db)

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
        if self.target_object:
            return "<a href='%(verify_read)s?next=%(target_url)s'>%(sender)s %(verb)s %(target)s with %(action)s</a>" % context
        else:
            "<a href='%(verify_read)s?next=%(target_url)s'>%(sender)s %(verb)s</a>" % context



def new_notification(sender, **kwargs):
    signal = kwargs.pop('signal', None)
    recipient = kwargs.pop('recipient')
    verb = kwargs.pop('verb')
    affected_users = kwargs.pop('affected_users')

    if affected_users is None:
        affected_users = [recipient,]

    for u in affected_users:
        print(u)
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
