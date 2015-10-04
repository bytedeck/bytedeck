from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.urlresolvers import reverse
from django.db import models
from django.utils.html import urlize

from bs4 import BeautifulSoup

# from quest_manager.models import Quest

# Create your models here.
class CommentQuerySet(models.query.QuerySet):
    def get_user(self, recipient):
        return self.filter(recipient=recipient)

    def get_object_target(self, object):
        object_type = ContentType.objects.get_for_model(object)
        return self.filter(target_content_type__pk = object_type.id,
                            target_object_id = object.id)

    def get_no_parents(self):
        return self.filter(parent=None)

    def get_not_flagged(self):
        return self.filter(flagged=False)


class CommentManager(models.Manager):
    def get_queryset(self):
        qs = CommentQuerySet(self.model, using=self._db)
        return qs.select_related('user')

    def all_with_target_object(self, object):
        return self.get_queryset().get_object_target(object).get_no_parents()

    # def all(self):
    #     return self.get_queryset.get_active().get_no_parents()

    def create_comment(self, user=None, text=None, path=None, target=None, parent=None):
        if not path:
            raise ValueError("Must include a path when adding a comment")
        if not user:
            raise ValueError("Must include a user  when adding a comment")

        # format unformatted links
        # https://djangosnippets.org/snippets/2072/

        soup = BeautifulSoup(text, "html.parser")
        # soup = BeautifulSoup(text)
        print("*****BEFORE***")
        print(soup)

        # finalFragments = []
        # textNodes = soup.findAll(text=True)
        # for textNode in textNodes:
        #     if getattr(textNode.parent, 'name') == 'a':
        #         finalFragments.append(str(textNode.parent))
        #     else:
        #         finalFragments.append(urlize(textNode))
        #
        # text = str("".join(finalFragments))

        textNodes = soup.findAll(text=True)
        for textNode in textNodes:
            if textNode.parent and getattr(textNode.parent, 'name') == 'a':
                continue  # skip already formatted links
            urlizedText = urlize(textNode, trim_url_limit = 50)
            textNode.replaceWith(BeautifulSoup(urlizedText, "html.parser"))
        text = str(soup)


        print("*****AFTER***")
        print(text)

        # text = str(soup)

        comment = self.model(
            user = user,
            path = path,
            text = text,
        )
        if target is not None:
            comment.target_content_type = ContentType.objects.get_for_model(target)
            comment.target_object_id = target.id
        # if quest is not None:
        #     comment.quest = quest

        if parent is not None:
            comment.parent = parent

        comment.save(using=self._db)
        return comment

class Comment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    parent = models.ForeignKey("self", null=True, blank=True)
    path = models.CharField(max_length=350)
    # quest = models.ForeignKey(Quest, null=True, blank=True)
    text = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    active = models.BooleanField(default=True)
    flagged = models.BooleanField(default=False)

    target_content_type = models.ForeignKey(ContentType, related_name='comment_target',
        null=True, blank=True)
    target_object_id = models.PositiveIntegerField(null=True, blank=True)
    target_object = GenericForeignKey("target_content_type", "target_object_id")

    objects = CommentManager()

    class Meta:
        ordering  = ['-timestamp']

    def __str__(self):
        return self.text

    def get_target_object(self):
        if self.target_object_id is not None:
            return self.target_content_type.get_object_for_this_type(id = self.target_object_id)
        else:
            return None

    def get_absolute_url(self):
        return reverse('comments:threads', kwargs={'id': self.id})

    def get_origin(self):
        return self.path

    def is_child(self):
        if self.parent is not None:
            return True
        else:
            return False

    def flag(self):
        self.flagged=True;
        self.save()

    def unflag(self):
        self.flagged=False;
        self.save()

    def get_children(self):
        if self.is_child():
            return None
        else:
            return Comment.objects.filter(parent=self)

    def get_affected_users(self):
        # it needs to be a parent and have children, which are the affected users
        comment_children = self.get_children()
        if comment_children is not None:
            users=[]
            for comment in comment_children:
                if comment.user in users:
                    pass
                else:
                    users.append(comment.user)
            return users
        else:
            return None

##### Document Handler ############################################
class Document(models.Model):
    docfile = models.FileField(upload_to='documents/%Y/%m/%d')
    comment = models.ForeignKey(Comment)


from notifications.models import Notification, deleted_object_receiver
from django.db.models.signals import pre_delete
pre_delete.connect(deleted_object_receiver, sender=Comment)
