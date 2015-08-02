from django.conf import settings
from django.core.urlresolvers import reverse
from django.db import models

from quest_manager.models import Quest

# Create your models here.


class CommentManager(models.Manager):
    def all(self):
        return super(CommentManager, self).filter(active=True).filter(parent=None)

    def create_comment(self, user=None, text=None, path=None, quest=None, parent=None):
        if not path:
            raise ValueError("Must include a path when adding a comment")
        if not user:
            raise ValueError("Must include a user  when adding a comment")

        comment = self.model(
            user = user,
            path = path,
            text = text,
            quest = quest
        )
        if quest is not None:
            comment.quest = quest

        if parent is not None:
            comment.parent = parent

        comment.save(using=self._db)
        return comment

class Comment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    parent = models.ForeignKey("self", null=True, blank=True)
    path = models.CharField(max_length=350)
    quest = models.ForeignKey(Quest, null=True, blank=True)
    text = models.TextField()
    timestamp = models.DateTimeField(auto_now=True, auto_now_add=False)
    updated = models.DateTimeField(auto_now=False, auto_now_add=True)
    active = models.BooleanField(default=True)

    objects = CommentManager()

    class Meta:
        ordering  = ['-timestamp']

    def __str__(self):
        return self.user.username

    def get_absolute_url(self):
        return reverse('comments:threads', kwargs={'id': self.id})

    def get_origin(self):
        return self.path

    def is_child(self):
        if self.parent is not None:
            return True
        else:
            return False

    def get_children(self):
        if self.is_child():
            return None
        else:
            return Comment.objects.filter(parent=self)
