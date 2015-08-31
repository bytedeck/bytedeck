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


class PrereqManager(models.Manager):
    def get_queryset(self):
        return PrereqQuerySet(self.model, using=self._db)

    def all_parent(self, parent_object):
        return self.get_queryset().get_all_parent_object(parent_object)

    def all_conditions_met(self, parent_object, user):
        # qs = self.all_parent(parent_object)
        print("checking prereq conditions!!!!!!!!")
        for prereq in self.all_parent(parent_object):
            if not prereq.condition_met_as_prerequisite(user):
                print("failed prereq condition!!!!!!!!")
                return False
        return True


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

    # @staticmethod
    # def autocomplete_search_fields():
    #     return ("name__icontains",)

    def condition_met_as_prerequisite(self, user):
        print("checking prereq #" + str(self.id))
        prereq_object = self.prereq_content_type.get_object_for_this_type(pk=self.prereq_object_id)
        main_condition_met = prereq_object.condition_met_as_prerequisite(user, self.prereq_count)

        if self.prereq_invert:
            main_condition_met = not main_condition_met

        if not self.or_prereq_object_id or not self.or_prereq_content_type:
            return main_condition_met

        print("checking OR prereq #" + str(self.id))
        or_prereq_object = self.or_prereq_content_type.get_object_for_this_type(pk=self.or_prereq_object_id)
        or_condition_met = or_prereq_object.condition_met_as_prerequisite(user, self.or_prereq_count)

        if self.or_prereq_invert:
            or_condition_met = not or_condition_met

        return main_condition_met or or_condition_met
