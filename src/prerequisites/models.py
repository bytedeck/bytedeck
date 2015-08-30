from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models


# Create your models here.

class Prereq(models.Model):
    parent_content_type = models.ForeignKey(ContentType, related_name='prereq_parent')
    parent_object_id = models.PositiveIntegerField()
    parent_object = GenericForeignKey("parent_content_type", "parent_object_id")

    prereq_content_type = models.ForeignKey(ContentType, related_name='prereq_item',
        verbose_name="Type of Prerequisite")
    prereq_object_id = models.PositiveIntegerField(verbose_name="Prerequisite")
    prereq_object = GenericForeignKey("prereq_content_type", "prereq_object_id")
    prereq_invert = models.BooleanField(default=False, verbose_name="NOT")

    or_prereq_content_type = models.ForeignKey(ContentType, related_name='or_prereq_item',
        verbose_name="OR Type of Prerequisite", blank=True, null=True)
    or_prereq_object_id = models.PositiveIntegerField(blank=True, null=True,
        verbose_name="OR Prerequisite")
    or_prereq_object = GenericForeignKey("or_prereq_content_type", "or_prereq_object_id")
    or_prereq_invert = models.BooleanField(default=False, verbose_name = 'OR NOT')
