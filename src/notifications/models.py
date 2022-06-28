from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags
from bs4 import BeautifulSoup

from tenant.utils import get_root_url

from .signals import notify

# Create your models here.


class UserNotificationOptionSet(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    quest_approved_without_comment = models.BooleanField(default=True)


class NotificationQuerySet(models.query.QuerySet):
    def get_user(self, recipient):
        return self.filter(recipient=recipient)

    # object matching sender, target or action object
    def get_object_anywhere(self, object):
        object_type = ContentType.objects.get_for_model(object)
        return self.filter(Q(target_content_type__pk=object_type.id,
                             target_object_id=object.id)
                           | Q(sender_content_type__pk=object_type.id,
                               sender_object_id=object.id)
                           | Q(action_content_type__pk=object_type.id,
                               action_object_id=object.id)
                           )

    def get_object_target(self, object):
        object_type = ContentType.objects.get_for_model(object)
        return self.filter(target_content_type__pk=object_type.id,
                           target_object_id=object.id)

    # def mark_targetless(self, recipient):
    #     qs = self.get_unread().get_user(recipient)
    #     qs_no_target = qs.filter(target_object_id=None)
    #     if qs_no_target:
    #         qs_no_target.update(unread=False)

    def mark_all_read(self, recipient):
        qs = self.get_unread().get_user(recipient)
        qs.update(unread=False)
        qs.update(time_read=timezone.now())

    def mark_all_unread(self, recipient):
        qs = self.get_read().get_user(recipient)
        qs.update(unread=True)
        qs.update(time_read=None)

    def get_unread(self):
        return self.filter(unread=True)

    def get_read(self):
        return self.filter(unread=False)

    def recent(self):
        return self.get_unread()[:5]  # last five


class NotificationManager(models.Manager):
    def get_queryset(self):
        return NotificationQuerySet(self.model, using=self._db).order_by('-timestamp')

    def all_unread(self, user):
        return self.all_for_user(user).get_unread()

    def all_read(self, user):
        return self.get_queryset().get_user(user).get_read()

    def all_for_user(self, user):
        # self.get_queryset().mark_targetless(user)
        return self.get_queryset().get_user(user)

    def get_user_target(self, user, target):
        # should only have one element?
        # ? Why only one?  Could have several?
        return self.get_queryset().get_user(user).get_object_target(target).first()

    def all_for_user_target(self, user, target):
        return self.get_queryset().get_user(user).get_object_target(target)

    def get_user_target_unread(self, user, target):
        # should be only one, first will convert from queryset to notification
        notification = self.get_queryset().get_user(user).get_object_target(target).first()
        if notification:
            return notification.unread
        else:
            return None


class Notification(models.Model):
    sender_content_type = models.ForeignKey(ContentType, related_name='notify_sender', on_delete=models.CASCADE)
    sender_object_id = models.PositiveIntegerField()
    sender_object = GenericForeignKey("sender_content_type", "sender_object_id")

    verb = models.CharField(max_length=255)

    action_content_type = models.ForeignKey(ContentType, related_name='notify_action',
                                            null=True, blank=True, on_delete=models.SET_NULL)
    action_object_id = models.PositiveIntegerField(null=True, blank=True)
    action_object = GenericForeignKey("action_content_type", "action_object_id")

    target_content_type = models.ForeignKey(ContentType, related_name='notify_target',
                                            null=True, blank=True, on_delete=models.SET_NULL)
    target_object_id = models.PositiveIntegerField(null=True, blank=True)
    target_object = GenericForeignKey("target_content_type", "target_object_id")

    font_icon = models.CharField(max_length=255, default="<i class='fa fa-info-circle'></i>")

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='notifications', on_delete=models.CASCADE)

    timestamp = models.DateTimeField(auto_now_add=True, auto_now=False)

    unread = models.BooleanField(default=True)
    time_read = models.DateTimeField(null=True, blank=True)

    objects = NotificationManager()

    def html_strip(string, char_limit=50, tag_size=1, resize_image=True, image_height=20, **kwargs) -> str:
        """  
            Strips all html tags except img tags and imposes a length limit. Returns the input text without html tags save for img tag

            tag_size: how many letters an image should count as

            resize_image: enables image resizing
            image_height: image height after resizing in pixels
        """
        if not string:
            return ""
        if type(string) is not str:
            string = str(string)

        limit_imposed = False
        HTML_tags = []
        tag_index = []

        # store HTML tags and index to lists
        cache_open_index = None
        for index in range(len(string)):
            char = string[index]

            # check for open img
            if char == "<" and string[index:].startswith("<img"):
                cache_open_index = index
            
            # check for closed if open already found 
            elif cache_open_index is not None and char == ">":
                # position img tag would be without html tags
                offset = cache_open_index - len(strip_tags(string[:cache_open_index]))

                start = cache_open_index
                end = index + 1

                # save the html tag and index to list
                HTML_tags.append(string[start:end])
                tag_index.append(cache_open_index - offset)

                cache_open_index = None

        # dict of html tag and its position in the string
        html_index = {HTML_tags[i]: tag_index[i] for i in range(len(HTML_tags))}

        # index count of images that will be shown
        shown_tag_count = len([index for _, index in html_index.items() if index < char_limit])
        # tags should count towards the character limit
        char_limit -= shown_tag_count * tag_size

        # strip all the tags and apply char limit to TEXT
        stripped = strip_tags(string)
        text = stripped[:char_limit]
        limit_imposed = len(stripped) > char_limit
        
        # reinsert tags with new stripped text
        for tag, index in html_index.items():
            if index < char_limit:
                text = text[:index] + tag + text[index:]

        # resizes all images in string
        if resize_image:
            soup = BeautifulSoup(text, features="html.parser")
            for img in soup.findAll('img'):
                img['style'] = ""  # remove style as it always comes with width/height modifiers
                img['height'] = f"{image_height}px"
                img['width'] = "auto"

            text = str(soup)
            
        return text + ("..." if limit_imposed else "")

    def __str__(self):
        try:
            target_url = self.target_object.get_absolute_url()

            # Is this the right place to do this?
            if 'commented on' in self.verb:
                target_url += '#comment-{}'.format(self.action_object_id)
        except AttributeError:
            target_url = None

        action = self.action_object

        # uses custom strip
        action = Notification.html_strip(action)

        # absolute url needed for when notifications are sent via email
        root_url = get_root_url()
        context = {
            "sender": self.sender_object,
            "verb": self.verb,
            "action": action,  # notif text
            "target": self.target_object,  # basically quest name
            "verify_read": "{}{}".format(root_url, reverse('notifications:read', kwargs={"id": self.id})),
            "target_url": target_url,
        }

        url_common_part = "%(sender)s %(verb)s <a href='%(verify_read)s?next=%(target_url)s'>" % context
        if self.target_object:
            if self.action_object:
                url = url_common_part + ' <em>%(target)s</em> with "%(action)s"</a>' % context
            else:
                url = url_common_part + " <em>%(target)s</em></a>" % context
        else:
            url = url_common_part + "</a>"  # this is for 'teacher returned/approved ...'
        return url

    def mark_read(self):
        self.unread = False
        self.time_read = timezone.now()
        self.save()

    def get_url(self):
        # print("***** NOTIFICATION.get_url **********")
        try:
            target_url = self.target_object.get_absolute_url()
        except:  # noqa 
            # TODO make this except explicit, don't remember what it's doing
            target_url = reverse('notifications:list')

        context = {
            "verify_read": reverse('notifications:read', kwargs={"id": self.id}),
            "target_url": target_url
        }

        return "%(verify_read)s?next=%(target_url)s" % context

    def get_link(self):
        # print("***** NOTIFICATION.get_link **********")
        # try:
        #     target_url = self.target_object.get_absolute_url()
        # except:
        #     target_url = reverse('notifications:list')

        # if len(str(self.action_object)) > 50:
        #     action = str(self.action_object)[:50] + "..."
        # else:
        #     action = str(self.action_object)

        # action = strip_tags(action)

        action = Notification.html_strip(str(self.action_object))

        context = {
            "sender": self.sender_object,
            "verb": self.verb,
            "action": action,
            "target": self.target_object,
            # "verify_read": reverse('notifications:read', kwargs={"id":self.id}),
            # "target_url": target_url,
            "url": self.get_url(),
            "icon": self.font_icon
        }

        url_common_part = "<a href='%(url)s'>%(icon)s&nbsp;&nbsp; %(sender)s %(verb)s" % context
        if self.target_object:
            if self.action_object:
                url = url_common_part + ' <em>%(target)s</em> with "%(action)s"</a>' % context
            else:
                url = url_common_part + " <em>%(target)s</em></a>" % context
        else:
            url = url_common_part + "</a>"

        return url


def new_notification(sender, **kwargs):
    """
    Creates notification when a signal is sent with notify.send(sender, **kwargs)
    :param sender: the object (any Model) initiating/causing the notification
    :param kwargs:
        target (any Model): The object being notified about (Submission, Comment, BadgeAssertion, etc.)
        action (any Model): Not sure... not used I assume.
        recipient (User): The receiving User, required (but not used if affected_users are provided ...?)
        affected_users (list of Users): everyone who should receive the notification
        verb (string): sender 'verb' [target] [action]. E.g MrC 'commented on' SomeAnnouncement
        icon (html string): e.g.:
            "<span class='fa-stack'>" + \
               "<i class='fa fa-comment-o fa-flip-horizontal fa-stack-1x'></i>" + \
               "<i class='fa fa-ban fa-stack-2x text-danger'></i>" + \
            "</span>"
    :return:
    """
    # signal = kwargs.pop('signal', None)
    kwargs.pop('signal', None)
    recipient = kwargs.pop('recipient')  # required
    verb = kwargs.pop('verb')  # required
    icon = kwargs.pop('icon', "<i class='fa fa-info-circle'></i>")
    affected_users = kwargs.pop('affected_users', [recipient, ])

    # try:
    #     affected_users = kwargs.pop('affected_users')
    # except:
    #     affected_users = [recipient, ]

    if affected_users is None:
        affected_users = [recipient, ]

    for u in affected_users:
        # don't send a notification to yourself/themself
        if u == sender:
            pass
        else:
            new_note = Notification(
                recipient=u,
                verb=verb,
                sender_content_type=ContentType.objects.get_for_model(sender),
                sender_object_id=sender.id,
                font_icon=icon,
            )
            # Set the target if provided.  Action not currently used...
            for option in ("target", "action"):
                # obj = kwargs.pop(option, None) #don't want to remove option with pop
                try:
                    obj = kwargs[option]
                    if obj is not None:
                        setattr(new_note, "%s_content_type" % option, ContentType.objects.get_for_model(obj))
                        setattr(new_note, "%s_object_id" % option, obj.id)
                except:  # noqa 
                    # TODO make this except explicit, don't remember what it's doing
                    pass
            new_note.save()


notify.connect(new_notification)


def deleted_object_receiver(sender, **kwargs):
    # Printing was causing and ASCII/Unicode error on the production server...I think
    # print("************delete signal ****************")
    # print(sender)
    # print(kwargs)
    object = kwargs["instance"]
    # print(object)
    Notification.objects.get_queryset().get_object_anywhere(object).delete()
