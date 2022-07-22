from django.db import models

from taggit.managers import TaggableManager


class TagsModelMixin(models.Model):
    """And abstract model to implement tags"""

    tags = TaggableManager(blank=True)

    class Meta:
        abstract = True
