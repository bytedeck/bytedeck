from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.base import ObjectDoesNotExist


class PrereqMixin:
    pass


class PrereqQuerySet(models.query.QuerySet):
    def get_all_for_parent_object(self, parent_object):
        ct = ContentType.objects.get_for_model(parent_object)
        return self.filter(parent_content_type__pk=ct.id,
                           parent_object_id=parent_object.id)

    def get_all_for_prereq_object(self, prereq_object):
        ct = ContentType.objects.get_for_model(prereq_object)
        return self.filter(prereq_content_type__pk=ct.id,
                           prereq_object_id=prereq_object.id)

    def get_all_for_or_prereq_object(self, prereq_object):
        ct = ContentType.objects.get_for_model(prereq_object)
        return self.filter(or_prereq_content_type__pk=ct.id,
                           or_prereq_object_id=prereq_object.id)

        # object matching sender, target or action object
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

    def all_conditions_met(self, parent_object, user, no_prereq_means=True):
        """
        Checks if all the prerequisites for this parent_object and user have been met.
        If the parent_object has no prerequisites, then return according to the no_prereq_means parameter
        """
        prereqs = self.all_parent(parent_object)
        if not prereqs:
            return no_prereq_means
        for prereq in prereqs:
            if not prereq.condition_met_as_prerequisite(user):
                return False
        return True


class Prereq(models.Model):
    """
    Links two (or three) objects (of any registered content type) in a prerequisite relationship
    parent: The owner of the prerequisite. Generally, for the parent to become 'active' the prereq_object conditions
        must be met.  'active' can mean whatever the user of this app wants it to mean.  It's a generic trigger.
    prereq: The object whose conditions must be met in order for the parent to become 'active', which optional
        additional conditions NOT and a number to indicate how many times the condition much be met.
    or_prereq: An optional alternate object who's condition can me met instead of prereq: prereq OR or_prereq
    """
    parent_content_type = models.ForeignKey(ContentType, related_name='prereq_parent')
    parent_object_id = models.PositiveIntegerField()
    parent_object = GenericForeignKey("parent_content_type", "parent_object_id")

    # the required prerequisite object and options
    prereq_content_type = models.ForeignKey(ContentType, related_name='prereq_item',
                                            verbose_name="Type of Prerequisite")
    prereq_object_id = models.PositiveIntegerField(verbose_name="Prerequisite")
    prereq_object = GenericForeignKey("prereq_content_type", "prereq_object_id")
    prereq_count = models.PositiveIntegerField(default=1)
    prereq_invert = models.BooleanField(default=False, verbose_name="NOT")

    # an optional alternate prerequisite object and options
    or_prereq_content_type = models.ForeignKey(ContentType, related_name='or_prereq_item',
                                               verbose_name="OR Type of Prerequisite", blank=True, null=True)
    or_prereq_object_id = models.PositiveIntegerField(blank=True, null=True,
                                                      verbose_name="OR Prerequisite")
    or_prereq_object = GenericForeignKey("or_prereq_content_type", "or_prereq_object_id")
    or_prereq_count = models.PositiveIntegerField(default=1)
    or_prereq_invert = models.BooleanField(default=False, verbose_name='OR NOT')

    objects = PrereqManager()

    def __str__(self):
        """
        Format: [NOT] (Type1) prereq.__str__ [xN] [OR [NOT] (Type2) or_prepreq.__str__ [xM] ]
        square bracketed content only if not None
        example: "(Quest) Blender Intro OR NOT (Badge) Hackerspace Alumni"
        """
        s = ""
        if self.prereq_invert:
            s += "NOT "
        s += "(" + str(self.prereq_content_type) + ") "
        s += str(self.get_prereq())
        if self.prereq_count > 1:
            s += " x" + str(self.prereq_count)
        if self.or_prereq_object_id and self.or_prereq_content_type:
            s += " OR "
            if self.or_prereq_invert:
                s += "NOT "
            s += "(" + str(self.or_prereq_content_type) + ") "
            s += str(self.get_or_prereq())
            if self.or_prereq_count > 1:
                s += " x" + str(self.or_prereq_count)
        return s

    # @staticmethod
    # def autocomplete_search_fields():
    #     return ("name__icontains",)

    def parent(self):
        """:return the parent as its object"""
        try:
            return self.parent_content_type.get_object_for_this_type(pk=self.parent_object_id)
        except ObjectDoesNotExist:
            return None

    def get_prereq(self):
        """:return the main prereq as its object"""
        try:
            return self.prereq_content_type.get_object_for_this_type(pk=self.prereq_object_id)
        except ObjectDoesNotExist:
            return None

    def get_or_prereq(self):
        """:return the alternate prereq as its object"""
        try:
            return self.or_prereq_content_type.get_object_for_this_type(pk=self.or_prereq_object_id)
        except ObjectDoesNotExist:
            return None

    def condition_met_as_prerequisite(self, user):
        """
        :param user:
        :return: True if the conditions for this prerequisite have been met by the user
        """

        # the first of two possible alternate prereq conditions
        prereq_object = self.get_prereq()
        if prereq_object is None:
            return False
        main_condition_met = prereq_object.condition_met_as_prerequisite(user, self.prereq_count)

        # invert the requirement if needed (NOT)
        if self.prereq_invert:
            main_condition_met = not main_condition_met

        # check if there is an alternate condition (OR)
        if not self.or_prereq_object_id or not self.or_prereq_content_type:
            return main_condition_met

        or_prereq_object = self.get_or_prereq()
        if or_prereq_object is None:
            return False
        or_condition_met = or_prereq_object.condition_met_as_prerequisite(user, self.or_prereq_count)

        # invert alternate if required (NOT OR)
        if self.or_prereq_invert:
            or_condition_met = not or_condition_met

        return main_condition_met or or_condition_met

    @classmethod
    def add_simple_prereq(cls, parent_object, prereq_object):
        """
        Adds an object (the prereq_parent) as a prerequisite to another object (prereq_object)
        Does not include any more complicated logic such as OR AND NOT
        :param parent_object:
        :param prereq_object:
        :return: True if successful
        """
        if not parent_object or not prereq_object:
            return False
        new_prereq = cls(
            parent_content_type=ContentType.objects.get_for_model(parent_object),
            parent_object_id=parent_object.id,
            prereq_content_type=ContentType.objects.get_for_model(prereq_object),
            prereq_object_id=prereq_object.id,
        )

        new_prereq.save()
        return True

    @classmethod
    def all_registered_content_types(cls):
        registered_list = [
            ct.pk for ct in ContentType.objects.all()
            if cls.model_is_registered(ct)
            ]
        return ContentType.objects.filter(pk__in=registered_list)

    @staticmethod
    def model_is_registered(content_type):

        # Check if class has the method `condition_met_as_prerequisite`
        # http://stackoverflow.com/questions/25295327/how-to-check-if-a-python-class-has-particular-method-or-not
        mc = content_type.model_class()

        # deleted models?
        if mc is None:
            return False

        if any("condition_met_as_prerequisite" in B.__dict__ for B in mc.__mro__):
            return True

        return False
