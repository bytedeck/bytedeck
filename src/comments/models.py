from django.conf import settings
from django.db import models

from quest_manager.models import Quest

# Create your models here.


class CommentManager(models.Manager):
    def create_comment(self, user=None, text=None, path=None, quest=None):
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
        comment.save(using=self._db)
        return user

class Comment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    path = models.CharField(max_length=350)
    quest = models.ForeignKey(Quest, null=True, blank=True)
    text = models.TextField()
    timestamp = models.DateTimeField(auto_now=True, auto_now_add=False)
    updated = models.DateTimeField(auto_now=False, auto_now_add=True)
    active = models.BooleanField(default=True)


    objects = CommentManager()

    def __str__(self):
        return self.user.username
