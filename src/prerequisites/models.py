from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.base import ObjectDoesNotExist


class IsAPrereqMixin:
    """
    For models that act as a prerequisite.  Classes using this mixin need to implement
    the method: condition_met_as_prerequisite(user, num_required)
    """

    # TODO: Can I force implementing models to define this method?
    def condition_met_as_prerequisite(self, user, num_required):
        """
        Defines what it means for the user to meet this prerequisite.  For this Mixin to be any use, the implementing
        model must override this method.
        :param user: a django user
        :param num_required - recommend to default this to when overriding
        :return: True if the user meets the requirements for this object as a prerequisite, otherwise False.

        """
        return False

    def get_reliant_qs(self):
        """
        :return: a queryset containing the objects that require this as a prereq
        """
        return Prereq.objects.all_reliant_on(self)

    def get_reliant_objects(self, active_only=True):
        """
        :return: a list containing the objects that require this as a prereq
        """
        reliant_qs = self.get_reliant_qs()
        reliant_objects = []
        for prereq in reliant_qs:
            parent_obj = prereq.parent()
            # Why would this be None?  It's happening in testing, perhaps deleted objects?
            if parent_obj is not None:
                # should refactor the name of this field, or make in common
                if active_only and hasattr(parent_obj, 'active'):
                    if parent_obj.active:
                        reliant_objects.append(parent_obj)
                else:
                    reliant_objects.append(parent_obj)
        return reliant_objects

    # to help with the prerequisite choices!
    # TODO: Why? link to grapelli docs and let implementing class choose field instead of static?
    @staticmethod
    def autocomplete_search_fields():
        return ("name__icontains",)


class PrereqQuerySet(models.query.QuerySet):
    """
    For models that have prerequisites
    NOT CURRENTLY USED
    """

    def __init__(self, no_prereqs_means=False):
        """
        :param no_prereqs_means: If an instance of this model has no prereqs, what should happen?
            True -> Make the object available
            False -> The object is unavailable (and would have to be made available through some other mechanism)  I use
            this for badges, which must be granted manually if they have no prerequisites.
        """
        self.no_prereqs_means = no_prereqs_means
        super(PrereqQuerySet, self).__init__()

    def get_conditions_met(self, user):
        """
        :param user:
        :param initial_query_set: The queryset to filter.  I think this is a very inefficient method, so until I figure
        out how to speed it up, make sure the provided query_set is already filtered down as small as possible.
        :return: A queryset containing all objects (of the model implementing this mixin) for which the user has met
        the prerequisites
        """

        # Initialize member variable in case the constructor wasn't called,
        # which might happen if the class implementing this mixin doesn't call the constructor?
        # If you're reading this and understand how python inheritance works with constructors, please let me know =)
        # I could look it up myself, but I'm on the subway with no internet access while on vacation in London,
        # and by the time I do get internet access, I'll probably be on to something else and forget about it.
        # TODO: is this necessary?
        if self.no_prereqs_means is None:
            self.no_prereqs_means = True

        # TODO: Make this more efficient, too slow!
        # build a list of object pks to use in the filter.
        pk_met_list = [
            obj.pk for obj in self
            if Prereq.objects.all_conditions_met(obj, user)
            ]
        return self.filter(pk__in=pk_met_list)


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
        return self.get_queryset().get_all_for_parent_object(parent_object)

    # TODO: Add in alternate prereqs to!
    def all_reliant_on(self, prereq_object):
        return self.get_queryset().get_all_for_prereq_object(prereq_object)

    def all_conditions_met(self, parent_object, user, no_prereq_means=True):
        """
        Checks if all the prerequisites for this parent_object and user have been met.
        If the parent_object has no prerequisites, then return according to the no_prereq_means parameter,
        this is because different models might want different behaviour if there are no prereqs, they can
        either be available (default, no_prereq_means=True) or unavailable (no_prereq_means=False).
        This should be set in the mixin constructor... I'd tell you how to do it here but I haven't figured it out yet.
        I assume by the time this is published anywhere that someone is reading it other than myself, the mixin itself
        will explain better...
        """
        prereqs = self.all_parent(parent_object)
        if not prereqs:
            return no_prereq_means
        for prereq in prereqs:
            if not prereq.condition_met(user):
                return False
        return True

    def is_prerequisite(self, prereq_obj):
        """
        :return: True if obj is a prerequisite to any other object
        """
        if self.get_queryset().get_all_for_prereq_object(prereq_obj):
            return True
        if self.get_queryset().get_all_for_or_prereq_object(prereq_obj):
            return True
        return False


class Prereq(models.Model, IsAPrereqMixin):
    """
    Links two (or three) objects (of any registered content type) in a prerequisite relationship.
    Note that a Prereq can itself be a prereq (in combination with AND OR NOT, this allows for arbitrary complexity)
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

    # A Prereq can itself be a prereq_object
    def condition_met_as_prerequisite(self, user, num_required=1):
        return self.condition_met(user)

    def condition_met(self, user):
        """
        :param user:
        :return: True if the conditions for this complex Prereq have been met by the user
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
