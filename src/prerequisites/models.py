import json
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.conf import settings
from django.db import models
from django.db.models import Q


class HasPrereqsMixin:
    """
    For models that have prerequisite requirements that determine their objects' availablity.
    """

    def prereqs(self):
        """ A queryset of all the object's prerequisites """
        return Prereq.objects.all_parent(self)

    def add_simple_prereqs(self, prereq_objects_list):
        """ Adds each object in the list as a simple pre-requisite requirement to this parent object """
        for prereq_object in prereq_objects_list:
            if prereq_object:
                if not isinstance(prereq_object, IsAPrereqMixin):
                    raise TypeError
                else:
                    Prereq.add_simple_prereq(self, prereq_object)

    def clear_all_prereqs(self):
        """ Removes all pre-requisite requirements from this parent object """
        num_deleted = self.prereqs().delete()
        return num_deleted

    def has_or_prereq(self, prereq_object=None, exclude_NOT=True):
        """Returns True if this object has the prereq_object as part of a prerequisite with an alterante "or" requirement.
        By default will return false if the prereq_objects is flagged as NOT.

        If not specific_prereq_object is provided, then return True if it has ANY or prereqs.
        """
        if prereq_object and not isinstance(prereq_object, IsAPrereqMixin):
            raise TypeError

        # Get all prereqs that have an OR object
        qs = self.prereqs()
        qs = qs.exclude(or_prereq_object_id=None)

        if not prereq_object:
            # then return True if any are found
            if exclude_NOT:
                qs = qs.exclude(or_prereq_invert=True).exclude(prereq_invert=True)
            if qs:
                return True
            else:
                return False

        ct = ContentType.objects.get_for_model(prereq_object)
        # Then filter those for prereqs that have the provided object in either spot
        if exclude_NOT:
            qs = qs.filter(
                Q(or_prereq_content_type__pk=ct.id, or_prereq_object_id=prereq_object.id, or_prereq_invert=False) |  # or
                Q(prereq_content_type__pk=ct.id, prereq_object_id=prereq_object.id, prereq_invert=False)
            )
        else:
            qs = qs.filter(
                Q(or_prereq_content_type__pk=ct.id, or_prereq_object_id=prereq_object.id) |  # or
                Q(prereq_content_type__pk=ct.id, prereq_object_id=prereq_object.id)
            )
        if qs:
            return True
        else:
            return False

    def has_inverted_prereq(self):
        """Returns true if this object has any prereqs that are inverted, i.e NOT"""
        # just remove all prereqs that are not inverted and see if anything is left
        qs = self.prereqs()
        qs = qs.filter(Q(or_prereq_invert=True) | Q(prereq_invert=True))
        if qs:
            return True
        else:
            return False


class IsAPrereqMixin:
    """
    For models that act as a prerequisite.
    Classes using this mixin need to implement
    the method: condition_met_as_prerequisite(user, num_required)
    and have a field "name", or override the autocomplete_search_fields() class method
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
        raise NotImplementedError

    def is_used_prereq(self):
        """
        :return: True if this object has been assigned as a prerequisite to at least one another object.
        """
        return Prereq.objects.is_prerequisite(self)

    def get_reliant_qs(self, exclude_NOT=False):
        """
        :return: a queryset containing the objects that require this as a prereq
        """
        return Prereq.objects.all_reliant_on(self, exclude_NOT=exclude_NOT)

    def get_reliant_objects(self, active_only=True, exclude_NOT=False):
        """
        :return: a list containing the objects that require this as a prereq
        """
        reliant_qs = self.get_reliant_qs(exclude_NOT=exclude_NOT)
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

    # to help with the prerequisite choices:
    # https://django-grappelli.readthedocs.io/en/latest/customization.html#autocomplete-lookups
    # override this static method in the class to choose different search fields
    @staticmethod
    def autocomplete_search_fields():
        return ("name__icontains",)


# class PrereqQuerySet(models.query.QuerySet):
#     """
#     For models that have prerequisites
#     NOT CURRENTLY USED
#     """

#     def __init__(self, no_prereqs_means=False):
#         """
#         :param no_prereqs_means: If an instance of this model has no prereqs, what should happen?
#             True -> Make the object available
#             False -> The object is unavailable (and would have to be made available through some other mechanism)
#              I use this for badges, which must be granted manually if they have no prerequisites.
#         """
#         self.no_prereqs_means = no_prereqs_means
#         super(PrereqQuerySet, self).__init__()

#     def get_conditions_met(self, user):
#         """
#         :param user:
#         :param initial_query_set: The queryset to filter.  I think this is a very inefficient method, so until
#          I figure out how to speed it up, make sure the provided query_set is already filtered down as small
#          as possible.
#         :return: A queryset containing all objects (of the model implementing this mixin) for which the user has met
#         the prerequisites
#         """

#         # Initialize member variable in case the constructor wasn't called,
#         # which might happen if the class implementing this mixin doesn't call the constructor?
#         # If you're reading this and understand how python inheritance works with constructors, please let me know =)
#         # I could look it up myself, but I'm on the subway with no internet access while on vacation in London,
#         # and by the time I do get internet access, I'll probably be on to something else and forget about it.
#         # TODO: is this necessary?
#         if self.no_prereqs_means is None:
#             self.no_prereqs_means = True

#         # TODO: Make this more efficient, too slow!
#         # build a list of object pks to use in the filter.
#         pk_met_list =  [
#             obj.pk for obj in self
#             if Prereq.objects.all_conditions_met(obj, user)
#             ]
#         return self.filter(pk__in=pk_met_list)


class PrereqQuerySet(models.query.QuerySet):
    def get_all_for_parent_object(self, parent_object):
        ct = ContentType.objects.get_for_model(parent_object)
        return self.filter(parent_content_type__pk=ct.id,
                           parent_object_id=parent_object.id)

    def get_all_for_prereq_object(self, prereq_object, exclude_NOT=False):
        ct = ContentType.objects.get_for_model(prereq_object)
        qs = self.filter(prereq_content_type__pk=ct.id,
                         prereq_object_id=prereq_object.id)
        if exclude_NOT:
            qs = qs.exclude(prereq_invert=True)
        return qs

    def get_all_for_or_prereq_object(self, prereq_object, exclude_NOT=False):
        ct = ContentType.objects.get_for_model(prereq_object)
        qs = self.filter(or_prereq_content_type__pk=ct.id,
                         or_prereq_object_id=prereq_object.id)
        if exclude_NOT:
            qs.exclude(or_prereq_invert=True)
        return qs

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

    def all_reliant_on(self, prereq_object, exclude_NOT=False):
        qs = self.get_queryset().get_all_for_prereq_object(prereq_object, exclude_NOT=exclude_NOT)
        or_qs = self.get_queryset().get_all_for_or_prereq_object(prereq_object, exclude_NOT=exclude_NOT)
        return qs.union(or_qs)

    def all_conditions_met(self, parent_object, user, no_prereq_means=True):
        """
        Checks if all the prerequisites for this parent_object and user have been met.
        If the parent_object has Prereq object in which it is the Prereq.parent_object,
        then return according to the no_prereq_means parameter,
        [this is because different models might want different behaviour if there are no prereqs, they can
        either be available (default, no_prereq_means=True) or unavailable (no_prereq_means=False).]

        This should be set in the IsAPrereqMixin constructor... I'd tell you how to do it here but I haven't figured it
        out yet.  I assume by the time this is published anywhere that someone is reading it other than myself, the
        mixin itself will explain better...
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


class Prereq(IsAPrereqMixin, models.Model):
    """
    A Prereq object indicates some conditions (prerequisites) that must be met before gaining access to something else.

    parent_object: The parent object is the thing with restricted access (for example, a quest, or a badge).
     Access to it is granted once the conditions are met.

    prereq_object: This is the main condition that has to be met for a user to gain access to the parent object.
     How that condition is met is determined by the Class's implementation of `condition_met_as_prerequisite()` from the
     IsAPrereqMixin.  This object could be any model that implements the mixin (quest, badge, grade, course, etc)

    or_prereq_object: This is an ALTERNATE condition that could be met instead of the condition laid out by prereq_
     object.

    Simple example:  Imagine a quest that a student only gains access to if they are in a grade 10 course:

        Prereq <
            parent_object = quest_manager.models.Quest object <"Some Quest">
            prereq_object = courses.models.Grade <"Grade 10">
        >

        Given a specific user, when the querying of available quests gets to this quest, it will find this Prereq and
          call condition_met() on it. If condition_met() returns True (supposedly, because the student has a Grade 10
          course) then this Prereq (Quest object <"Some Quest"> will not be filtered out of the user's available quests

          See condition_met() for further details.


    Links two (or three) objects (of any registered content type) in a prerequisite relationship.
    Note that a Prereq can itself be a prereq (in combination with AND OR NOT, this allows for arbitrary complexity)
    parent: The owner of the prerequisite. Generally, for the parent to become 'active' the prereq_object conditions
        must be met.  'active' can mean whatever the user of this app wants it to mean.  It's a generic trigger.
    prereq: The object whose conditions must be met in order for the parent to become 'active', which optional
        additional conditions NOT and a number to indicate how many times the condition much be met.
    or_prereq: An optional alternate object who's condition can me met instead of prereq: prereq OR or_prereq
    """

    name = models.CharField(max_length=256, null=True, blank=True,
                            help_text="Providing a name to a prereq allows it to be used itself as a prerequisite. "
                                      "One use for this to to chain more than two OR conditions.")

    parent_content_type = models.ForeignKey(ContentType, related_name='prereq_parent', on_delete=models.CASCADE)
    parent_object_id = models.PositiveIntegerField()
    parent_object = GenericForeignKey("parent_content_type", "parent_object_id")

    # the required prerequisite object and options
    prereq_content_type = models.ForeignKey(ContentType, related_name='prereq_item',
                                            verbose_name="Type of Prerequisite",
                                            on_delete=models.CASCADE)
    prereq_object_id = models.PositiveIntegerField(verbose_name="Prerequisite")
    prereq_object = GenericForeignKey("prereq_content_type", "prereq_object_id")
    prereq_count = models.PositiveIntegerField(default=1)
    prereq_invert = models.BooleanField(default=False, verbose_name="NOT")

    # an optional alternate prerequisite object and options
    or_prereq_content_type = models.ForeignKey(ContentType, related_name='or_prereq_item',
                                               verbose_name="OR Type of Prerequisite", blank=True, null=True,
                                               on_delete=models.SET_NULL)
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
        return self.parent_object

    def get_prereq(self):
        """:return the main prereq as its object"""
        return self.prereq_object

    def get_or_prereq(self):
        """:return the alternate prereq as its object"""
        return self.or_prereq_object

    # A Prereq can itself be a prereq_object
    def condition_met_as_prerequisite(self, user, num_required=1):
        return self.condition_met(user)

    def condition_met(self, user):
        """
        :param user:
        :return: True if the conditions for this complex Prereq have been met by the user

        CONTINUE this simple example from Prereq:
        Imagine a quest that a student only gains access to if they are in a grade 10 course:

        Prereq <
            parent_object = quest_manager.models.Quest <"Some Quest">
            prereq_object = courses.models.Grade <"Grade 10">
        >

        When a user is querying the list of available objects (in this case, quests), each quest will look to see if it
        is the parent_object for any Prereq objects.  If it is, that means there are some pre conditions that must be
        met before it can make it into the query.  An example of this query can be found at QuestManager.get_available()
        which in turn calls QuestQuerySet.get_conditions_met(), which, for each quest, calls
        PrereqManager.all_conditions_met() -- see that one for more details.

        If Quest <"Some Quest"> is passed to PrereqManager.all_conditions_met() for a user, it will search for
        Prereq objects and find our example above.  In turn, it will call THIS method on that Prereq.

        The example Prereq shows that Grade <"Grade 10"> is required before Quest <"Some Quest">
        is available to the student.

        THIS method will then call condition_met_as_prerequisite on Grade <"Grade 10"> FOR THAT USER.

        condition_met_as_prerequisite() is a method that all models with the IsAPrereqMixin should have.

        In this case, if they are currently in a grade 10 course it will return True, otherwise False,
        but the specific implementation can be found in courses.models.Grade.condition_met_as_prerequisite().
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
        Adds an object (prereq_object) as a prerequisite to another object (parent_object)
        Does not include any more complicated logic such as OR AND NOT
        :param parent_object: The owner of the prereq (i.e the object that needs the prereq fulfilled before it becomes available)
        :param prereq_object: The preq that needs to be completed before the parent becomes available
        :return: True if successful
        """
        # This breaks some data migrations because custom methods are not available during
        # migrations, and it seems the objects don't get their Mixin during the data migrations?
        if not isinstance(parent_object, HasPrereqsMixin):
            raise TypeError("parent_object does not implement HasPrereqsMixin")
        if not isinstance(prereq_object, IsAPrereqMixin):
            raise TypeError("parent_object does not implement IsAPrereqMixin")

        # prereq_object can be sent empty for convenience
        if not parent_object or not prereq_object:
            return None

        new_prereq = cls(
            # Why do tests throw errors when I try to assign the GFK objects directly?
            # parent_object=parent_object,
            # prereq_object=prereq_object
            parent_content_type=ContentType.objects.get_for_model(parent_object),
            parent_object_id=parent_object.id,
            prereq_content_type=ContentType.objects.get_for_model(prereq_object),
            prereq_object_id=prereq_object.id,
        )
        new_prereq.save()
        return new_prereq

    @classmethod
    def all_registered_content_types(cls):
        registered_list = [
            ct.pk for ct in ContentType.objects.all()
            if cls.model_is_registered(ct)
        ]
        return ContentType.objects.filter(pk__in=registered_list)

    @staticmethod
    def model_is_registered(content_type):
        """Check if class implements IsAPrereqMixin"""
        mc = content_type.model_class()

        # handle old content types that may not have been removed? mc = None
        if mc and issubclass(mc, IsAPrereqMixin):
            return True
        else:
            return False


class PrereqAllConditionsMet(models.Model):
    """This is a cache of the Prereq.objects.all_conditions_met(obj, user) method which is super innefficient and clunky
    but also critical to how this site works.

    It is recalulated asynchronously using celery (see tasks.py).
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    # these next two fields look like a custom Generic Foreign Key implementation?
    ids = models.TextField(default='[]')  # str representation of a list of ids for the model, e.g '[25, 34, 55, 56, 77]'
    model_name = models.CharField(max_length=256)  # model name as a string with .get_model_name()

    def add_id(self, new_id):
        ids = self.get_ids()
        if new_id not in ids:
            ids.append(new_id)
            self.set_ids(ids)

    def remove_id(self, id_to_remove):
        ids = self.get_ids()
        if id_to_remove in ids:
            ids.remove(id_to_remove)
            self.set_ids(ids)

    def get_ids(self):
        if self.ids:
            return json.loads(self.ids)
        return PrereqAllConditionsMet.ids.default

    def set_ids(self, id_list=[]):
        self.ids = str(id_list)
        self.save()
