import json
import re

import random
from badges.models import Badge
from courses.models import Rank
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse
from django.db import models
from django.shortcuts import get_object_or_404
from django.utils import timezone

from url_or_relative_url_field.fields import URLOrRelativeURLField

from quest_manager.models import Category


def clean_JSON(dirty_json_str):
    """ Takes a poorly formatted JSON string and cleans it up a bit:
    - double quote all keys,
    - replace single quotes with double quotes,
    - remove trailing commas after last element, and
    - wrap in braces if needed
    """
    txt = dirty_json_str.strip()

    # remove trailing comma
    if txt[-1] == ",":
        txt = txt[:-1]

    # remove trailing comma before closing brace or square bracket
    regex = r"(,)\s*[\]}]"
    txt = re.sub(regex, '', txt)

    # Add enclosing braces if not present
    if txt[0] != "{":
        txt = "{" + txt

    if txt[-1] != "}":
        txt += "}"

    # Find unquoted keys and add quotes:
    # https://regex101.com/r/oV0udR/1
    regex = r"([{,]\s*)([^\"':]+)(\s*:)"
    subst = "\\1\"\\2\"\\3"
    txt = re.sub(regex, subst, txt, 0)

    # replace single quotes with double quotes:
    txt = txt.replace("\'", "\"")

    return txt


class CytoElementQuerySet(models.query.QuerySet):
    def all_scape(self, scape_id):
        return self.filter(scape_id=scape_id)

    def all_parent(self, data_parent_id):
        return self.filter(data_parent_id=data_parent_id)

    def nodes(self):
        return self.filter(group=CytoElement.NODES)


class CytoElementManager(models.Manager):
    def get_queryset(self):
        return CytoElementQuerySet(self.model, using=self._db)

    def all_for_scape(self, scape):
        return self.get_queryset().all_scape(scape.id)

    def get_random_node(self, scape):
        qs = self.get_queryset().nodes().all_scape(scape.id)
        count = qs.count()
        random_index = random.randint(0, count - 1)
        return qs[random_index]

    def get_random_node_triangular_distribution(self, scape):
        qs = self.get_queryset().nodes().all_scape(scape.id)
        count = qs.count()
        random_index = int(random.triangular(0, count - 1, count / 2))
        return qs[random_index]

    def all_for_campaign(self, scape, data_parent):
        return self.all_for_scape(scape).all_parent(data_parent.id)


class CytoElement(models.Model):
    NODES = 'nodes'
    EDGES = 'edges'
    GROUP_CHOICES = ((NODES, 'nodes'), (EDGES, 'edges'))
    # name = models.CharField(max_length=200)
    scape = models.ForeignKey('CytoScape', on_delete=models.CASCADE)
    selector_id = models.CharField(
        max_length=16, blank=True, null=True,
        help_text="unique id in the form of 'model-#' where the model = Quest (etc) and # = object id."
    )
    group = models.CharField(max_length=6, choices=GROUP_CHOICES, default=NODES)
    # TODO: make a callable for limit choices to, so that limited to nodes within the same scape
    data_parent = models.ForeignKey('self', blank=True, null=True, related_name="parents",
                                    limit_choices_to={'group': NODES},
                                    help_text="indicates the compound node parent; blank/null => no parent",
                                    on_delete=models.CASCADE)
    data_source = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True, related_name="sources",
                                    help_text="edge comes from this node")
    data_target = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True, related_name="targets",
                                    help_text="edge goes to this node")
    data_dict = models.TextField(blank=True, null=True,
                                 help_text="python dictionary stored as string: {'key1':'value1', 'key2':'value2'}")
    selected = models.BooleanField(default=False)
    selectable = models.BooleanField(default=True)
    locked = models.BooleanField(default=False)
    grabbable = models.BooleanField(default=True)
    classes = models.CharField(max_length=250, blank=True, null=True,
                               help_text="a space separated list of css class names for the element")
    id_styles = models.TextField(blank=True, null=True,
                                 help_text="styles specific to this node (using id selector)")
    label = models.CharField(max_length=50, blank=True, null=True,
                             help_text="if present, will be used as node label instead of id")
    min_len = models.IntegerField(default=1,
                                  help_text="number of ranks to keep between the source and target of the edge")
    href = URLOrRelativeURLField(blank=True, null=True, max_length=50)
    is_transition = models.BooleanField(default=False,
                                        help_text="Whether this node transitions to a new map")
    objects = CytoElementManager()

    class Meta:
        # elements neet to be ordered with nodes first, then edges, or the edges might try to
        # connect nodes that don't exist yet and mess up creation of the cytoscape
        # e.g. https://stackoverflow.com/questions/60825627/cytoscape-js-and-dagre-result-in-one-node-positioned-awkwardly

        # nodes then edges, then nodes without a parent, which might be a compound (campaign) node and need to come before
        # other nodes within that comound node (campaign)
        ordering = ['-group', models.F('data_parent').asc(nulls_first=True)]

    def __str__(self):
        if self.group == self.NODES:
            return str(self.id) + ": " + str(self.label)
        else:
            return str(self.id) + ": " + str(self.data_source.id) + "->" + str(self.data_target.id)

    def has_parent(self):
        return self.data_parent is not None

    def is_edge(self):
        """Edges will have a source and target"""
        return self.data_source and self.data_target

    def is_node(self):
        """Anything that is not an edge.  Includes compound nodes (i.e. campaigns/Categories)"""
        return not self.is_edge()

    def is_parent(self):
        """This node represents a campaign, and is the parent of a compound node"""
        return CytoElement.objects.filter(data_parent=self).exists()

    def json_dict(self):
        """ Returns a json serializable python dictionary representing this element as a djcytoscape node or edge
        resulting in something like:
        {
            "data": {
                "id": 2107,
                "label": "Badge: ByteDeck Proficiency* (2)",
                "href": "/maps/2/1/1/",
                "Badge": 1
            },
            "classes": "Badge link"
        }
        """
        data = {"id": self.id}

        if self.label:
            data["label"] = self.label

        if self.has_parent():
            data["parent"] = self.data_parent.id

        elif self.is_edge():
            data["source"] = self.data_source.id
            data["target"] = self.data_target.id
            if self.min_len and self.min_len != 1:  # 1 is default, not needed:
                data["minLen"] = str(self.min_len)
            # json_str += "        edgeWeight: 1, \n"  # '" + str(self.edge_weight) + "',\n"
        if self.href:
            data["href"] = self.href
        if self.selector_id:
            # selector_id will be something like "Quest: 342"
            key = self.selector_id.split(":")[0].strip()
            value = self.selector_id.split(":")[1].strip()  # this is the pk/id of the quest or badge
            data[key] = int(value)

        json_dict = {"data": data}

        if self.classes:
            json_dict["classes"] = self.classes

        return json_dict

    def json(self):
        return json.dumps(self.json_dict())

    def convert_to_transition_node(self, obj, scape):
        """ If this obj is a transition node (to a new map), convert it."""
        ct = ContentType.objects.get_for_model(obj)

        self.href = reverse('maps:quest_map_interlink', args=[ct.id, obj.id, scape.id])
        self.classes = "link child-map"
        self.is_transition = True
        self.save()

    @staticmethod
    def generate_selector_id(obj):
        """
        unique id in the form of 'model: #' where the model = Quest (etc) and # = object id.
        Examples: Quest: 21 or Badge: 5
        # Todo, this seems uneccessary, because we just have to parse it when building the json dict.
        # Just save the model name and the id seperately?
        """
        return str(type(obj).__name__) + ": " + str(obj.id)

    @staticmethod
    def get_selector_styles_json_dict(selector, styles):
        if styles:
            json_dict = {}
            json_dict['selector'] = selector
            styles = clean_JSON(styles)
            json_dict['style'] = json.loads(styles)
            return json_dict
        else:
            return None


class TempCampaignNode:
    def __init__(self, id_, prereq_node_id=None):
        self.id = id_
        self.prereq_node_ids = []
        self.reliant_node_ids = []
        if prereq_node_id:
            self.prereq_node_ids.append(prereq_node_id)

    def __str__(self):
        return str(self.id)


class TempCampaign:
    """
    Temporary structure used to help build the cytoscape, generates lists for each campaign to make it easier to
    properly generate edges to give the desired layout.
    """

    def __init__(self, parent_node_id):
        self.node_id = parent_node_id  # Campaigns are parent/compound nodes
        self.campaign_reliant_node_ids = []
        self.nodes = []  # a list of TempCampaignNodes (representing quests) in the Campaign

    def __str__(self):
        tmp_str = "Parent: " + str(self.node_id)
        if self.nodes:
            for node in self.nodes:
                tmp_str += " Child:" + str(node)
        else:
            tmp_str += " No children"
        return tmp_str

    def add_node(self, node_id, prereq_node_id):
        # if node already exists, add to existing node data
        existing_node = self.get_node(node_id)
        if existing_node:
            existing_node.prereq_node_ids.append(prereq_node_id)
        else:
            new_node = TempCampaignNode(node_id, prereq_node_id)
            self.nodes.append(new_node)

    def add_reliant(self, node_id, reliant_node_id):
        """ Adds nodes the the temp campaign for later cleanup

        Args:
            node_id (int): the source node that is in this campaign
            reliant_node_id (int): the target node that has the source as a prerequisite.  This node also be in the campaign, or may not.
        """
        node = self.get_node(node_id)
        node.reliant_node_ids.append(reliant_node_id)

    def add_campaign_reliant(self, reliant_node_id):
        """ Add nodes that are directly reliant on the Campaign, i.e. this campaign is a prereq"""
        self.campaign_reliant_node_ids.append(reliant_node_id)

    def get_last_node(self):
        return self.nodes[-1]

    def get_first_node(self):
        return self.nodes[0]

    def get_node(self, node_id):
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def get_next_node(self, current_node):
        next_loc = self.nodes.index(current_node) + 1
        if len(self.nodes) > next_loc:
            return self.nodes[next_loc]

    def get_all_prereq_ids(self):
        all_prereq_ids = []
        for node in self.nodes:
            all_prereq_ids += node.prereq_node_ids
        return all_prereq_ids

    def get_all_reliant_ids(self):
        all_reliant_ids = []
        for node in self.nodes:
            all_reliant_ids += node.reliant_node_ids
        return all_reliant_ids

    def has_internal_prereq(self, node):
        for internal_node in self.nodes:
            if internal_node.id in node.prereq_node_ids:
                return True
        return False

    def has_internal_reliant(self, node):
        for internal_node in self.nodes:
            if internal_node.id in node.reliant_node_ids:
                return True
        return False

    def get_common_reliant_node_ids(self):
        """
        :return: return nodes that are reliant on ALL nodes within the campaign, excluded from this requirement
        are nodes that have an internal reliant node, which itself will have this common external reliant.
        """
        common_reliant_ids = []
        # print(self.get_all_reliant_ids())
        for reliant_id in set(self.get_all_reliant_ids()):
            count = 0
            for node in self.nodes:
                if reliant_id in node.reliant_node_ids or self.has_internal_reliant(node):
                    count += 1
            if count == len(self.nodes):
                common_reliant_ids.append(reliant_id)
        return common_reliant_ids

    def get_common_prereq_node_ids(self):
        """
        :return: return nodes that are a prerequisite to ALL nodes within the campaign, excluded form requirement of
        having this common prereq are nodes with a prereq already internal to the campaign (which itself will share
        this common prereq)
        """
        common_prereq_ids = []
        # print(self.get_all_prereq_ids())
        for prereq_id in set(self.get_all_prereq_ids()):
            external_count = 0
            internal_count = 0
            for node in self.nodes:
                if prereq_id in node.prereq_node_ids:
                    external_count += 1
                elif self.has_internal_prereq(node):
                    internal_count += 1
            # Need more than one or kind of pointless to say the campaign is reliant, when one one quest!
            if external_count > 1 and (external_count + internal_count) == len(self.nodes):
                common_prereq_ids.append(prereq_id)
        return common_prereq_ids

    def is_non_sequential(self):
        # If there is at least one common prereq node
        return self.get_common_prereq_node_ids() is True


class CytoScapeQueryset(models.QuerySet):

    def get_maps_as_formatted_string(self):
        """ returns queryset of maps as grammatically correct string with hyperlinks to map pages
        [map1]
        >>> map1
        [map1, map2]
        >>> map1 and map2
        [map1, map2, ..., mapN]
        >>> map1, map2, ..., and mapN
        """
        # .join functions do not convert to str
        names = [f'<a href="{scape.get_absolute_url()}">{str(scape)}</a>' for scape in self]

        if self.count() == 0:
            return None
        elif self.count() == 1:
            return names[0]
        # oxford comma not applicable
        elif self.count() == 2:
            return " and ".join(names)
        # oxford comma
        else:
            return ", ".join(names[:-1]) + f", and {names[-1]}"


class CytoScapeManager(models.Manager):

    def get_queryset(self):
        return CytoScapeQueryset(self.model, using=self._db)

    def generate_random_tree_scape(self, name, size=100):
        scape = CytoScape(
            name=name,
            layout_name='breadthfirst',
            layout_options="directed: true, spacingFactor: " + str(1.75 * 30 / size),
        )
        scape.save()

        # generate starting node
        source_node = CytoElement(scape=scape, group=CytoElement.NODES, )
        source_node.save()
        node_list = [source_node]
        count = 1
        while node_list and count < size:
            current_node = random.choice(node_list)
            # 10% chance to split branch, 10% to cap it
            split = random.random()
            children = 1
            if split < .10:
                children = random.randint(1, 3)  # 1 to 3

            if current_node is source_node:
                children = 10
            if split < 90:  # create the target nodes, connect them to source, add them to list
                for _i in range(0, children):
                    new_node = CytoElement(scape=scape, group=CytoElement.NODES, )
                    new_node.save()
                    node_list.append(new_node)
                    edge = CytoElement(
                        scape=scape, group=CytoElement.EDGES,
                        data_source=current_node,
                        data_target=new_node,
                    )
                    edge.save()
                    count += 1

            if len(node_list) > 1:  # don't cap last node
                node_list.remove(current_node)

        return scape

    def generate_random_scape(self, name, size=100):
        new_scape = CytoScape(
            name=name,
        )
        new_scape.save()

        # generate nodes
        for _i in range(0, size):
            new_node = CytoElement(
                scape=new_scape,
                group=CytoElement.NODES,
            )
            new_node.save()

        # generate edges
        for _i in range(0, size * 3):
            new_edge = CytoElement(
                scape=new_scape,
                group=CytoElement.EDGES,
                data_source=CytoElement.objects.get_random_node(new_scape),
                data_target=CytoElement.objects.get_random_node(new_scape),
            )
            new_edge.save()

        return new_scape

    def get_map_for_init(self, initial_object):
        """Return the map that this object initiates, else return None"""
        ct = ContentType.objects.get_for_model(initial_object)
        try:
            return self.get_queryset().get(initial_object_id=initial_object.id, initial_content_type=ct)
        except ObjectDoesNotExist:
            return None

    def get_related_maps(self, object_):
        """ returns all CytoScape maps associated with object as a queryset """
        selector_id = CytoElement.generate_selector_id(object_)

        related_ids = CytoElement.objects.filter(
            group=CytoElement.NODES,
            selector_id=selector_id,
        ).values_list('scape__id', flat=True)

        return self.get_queryset().filter(id__in=related_ids)


class CytoScape(models.Model):
    ALLOWED_INITIAL_CONTENT_TYPES = models.Q(app_label='quest_manager', model='quest') | \
                                    models.Q(app_label='badges', model='badge') | \
                                    models.Q(app_label='courses', model='rank')

    name = models.CharField(max_length=250)

    # initial_object = models.OneToOneField(Quest)

    # The initial object
    initial_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE,
                                             limit_choices_to=ALLOWED_INITIAL_CONTENT_TYPES)
    initial_object_id = models.PositiveIntegerField(help_text="The id of the object for this content type. "
                                                              "You may need to look this up.  E.g. If the initial type "
                                                              "is a quest, then the quest's id goes here.")
    initial_content_object = GenericForeignKey('initial_content_type', 'initial_object_id')

    parent_scape = models.ForeignKey('self', blank=True, null=True,
                                     help_text="The map/scape preceding this one, so it can be linked back to",
                                     on_delete=models.CASCADE)
    is_the_primary_scape = models.BooleanField(default=False,
                                               help_text="There can only be one primary map/scape. Making this True "
                                                         "will change all other map/scapes will be set to False.")
    last_regeneration = models.DateTimeField(default=timezone.now)
    autobreak = models.BooleanField(default=True,
                                    help_text="Stop the map when reaching a quest with a ~ or a badge with a *."
                                              "If this is unchecked, the map is gonna be CRAZY!")
    elements_json = models.TextField(
        blank=True,
        null=True,
        help_text="A cache of the json representing all elements in this scape.  Updated when the map is recalculated.",
    )
    class_styles_json = models.TextField(
        blank=True,
        null=True,
        help_text="A cache of the json representing element-specific styles in this scape.  Updated when the map is recalculated.",
    )

    class Meta:
        unique_together = (('initial_content_type', 'initial_object_id'),)
        verbose_name = "Quest Map"
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # if this is the first scape, make it primary
        if CytoScape.objects.all().count() == 0:
            self.is_the_primary_scape = True
        # if setting this to primary, turn other primary to False
        elif self.is_the_primary_scape:
            try:
                current_primary_scape = CytoScape.objects.get(is_the_primary_scape=True)
                if self != current_primary_scape:
                    current_primary_scape.is_the_primary_scape = False
                    current_primary_scape.save()
            except CytoScape.DoesNotExist:
                pass
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('djcytoscape:quest_map', kwargs={'scape_id': self.id})

    objects = CytoScapeManager()

    class InitialObjectDoesNotExist(Exception):
        """The initial object for this does not exist, it may have been deleted"""

    def elements(self):
        elements = self.cytoelement_set.all()
        return elements.select_related('data_parent', 'data_source', 'data_target')

    def elements_dict(self):
        elements = self.elements()
        nodes = elements.filter(group=CytoElement.NODES)
        edges = elements.filter(group=CytoElement.EDGES)

        nodes_list = [node.json_dict() for node in nodes]
        edges_list = [edge.json_dict() for edge in edges]

        elements_dict = {
            'nodes': nodes_list,
            'edges': edges_list,
        }
        return elements_dict

    def generate_elements_json(self):
        return json.dumps(self.elements_dict())

    def class_styles_list(self):
        ls = []
        for element in self.elements():
            if element.id_styles:
                ls.append(
                    element.get_selector_styles_json_dict("#" + str(element.id), element.id_styles)
                )
        return ls

    def generate_class_styles_json(self):
        return json.dumps(self.class_styles_list())

    def update_cache(self):
        self.elements_json = self.generate_elements_json()
        self.class_styles_json = self.generate_class_styles_json()
        self.save()

    @staticmethod
    def generate_label(obj):
        # set max label length in characters
        # object labels with large xp values require a shorter name length so all values when combined comply with max label length
        if hasattr(obj, 'xp'):
            max_len = 46 - len(str(obj.xp))
        else:
            max_len = 44

        post = ""
        pre = ""
        if type(obj) is Badge:
            pre = "Badge: "
        elif type(obj) is Rank:
            pre = "Rank: "

        title = pre + str(obj)
        # shorten the end
        if len(title) > max_len:
            title = title[:(max_len - 3)] + "..."  # + title[-int(l/2-2):]

        if hasattr(obj, 'xp'):
            if hasattr(obj, 'xp_can_be_entered_by_students') and obj.xp_can_be_entered_by_students:
                plus = "+"
            else:
                plus = ""
            post = f" ({str(obj.xp)}{plus})"
        elif type(obj) is Category:
            post = f" ({str(obj.xp_sum())} XP)"

        # if hasattr(obj, 'max_repeats'): # stop trying to be fancy!
        #     if obj.max_repeats != 0:
        #         post += ' ⟲'

        # json.dumps to escape special characters in the object, such as single and double quote marks.
        # dumps not working...just try manually
        title = title.replace('"', '\\"')
        return title + post

    def get_last_node_in_campaign(self, parent_node, offset=0):
        """
        :param offset: offset from last node by this (i.e. 1 --> second last node)
        :param parent_node: the compound node/parent, i.e. campaign
        :return: the most recent node added to the campaign (added to the compound/parent node) by using the highest id
        """
        try:
            # latest normally used with dates, but actually works with other fields too!
            # return CytoElement.objects.all_for_campaign(self, parent_node).latest('id')
            qs = CytoElement.objects.all_for_campaign(self, parent_node).order_by('-id')
            return qs[offset]
        except self.DoesNotExist:
            return None

    def create_first_node(self, obj):
        """ Creates the first node from `obj`, then if this map has a parent, creates an aditiona node to link back to back to the parent scape/map.
        Returns the first node."""

        # the initial node in this map
        first_node, _ = self.create_node_from_object(obj, initial_node=True)

        if self.parent_scape:
            # the node to link to the parent map
            parent_node, _ = CytoElement.objects.get_or_create(
                scape=self,
                group=CytoElement.NODES,
                label=f"{self.parent_scape.name} Quest Map",
                href=reverse('maps:quest_map', args=[self.parent_scape.id]),
                classes='link parent-map'
            )

            # link them together with an edge
            CytoElement.objects.get_or_create(
                scape=self,
                group=CytoElement.EDGES,
                data_source=parent_node,
                data_target=first_node,
            )

        return first_node

    def create_child_map_node(self, obj, data_source):
        """ If this obj is a transition node (to a new map, make a node to link to the next map"""
        ct = ContentType.objects.get_for_model(obj)
        # obj = ct.get_object_for_this_type(id=obj.id)

        child_map_qs = CytoScape.objects.filter(initial_content_type=ct.id, initial_object_id=obj.id)
        if child_map_qs.exists():
            child_map = child_map_qs[0]
            label = f"{child_map.name} Map"
        else:
            label = "The Void"

        child_map_node, _ = CytoElement.objects.get_or_create(
            scape=self,
            group=CytoElement.NODES,
            label=label,
            href=reverse('maps:quest_map_interlink', args=[ct.id, obj.id, self.id]),  # <content_type_id>, <object_id>, <originating_scape_id>
            classes="link child-map",
        )

        # link them together with an edge
        CytoElement.objects.get_or_create(
            scape=self,
            group=CytoElement.EDGES,
            data_source=data_source,
            data_target=child_map_node,
        )

        return child_map_node

    def create_node_from_object(self, obj, initial_node=False):
        # If node node doesn't exist already, create a new one

        # check for an icon
        if hasattr(obj, 'get_icon_url'):
            img_url = obj.get_icon_url()
        else:
            img_url = "none"

        # check for map transition
        map_transition = False
        if hasattr(obj, 'map_transition'):
            map_transition = obj.map_transition

        new_node, created = CytoElement.objects.get_or_create(
            scape=self,
            group=CytoElement.NODES,
            selector_id=CytoElement.generate_selector_id(obj),
            label=self.generate_label(obj),
            defaults={
                      'id_styles': "'background-image': '" + img_url + "'",
                      'classes': type(obj).__name__,
                      'href': obj.get_absolute_url(),
                      'is_transition': map_transition,
                     }
        )

        # if this is a transition node (to a new map), format it and link it.
        if not initial_node and self.is_transition_node(new_node):
            new_node.convert_to_transition_node(obj, self)

        return new_node, created

    def init_temp_campaign_list(self):
        """
        Create a new member variable `campaign_list` or clear it if it already exists
        """
        self.campaign_list = []

    def get_temp_campaign(self, campaign_id) -> TempCampaign:
        for campaign in self.campaign_list:
            try:
                if campaign.node_id == campaign_id:
                    return campaign
            except ValueError:
                pass
        return None

    def add_to_campaign(self, obj, target_node, source_node):
        """
        Checks if obj is in a campaign, if so, gets or creates the campaign_node (Parent/compound node)
        and adds it as the parent (compound) node.  Also registers the target_node and source_node with the TempCampaign (for edges later)
        :param source_node: node representing the target_node's prereq
        :param obj: the django object currently being processed, represented by the target_node
        :param target_node: node of the reliant object, obj
        :return: campaign_node = None if obj isn't part of a campaign, otherwise = the campaign_node (i.e. parent_node)
        campaign_created = False if obj is in campaign, but the campaign was created by an earlier node
        """
        # If part of a campaign, create parent and add to "parent" node, i.e. compound node
        campaign_node = None
        campaign = None
        campaign_created = False

        # Check if the obj has a campaign attribute, currently only Quest objects have this, but obj could be a Badge or other prereq model
        if hasattr(obj, 'campaign') and obj.campaign is not None:
            campaign = obj.campaign

            # Create a node for this campaign (or get it if it already exists)
            campaign_node, campaign_created = CytoElement.objects.get_or_create(
                scape=self,
                group=CytoElement.NODES,
                label=CytoScape.generate_label(obj.campaign),
                classes="campaign",
                # defaults={'attribute': value},
            )

            # Add a parent (i.e. campaign) to the target node (to form a compound node)
            target_node.data_parent = campaign_node
            target_node.save()

            # TempCampaign utility for cleaning up the edges and making the resulting map look good, after the entire map is built
            if campaign_created:
                self.campaign_list.append(TempCampaign(campaign_node.id))
            temp_campaign = self.get_temp_campaign(campaign_node.id)  # not a Django model, so custom method

            # TODO: Nodes might be present multiple times through different source nodes?  check and combine
            temp_campaign.add_node(target_node.id, source_node.id)

        return campaign, campaign_node, campaign_created

    def fix_nonsequential_campaign_edges(self):
        """
        cyto dagre layout doesn't support compound/parent nodes, so for non-sequential/non-directed campaigns
        (i.e. all quests are available concurrently) we need to:
         1. add invisible edges joining the quests
         2. remove edges between common prereqs and quests
         3. add edges between common prereqs and campaign/compound/parent node
         4. add invisible edge (for structure) from prereqs to first node
         5. (deprecated) remove edges between quests and common reliants
         6. (deprecated) add edges between campaign/compound/parent node and common reliants
         7. (deprecated) add invisible edge (for structure) from last node to common reliants
         8. add invisible edge (for structure) from last node to campaign reliants
        """

        for campaign in self.campaign_list:

            last_node = campaign.get_last_node()

            common_prereq_ids = campaign.get_common_prereq_node_ids()
            if common_prereq_ids:  # then non-sequential campaign

                # 1. add invisible edges joining the quests
                for current_node in campaign.nodes:
                    next_node = campaign.get_next_node(current_node)
                    if next_node:
                        CytoElement.objects.get_or_create(
                            scape=self,
                            group=CytoElement.EDGES,
                            data_source_id=current_node.id,
                            data_target_id=next_node.id,
                            defaults={'classes': 'hidden', },
                        )

                first_node = campaign.get_first_node()
                for prereq_node_id in common_prereq_ids:

                    # 2. remove edges between common prereqs and quests
                    for quest_node in campaign.nodes:
                        # we already know all quests have this prereq node in common, so the edges should all exist
                        # unless quest has internal prereq...
                        if prereq_node_id in quest_node.prereq_node_ids:
                            edge_node = get_object_or_404(CytoElement,
                                                          data_source_id=prereq_node_id,
                                                          data_target_id=quest_node.id)
                            edge_node.delete()

                    # 3. add edges between common prereqs and campaign/compound/parent node
                    CytoElement.objects.get_or_create(
                        scape=self,
                        group=CytoElement.EDGES,
                        data_source_id=prereq_node_id,
                        data_target_id=campaign.node_id,
                        # defaults={'attribute': value},
                    )

                    # 4. add invisible edge (for structure) from prereqs to first node
                    CytoElement.objects.get_or_create(
                        scape=self,
                        group=CytoElement.EDGES,
                        data_source_id=prereq_node_id,
                        data_target_id=first_node.id,
                        defaults={'classes': 'hidden', }
                    )

                # TODO this should no longer be required now that Campaigns can be set as prerequisites
                # TODO but will break old maps / prereq setups if removed
                reliant_node_ids = campaign.get_common_reliant_node_ids()
                if reliant_node_ids:
                    for reliant_node_id in reliant_node_ids:

                        # 5 remove edges between quests and common reliants
                        for quest_node in campaign.nodes:
                            # we already know all quests have this reliant node in common, so the edges should all exist
                            # unless it has an internal reliant...
                            if reliant_node_id in quest_node.reliant_node_ids:
                                edge_node = get_object_or_404(CytoElement,
                                                              data_source_id=quest_node.id,
                                                              data_target_id=reliant_node_id)
                                edge_node.delete()

                        # 6. add edges between campaign/compound/parent node and common reliants
                        CytoElement.objects.get_or_create(
                            scape=self,
                            group=CytoElement.EDGES,
                            data_source_id=campaign.node_id,
                            data_target_id=reliant_node_id,
                            # defaults={'attribute': value},
                        )

                        # 7. add invisible edge (for structure) from last node to reliants
                        CytoElement.objects.get_or_create(
                            scape=self,
                            group=CytoElement.EDGES,
                            data_source_id=last_node.id,
                            data_target_id=reliant_node_id,
                            defaults={'classes': 'hidden', }
                            # defaults={'attribute': value},
                        )

            # 8. add invisible edge (for structure) from last node to campaign reliants
            # TODO actually add nodes to the campaign_reliant_nodes_ids list!!!!
            for reliant_node_id in campaign.campaign_reliant_node_ids:
                CytoElement.objects.get_or_create(
                    scape=self,
                    group=CytoElement.EDGES,
                    data_source_id=last_node.id,
                    data_target_id=reliant_node_id,
                    defaults={'classes': 'hidden', }
                    # defaults={'attribute': value},
                )

    def find_reliant_objects_and_add_target_nodes(self, source_obj, source_node: CytoElement):
        """ Recursivly connect nodes together with edges.  Starts at the top and works down through all objects
        that rely on the source_obj as a prerequisite.

        source_obj: the current django object being processed (could be any mappable prerequisite, such as a Quest, Badge, or Campaign)
        source_node: the cytoscape node representing the source_obj

        Other names:
        parent node is confusing, but refers to the compound nodes that group other nodes together (i.e. campaigns)
        variables with names such as data_parent, parent_node, etc, are Campaigns that a quest might be in.
        In graph terms these are called parent nodes or compound nodes

        target_nodes are nodes created from reliant objects (objects that rely on the source_obj as a prerequisite)
        """
        reliant_objects = source_obj.get_reliant_objects(exclude_NOT=True, sort=True)

        for obj in reliant_objects:
            # source_node
            #  > reliant obj1 (target node 1)
            #  > reliant obj2 (target node 2)
            #  > ...

            # create or get the node represented by the reliant object
            target_node, node_created = self.create_node_from_object(obj)

            # if source node is in a compound node (has a parent / campaign), add target_node as a reliant in the temp_campaign
            if source_node.data_parent:
                temp_campaign: TempCampaign = self.get_temp_campaign(source_node.data_parent.id)
                temp_campaign.add_reliant(source_node.id, target_node.id)

            # if the source node is ITSELF a campaign (parent of a compound node)
            if source_node.is_parent():
                temp_campaign: TempCampaign = self.get_temp_campaign(source_node.id)
                temp_campaign.add_campaign_reliant(target_node.id)

            # add new_node to a campaign/compound/parent, if required
            campaign_obj, campaign_node, campaign_node_created = self.add_to_campaign(obj, target_node, source_node)

            # If this is the first time this campaign has been encountered, then check if IT has any reliant objects
            if campaign_node_created:
                self.find_reliant_objects_and_add_target_nodes(campaign_obj, campaign_node)
                # these nodes need to be added to the temp_campaigncampaign_reliant_node_ids for later cleanup

            # add a class to alternate prerequisites edges so they can be styled differently if desired
            if obj.has_or_prereq() or obj.has_inverted_prereq():
                # add "alternate" class
                defaults = {'classes': 'complicated-prereqs'}
            else:
                defaults = {}

            # TODO: should add number of times prereq is required, similar to repeat edges below
            CytoElement.objects.get_or_create(
                scape=self,
                group=CytoElement.EDGES,
                data_source=source_node,
                data_target=target_node,
                defaults=defaults,
            )

            # If repeatable, also add circular edge
            if hasattr(obj, 'max_repeats'):
                if obj.max_repeats != 0:
                    if obj.max_repeats < 0:
                        label = '∞'
                    else:
                        label = 'x' + str(obj.max_repeats)

                    CytoElement.objects.get_or_create(
                        scape=self,
                        group=CytoElement.EDGES,
                        data_source=target_node,
                        data_target=target_node,
                        defaults={
                            'label': label,
                            'classes': 'repeat-edge',
                        },
                    )

            # recursive, continue adding if this is a new node, and not a closing node
            if node_created and not self.is_transition_node(target_node):
                self.find_reliant_objects_and_add_target_nodes(obj, target_node)

    def is_transition_node(self, node: CytoElement):
        """ A transition node represents an obj.map_transition attribute set to True (saved in node.is_transition_)
        DEPRECATED: Also return True if node.label begins with the tilde '~' or contains an astrix '*'
        But only do this if autobreaking is turned on
        """
        if self.autobreak:
            if node.is_transition:
                return True
            else:
                return node.label[0] == "~" or "*" in node.label
        else:
            return False

    @staticmethod
    def generate_map(initial_object, name, parent_scape=None, autobreak=True):

        scape = CytoScape(
            name=name,
            initial_content_object=initial_object,
            parent_scape=parent_scape,
            autobreak=autobreak,
        )
        scape.save()
        scape.calculate_nodes()
        return scape

    def calculate_nodes(self,):

        # Create the starting node from the initial quest, and a link back to the parent map if there is one
        first_node = self.create_first_node(self.initial_content_object)

        # Temp campaign list used to track funky edges required for compound nodes to display properly with dagre
        self.init_temp_campaign_list()

        # Add nodes reliant on the first_node, this is recursive and will generate all nodes until endpoints reached
        # Endpoints... not sure yet, but probably quests starting with '~' tilde character, or add a new field?
        self.find_reliant_objects_and_add_target_nodes(self.initial_content_object, first_node)

        # Add those funky edges for proper display of compound (parent) nodes in cyto dagre layout
        self.fix_nonsequential_campaign_edges()
        self.last_regeneration = timezone.now()
        self.update_cache()
        self.save()

    def regenerate(self):
        if self.initial_content_object is None:
            self.delete()
            raise (self.InitialObjectDoesNotExist)

        # Delete existing nodes
        CytoElement.objects.all_for_scape(self).delete()
        self.calculate_nodes()
