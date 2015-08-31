from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models


# Create your models here.
class PrereqQuerySet(models.query.QuerySet):
    def get_all_parent_object(self, parent_object):
        ct = ContentType.objects.get_for_model(parent_object)
        return self.filter(parent_content_type__pk = ct.id,
                        parent_object_id = parent_object.id)

    #object matching sender, target or action object
    # def get_object_anywhere(self, object):
    #     object_type = ContentType.objects.get_for_model(object)
    #     return self.filter(Q(target_content_type__pk = object_type.id,
    #                     target_object_id = object.id)
    #                     | Q(sender_content_type__pk = object_type.id,
    #                                     sender_object_id = object.id)
    #                     | Q(action_content_type__pk = object_type.id,
    #                                     action_object_id = object.id)
    #                     )
    #
    # def get_object_target(self,object):
    #     object_type = ContentType.objects.get_for_model(object)
    #     return self.filter(target_content_type__pk = object_type.id,
    #                     target_object_id = object.id)

class PrereqManager(models.Manager):
    def get_queryset(self):
        return PrereqQuerySet(self.model, using=self._db)

    def all_mine(self, parent_object):
        return self.get_queryset().get_all_parent_object(parent_object)

class Prereq(models.Model):
    parent_content_type = models.ForeignKey(ContentType, related_name='prereq_parent')
    parent_object_id = models.PositiveIntegerField()
    parent_object = GenericForeignKey("parent_content_type", "parent_object_id")

    prereq_content_type = models.ForeignKey(ContentType, related_name='prereq_item',
        verbose_name="Type of Prerequisite")
    prereq_object_id = models.PositiveIntegerField(verbose_name="Prerequisite")
    prereq_object = GenericForeignKey("prereq_content_type", "prereq_object_id")
    prereq_count = models.PositiveIntegerField(default=1)
    prereq_invert = models.BooleanField(default=False, verbose_name="NOT")

    or_prereq_content_type = models.ForeignKey(ContentType, related_name='or_prereq_item',
        verbose_name="OR Type of Prerequisite", blank=True, null=True)
    or_prereq_object_id = models.PositiveIntegerField(blank=True, null=True,
        verbose_name="OR Prerequisite")
    or_prereq_object = GenericForeignKey("or_prereq_content_type", "or_prereq_object_id")
    or_prereq_count = models.PositiveIntegerField(default=1)
    or_prereq_invert = models.BooleanField(default=False, verbose_name = 'OR NOT')

    objects = PrereqManager()

    def conditions_met(self):
        parent = self.prereq_content_type.get_object_for_this_type(pk=prereq_object_id)
        return parent
