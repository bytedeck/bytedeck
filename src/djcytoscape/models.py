import ast
import json

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


class CytoStyleClass(models.Model):
    name = models.CharField(max_length=20, help_text="a period will be added before the name when used as a selector")
    styles = models.TextField(blank=True, null=True,
                              help_text="Format = key1: value1, key2: value2, ... (see http://js.cytoscape.org/#style)")

    def __str__(self):
        return self.name


class CytoStyleSet(models.Model):
    DEFAULT_NAME = "Default"

    DEFAULT_INIT_OPTIONS = "  minZoom: 0.5, \n" \
                           "  maxZoom: 1.5, \n" \
                           "  wheelSensitivity: 0.1, \n" \
                           ""

    DEFAULT_LAYOUT_OPTIONS = "'nodeSep': 25, \n 'rankSep': 10, \n"

    DEFAULT_NODE_STYLES = "'label':         'data(label)', \n" \
                          "'text-valign':   'center', 'text-halign': 'right', \n" \
                          "'text-margin-x': '-270', \n" \
                          "'background-fit':'contain', \n" \
                          "'shape':         'roundrectangle', \n" \
                          "'background-opacity': 0, \n" \
                          "'background-position-x': 0, \n" \
                          "'width':         300, \n" \
                          "'border-width':  1, \n" \
                          "'padding-right': 5, 'padding-left':5, 'padding-top':5, 'padding-bottom':5, \n" \
                          "'text-events':   'yes'," \
                          ""

    DEFAULT_EDGE_STYLES = "'width': 1, \n" \
                          "'curve-style':   'bezier', \n" \
                          "'line-color':    'black', \n" \
                          "'line-style':    'solid', \n" \
                          "'target-arrow-shape': 'triangle-backcurve', \n" \
                          "'target-arrow-color':'black', \n" \
                          "'text-rotation': 'autorotate', \n" \
                          "'label':         'data(label)', \n" \
                          ""

    DEFAULT_PARENT_STYLES = "'text-rotation':   '-90deg', \n" \
                            "'text-halign':     'left', \n" \
                            "'text-margin-x':   -10, \n" \
                            "'text-margin-y':   -40, \n" \
                            ""

    LAYOUT_CHOICES = (('null', 'null'),
                      ('random', 'random'),
                      ('grid', 'grid'),
                      ('circle', 'circle'),
                      ('concentric', 'concentric'),
                      ('breadthfirst', 'breadthfirst'),
                      ('cose', 'cose'),
                      ('cola', 'cola'),
                      ('dagre', 'dagre'),
                      )

    JAVASCRIPT_DEFAULT = "$(document).ready(function() { \n" \
                         "\n" \
                         "});\n"

    name = models.CharField(max_length=50)
    init_options = models.TextField(blank=True, null=True, default=DEFAULT_INIT_OPTIONS,
                                    help_text="Format = key1: value1, key2: value2, ... (see "
                                              "http://js.cytoscape.org/#core/initialisation)")
    layout_name = models.CharField(max_length=50, default="dagre", choices=LAYOUT_CHOICES,
                                   help_text="see http://js.cytoscape.org/#layouts")
    layout_options = models.TextField(blank=True, null=True, default=DEFAULT_LAYOUT_OPTIONS,
                                      help_text="Format = key1: value1, key2: value2, ... (see "
                                                "http://js.cytoscape.org/#layouts)")
    node_styles = models.TextField(blank=True, null=True, default=DEFAULT_NODE_STYLES,
                                   help_text="Format = key1: value1, key2: value2, ... (see "
                                             "http://js.cytoscape.org/#style)")
    edge_styles = models.TextField(blank=True, null=True, default=DEFAULT_EDGE_STYLES,
                                   help_text="Format = key1: value1, key2: value2, ... (see "
                                             "http://js.cytoscape.org/#style)")
    parent_styles = models.TextField(blank=True, null=True, default=DEFAULT_PARENT_STYLES,
                                     help_text="Format = key1: value1, key2: value2, ... (see "
                                               "http://js.cytoscape.org/#style)")
    style_classes = models.ManyToManyField(CytoStyleClass, blank=True)
    javascript = models.TextField(blank=True, null=True, default=JAVASCRIPT_DEFAULT,
                                  help_text="Will be placed inside script tags. JQuery available. "
                                            "See http://js.cytoscape.org/#core")

    def __str__(self):
        return self.name

    def get_node_styles(self):
        if self.node_styles:
            return self.get_selector_styles_json('node', self.node_styles)
        return ""

    def get_edge_styles(self):
        if self.edge_styles:
            return self.get_selector_styles_json('edge', self.edge_styles)
        return ""

    def get_parent_styles(self):
        if self.parent_styles:
            return self.get_selector_styles_json('$node > node', self.parent_styles)
        return ""

    def get_init_options(self):
        if self.init_options:
            return self.init_options
        return ""

    def get_layout_json(self):
        json_str = ""
        json_str += "  layout: { \n"
        json_str += "    name: '" + self.layout_name + "', \n"
        if self.layout_options:
            json_str += self.layout_options
        json_str += "  }, \n"
        return json_str

    def get_classes(self):
        json_str = ""
        style_classes = self.style_classes.all()
        for style_class in style_classes:
            selector = "." + style_class.name
            json_str += self.get_selector_styles_json(selector, style_class.styles)
        return json_str

    @staticmethod
    def get_selector_styles_json(selector, styles):
        json_str = "    { \n"
        json_str += "      selector: '" + selector + "', \n"
        json_str += "      style: { \n"
        json_str += styles
        json_str += "      } \n"
        json_str += "    }, \n"
        return json_str


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
    href = models.URLField(blank=True, null=True)

    objects = CytoElementManager()

    def __str__(self):
        return str(self.id) + ": " + str(self.label)

    def get_data_dict(self):
        """:return data_dict text field as a python dictionary."""
        return ast.literal_eval(self.data_dict)

    def add_data(self, key, value):
        data = self.get_data_dict()
        data[key] = value
        self.data_dict = data
        self.save()

    def get_data(self, key):
        """:return the value for this key.  None if key doesn't exist."""
        data = self.get_data_dict()
        return data.get(key)

    def get_data_json(self):
        return json.dumps(self.data_dict)

    def has_parent(self):
        return self.data_parent is not None

    def is_edge(self):
        return self.data_source and self.data_target

    def is_node(self):
        return not self.is_edge()

    def json(self):
        json_str = "    {\n"
        # json_str +=         "      group: '" + self.group + "',\n"
        json_str += "      data: {\n"
        json_str += "        id: " + str(self.id) + ",\n"
        if self.label:
            json_str += '        label: "' + self.label + '",\n'  # TODO: should properly escape string
        if self.has_parent():
            json_str += "        parent: " + str(self.data_parent.id) + ",\n"
        elif self.is_edge():
            json_str += "        source: " + str(self.data_source.id) + ",\n"
            json_str += "        target: " + str(self.data_target.id) + ",\n"
            json_str += "        minLen: " + str(self.min_len) + ",\n"
            # json_str += "        edgeWeight: 1, \n"  # '" + str(self.edge_weight) + "',\n"
        if self.href:
            json_str += "        href: '" + self.href + "',\n"
        json_str += "      },\n "  # end data
        if self.classes:
            json_str += "     classes: '" + self.classes + "',\n"
        json_str += "    },\n "

        return json_str


class TempCampaignNode(object):
    def __init__(self, id_, prereq_node_id=None):
        self.id = id_
        self.prereq_node_ids = []
        self.reliant_node_ids = []
        if prereq_node_id:
            self.prereq_node_ids.append(prereq_node_id)

    def __str__(self):
        return str(self.id)


class TempCampaign(object):
    """
    Temporary structure used to help build the cytoscape, generates lists for each campaign to make it easier to
    properly generate edges to give the desired layout.
    """

    def __init__(self, parent_node_id):
        self.node_id = parent_node_id
        # self.child_node_ids = []  # Quests in the campaign
        # self.reliant_node_ids = []  # Quests that rely on completion of quests in the campaign
        # self.prereq_node_ids = []  # External quests that are required for quests in the campaign
        # self.internal_prereq_node_ids = []
        self.nodes = []  # a list of TempCampaignNodes in the Campaign

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
        node = self.get_node(node_id)
        node.reliant_node_ids.append(reliant_node_id)

    # def add_prereq(self, prereq_node_id):
    #     # prereqs can't be in the campaign already, so check:
    #     if prereq_node_id not in self.child_node_ids:
    #         self.prereq_node_ids.append(prereq_node_id)
    #     else:
    #         self.internal_prereq_node_ids.append(prereq_node_id)

    def get_last_node(self):
        return self.nodes[-1]

    def get_first_node(self):
        return self.nodes[0]

    # def get_first_prereq_id(self):
    #     return self.prereq_node_ids[0]

    # def get_last_reliant_id(self):
    #     if self.reliant_node_ids:
    #         return self.reliant_node_ids[-1]
    #     else:
    #         return None

    def get_node(self, node_id):
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None
    #
    # def get_next_node_id(self, current_node_id):
    #     current_node = self.get_node(current_node_id)
    #     next_loc = self.nodes.index(current_node) + 1
    #     if len(self.nodes) > next_loc:
    #         return self.nodes[next_loc].id

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

        # num_children = len(self.child_node_ids)
        #
        # reliant_on_all_ids = []
        # for reliant_id in set(self.reliant_node_ids):  # set( myList ) contains only unique values
        #     count = self.reliant_node_ids.count(reliant_id)
        #     if count == num_children:  # if all children point to the reliant node, consider it reliant
        #                                # on the campaign
        #         reliant_on_all_ids.append(reliant_id)
        # return reliant_on_all_ids

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

        # for prereq_id in set(self.prereq_node_ids):
        #     count = self.prereq_node_ids.count(prereq_id)
        #     count_internal = len(self.internal_prereq_node_ids)
        #     print(count)
        #     print(count_internal)
        #     print(num_children)
        #     # if all children require this prereq (or an internal), consider it a prereq for the campaign
        #     if count + count_internal == num_children:
        #         prereq_for_all_ids.append(prereq_id)
        # return prereq_for_all_ids

    def is_non_sequential(self):
        # If there is at least one common prereq node
        return self.get_common_prereq_node_ids() is True


class CytoScapeManager(models.Manager):
    def generate_random_tree_scape(self, name, size=100, container_element_id="cy"):
        scape = CytoScape(
            name=name,
            container_element_id=container_element_id,
            layout_name='breadthfirst',
            layout_options="directed: true, spacingFactor: " + str(1.75 * 30 / size),
        )
        scape.save()

        # generate starting node
        mother_node = CytoElement(scape=scape, group=CytoElement.NODES, )
        mother_node.save()
        node_list = [mother_node]
        count = 1
        while node_list and count < size:
            current_node = random.choice(node_list)
            # 10% chance to split branch, 10% to cap it
            split = random.random()
            children = 1
            if split < .10:
                children = random.randint(1, 3)  # 1 to 3

            if current_node is mother_node:
                children = 10
            if split < 90:  # create the target nodes, connect them to source, add them to list
                for i in range(0, children):
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

    def generate_random_scape(self, name, size=100, container_element_id="cy"):
        new_scape = CytoScape(
            name=name,
            container_element_id=container_element_id
        )
        new_scape.save()

        # generate nodes
        for i in range(0, size):
            new_node = CytoElement(
                scape=new_scape,
                group=CytoElement.NODES,
            )
            new_node.save()

        # generate edges
        for i in range(0, size * 3):
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


class CytoScape(models.Model):
    ALLOWED_INITIAL_CONTENT_TYPES = models.Q(app_label='quest_manager', model='quest') | \
                                    models.Q(app_label='badges', model='badge') | \
                                    models.Q(app_label='courses', model='rank')

    name = models.CharField(max_length=250)
    style_set = models.ForeignKey(CytoStyleSet, null=True, on_delete=models.SET_NULL)

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
    container_element_id = models.CharField(max_length=50, default="cy",
                                            help_text="id of the html element where the graph's canvas will be placed")
    autobreak = models.BooleanField(default=True,
                                    help_text="Stop the map when reaching a quest with a ~ or a badge with a *."
                                              "If this is unchecked, the map is gonna be CRAZY!")

    class Meta:
        unique_together = (('initial_content_type', 'initial_object_id'),)

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
                    current_primary_scape.is_the_chosen_one = False
                    current_primary_scape.save()
            except CytoScape.DoesNotExist:
                pass
        super(CytoScape, self).save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('djcytoscape:quest_map', kwargs={'scape_id': self.id})

    objects = CytoScapeManager()

    def json(self):
        elements = CytoElement.objects.all_for_scape(self)

        json_str = "cytoscape({ \n"
        json_str += "  container: document.getElementById('" + self.container_element_id + "'), \n"
        json_str += "  elements: [ \n"
        for element in elements:
            json_str += element.json()
        json_str += "  ], \n"
        json_str += self.style_set.get_layout_json()
        json_str += "  style: [ \n"
        json_str += self.style_set.get_node_styles()
        json_str += self.style_set.get_edge_styles()
        json_str += self.style_set.get_parent_styles()
        json_str += self.style_set.get_classes()
        # json_str += self.get_selector_styles_json('.Quest', self.quest_styles)
        # json_str += self.get_selector_styles_json('.Badge', self.badge_styles)
        # json_str += self.get_selector_styles_json('.campaign', self.campaign_styles)
        # json_str += self.get_selector_styles_json('.hidden', self.hidden_styles)
        # json_str += self.get_selector_styles_json('.link', self.link_styles)
        # json_str += self.get_selector_styles_json('.link_hover', self.link_hover_styles)
        for element in elements:
            if element.id_styles:
                json_str += self.get_selector_styles_json('#' + str(element.id), element.id_styles)
        json_str += "  ], \n"  # end style: [
        json_str += self.style_set.get_init_options()
        json_str += "});"

        return json_str

    @staticmethod
    def get_selector_styles_json(selector, styles):
        json_str = "    { \n"
        json_str += "      selector: '" + selector + "', \n"
        json_str += "      style: { \n"
        json_str += styles
        json_str += "      } \n"
        json_str += "    }, \n"
        return json_str

    @staticmethod
    def generate_label(obj):
        max_len = 44  # max label length in characters
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
            post = " (" + str(obj.xp) + ")"
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

    def add_node_from_object(self, obj, initial_node=False):
        # If node node doesn't exist already, create a new one

        # check for an icon
        if hasattr(obj, 'get_icon_url'):
            img_url = obj.get_icon_url()
        else:
            img_url = "none"

        new_node, created = CytoElement.objects.get_or_create(
            scape=self,
            group=CytoElement.NODES,
            label=self.generate_label(obj),
            defaults={'id_styles': "'background-image': '" + img_url + "'",
                      'classes': type(obj).__name__, }
        )

        # if this is a transition node (to a new map), add the link to href field. And add the "link" class
        if not initial_node and self.is_transition_node(new_node):
            ct = ContentType.objects.get_for_model(obj)
            obj = ct.get_object_for_this_type(id=obj.id)

            # <content_type_id>, <object_id>, <originating_scape_id>
            new_node.href = reverse('maps:quest_map_interlink', args=[ct.id, obj.id, self.id])
            new_node.classes += " link"
            new_node.save()
        else:  # add a link to the object itself
            new_node.href = obj.get_absolute_url()
            new_node.save()

        return new_node, created

    def init_temp_campaign_list(self):
        """
        Create a new member variable `campaign_list` or clear it if it already exists
        """
        self.campaign_list = []

    def get_temp_campaign(self, campaign_id):
        for campaign in self.campaign_list:
            try:
                if campaign.node_id == campaign_id:
                    return campaign
            except ValueError:
                pass
        return None

    def add_to_campaign(self, obj, node, mother_node):
        """
        Checks if obj is in a campaign, if so, gets or creates the campaign_node (Parent/compound node)
        and adds is as the parent node.  Also registers the node and parent with the TempCampaign (for edges later)
        :param mother_node: prereq node
        :param obj:
        :param node: node of the object
        :return: campaign_node = None if obj isn't part of a campaign, otherwise = the campaign_node (i.e. parent_node)
        campaign_created = False if obj is in campaign, but the campaign was created by an earlier node
        """
        # If part of a campaign, create parent and add to "parent" node, i.e. compound node
        campaign_node = None
        campaign_created = False
        if hasattr(obj, 'campaign') and obj.campaign is not None:
            # parent_name = str(obj.campaign)
            campaign_node, campaign_created = CytoElement.objects.get_or_create(
                scape=self,
                group=CytoElement.NODES,
                label=str(obj.campaign),
                classes="campaign",
                # defaults={'attribute': value},
            )
            # Add parent
            node.data_parent = campaign_node
            node.save()

            # TempCampaign utility
            if campaign_created:
                self.campaign_list.append(TempCampaign(campaign_node.id))
            temp_campaign = self.get_temp_campaign(campaign_node.id)
            # temp_campaign.add_child(node.id)
            # TODO: Nodes might be present multiple times through different mothers?  check and combine
            temp_campaign.add_node(node.id, mother_node.id)
            # temp_campaign.add_prereq(mother_node.id)

        return campaign_node, campaign_created

    def fix_nonsequential_campaign_edges(self):
        """
        cyto dagre layout doesn't support compound/parent nodes, so for non-sequential/non-directed campaigns
        (i.e. all quests are available concurrently) we need to:
         1. add invisible edges joining the quests
         2. remove edges between common prereqs and quests
         3. remove edges between quests and common reliants
         4. add edges between common prereqs and campaign/compound/parent node
         5. add edges between campaign/compound/parent node and common reliants
         6. add invisible edge (for structure) from prereqs to first node
         7. add invisible edge (for structure) from last node to reliants
        """

        for campaign in self.campaign_list:

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

                    # 4. add edges between common prereqs and campaign/compound/parent node
                    CytoElement.objects.get_or_create(
                        scape=self,
                        group=CytoElement.EDGES,
                        data_source_id=prereq_node_id,
                        data_target_id=campaign.node_id,
                        # defaults={'attribute': value},
                    )

                    # 6. add invisible edge (for structure) from prereqs to first node
                    CytoElement.objects.get_or_create(
                        scape=self,
                        group=CytoElement.EDGES,
                        data_source_id=prereq_node_id,
                        data_target_id=first_node.id,
                        defaults={'classes': 'hidden', }
                    )

                last_node = campaign.get_last_node()
                reliant_node_ids = campaign.get_common_reliant_node_ids()
                if reliant_node_ids:
                    for reliant_node_id in reliant_node_ids:

                        # 3 remove edges between quests and common reliants
                        for quest_node in campaign.nodes:
                            # we already know all quests have this reliant node in common, so the edges should all exist
                            # unless it has an internal reliant...
                            if reliant_node_id in quest_node.reliant_node_ids:
                                edge_node = get_object_or_404(CytoElement,
                                                              data_source_id=quest_node.id,
                                                              data_target_id=reliant_node_id)
                                edge_node.delete()

                        # 5. add edges between campaign/compound/parent node and common reliants
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

    def add_reliant(self, current_obj, mother_node):
        reliant_objects = current_obj.get_reliant_objects()
        for obj in reliant_objects:
            # mother_node
            #  > obj (reliant node 1)
            #  > obj (reliant node 2)
            #  > ...

            # create the new reliant node if it doesn't already exist
            new_node, created = self.add_node_from_object(obj)

            # if mother node is in a campaign/parent, add new_node as a reliant in the temp_campaign
            if mother_node.data_parent:
                temp_campaign = self.get_temp_campaign(mother_node.data_parent.id)
                temp_campaign.add_reliant(mother_node.id, new_node.id)

            # add new_node to a campaign/compound/parent, if required
            self.add_to_campaign(obj, new_node, mother_node)

            # TODO: should add number of times prereq is required, similar to repeat edges below
            CytoElement.objects.get_or_create(
                scape=self,
                group=CytoElement.EDGES,
                data_source=mother_node,
                data_target=new_node,
                # defaults={'attribute': value},
            )

            # If repeatable, add circular edge
            # TODO: cool idea, but currently big edge gets in the way, need a tight small one.
            # if hasattr(obj, 'max_repeats'):
            #     if obj.max_repeats != 0:
            #         if obj.max_repeats < 0:
            #             label = '∞'
            #         else:
            #             label = 'x ' + str(obj.max_repeats)
            #         repeat_edge = CytoElement(
            #             scape=self, group=CytoElement.EDGES,
            #             data_source=new_node,
            #             data_target=new_node,
            #             label=label,
            #         )
            #         repeat_edge.save()

            # recursive, continue adding if this is a new node, and not a closing node
            if created and not self.is_transition_node(new_node):
                self.add_reliant(obj, new_node)

    def is_transition_node(self, node):
        """
        :return: True if node.label begins with the tilde '~' or contains an astrix '*'
        """
        if self.autobreak:
            return node.label[0] == "~" or "*" in node.label
        else:
            return False

    @staticmethod
    def generate_map(initial_object, name, parent_scape=None, container_element_id="cy", autobreak=True):

        if parent_scape:
            style_set = parent_scape.style_set
        else:
            style_set, created = CytoStyleSet.objects.get_or_create(name=CytoStyleSet.DEFAULT_NAME)

        scape = CytoScape(
            name=name,
            initial_content_object=initial_object,
            parent_scape=parent_scape,
            container_element_id=container_element_id,
            style_set=style_set,
            autobreak=autobreak,
        )
        scape.save()
        scape.calculate_nodes()
        return scape

    def calculate_nodes(self):
        # Create the starting node from the initial quest
        mother_node, created = self.add_node_from_object(self.initial_content_object, initial_node=True)
        # Temp campaign list used to track funky edges required for compound nodes to display properly with dagre
        self.init_temp_campaign_list()
        # Add nodes reliant on the mother_node, this is recursive and will generate all nodes until endpoints reached
        # Endpoints... not sure yet, but probably quests starting with '~' tilde character, or add a new field?
        self.add_reliant(self.initial_content_object, mother_node)
        # Add those funky edges for proper display of compound (parent) nodes in cyto dagre layout
        self.fix_nonsequential_campaign_edges()
        self.last_regeneration = timezone.now()
        self.save()

    def regenerate(self):
        # Delete existing nodes
        CytoElement.objects.all_for_scape(self).delete()
        self.calculate_nodes()
