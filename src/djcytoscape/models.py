import random
from badges.models import Badge
from django.core.exceptions import ObjectDoesNotExist

from django.core.urlresolvers import reverse
from django.db import models

from quest_manager.models import Quest


class CytoElementQuerySet(models.query.QuerySet):
    def all_scape(self, scape_id):
        return self.filter(scape_id=scape_id)

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
                                    help_text="indicates the compound node parent; blank/null => no parent")
    data_source = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True, related_name="sources",
                                    help_text="edge comes from this node")
    data_target = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True, related_name="targets",
                                    help_text="edge goes to this node")

    # position_x = models.IntegerField()
    # position_y = models.IntegerField()
    # rendered_position_x = models.IntegerField()
    # rendered_position_y = models.IntegerField()
    selected = models.BooleanField(default=False)
    selectable = models.BooleanField(default=True)
    locked = models.BooleanField(default=False)
    grabbable = models.BooleanField(default=True)
    classes = models.CharField(max_length=250, blank=True, null=True,
                               help_text="a space separated list of css class names for the element")
    label = models.CharField(max_length=50, blank=True, null=True,
                             help_text="if present, will be used as node label instead of id")
    # data_type = models.CharField(max_length=50, blank=True, null=True,
    #                          help_text="A tag to group nodes")

    objects = CytoElementManager()

    def is_parent(self):
        return self.data_parent is not None

    def is_edge(self):
        """
        :return: True if not a node parent and has a source and target
        """
        if self.is_parent():
            return False
        return self.data_source is not None and self.data_target is not None

    def is_node(self):
        """
        :return: True if not a node parent or an edge
        """
        if self.is_parent() or self.is_edge():
            return False
        return True

    def json(self):
        json_str = "    {\n"
        # json_str +=         "      group: '" + self.group + "',\n"
        json_str += "      data: {\n"
        json_str += "        id: '" + str(self.id) + "',\n"
        if self.label:
            json_str += "        label: '" + self.label + "',\n"
        if self.is_parent():
            json_str += "        parent: '" + str(self.data_parent.id) + "',\n"
        elif self.is_edge():
            json_str += "        source: '" + str(self.data_source.id) + "',\n"
            json_str += "        target: '" + str(self.data_target.id) + "',\n"
        json_str += "      },\n "
        if self.classes:
            json_str += "      classes: '" + self.classes + "',\n"
        json_str += "    },\n "

        return json_str


# class CytoStyle(models.Model):


class CytoLayout(models.Model):
    description = models.CharField(max_length=250)

    # Also common to all layouts:
    # animationEasing: undefined, // easing of animation if enabled
    # ready: undefined, // callback on layoutready
    # stop: undefined // callback on layoutstop
    # http://js.cytoscape.org/#layouts


class CytoScapeManager(models.Manager):
    def generate_random_tree_scape(self, name, size=100, container_element_id="cy"):
        scape = CytoScape(
            name=name,
            container_element_id=container_element_id,
            layout_name='breadthfirst',
            layout_options="directed: true, spacingFactor: " + str(1.75 * 30/size),
        )
        scape.save()

        # generate starting node
        mother_node = CytoElement(scape=scape, group=CytoElement.NODES,)
        mother_node.save()
        node_list = [mother_node]
        count = 1
        while node_list and count < size:
            current_node = random.choice(node_list)
            # 10% chance to split branch, 10% to cap it
            split = random.random()
            children = 1
            if split < .10:
                children = random.randint(1, 3) # 1 to 3

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


class CytoScape(models.Model):
    name = models.CharField(max_length=250)
    container_element_id = models.CharField(max_length=50, default="cy",
                                            help_text="id of the html element where the graph's canvas will be placed")
    layout_name = models.CharField(max_length=50, default="random",
                                   help_text="layout name according to cytoscape API: http://js.cytoscape.org/#layouts \
                                              null, random, preset, grid, circle, concentric, breadthfirst, cose, dagre")
    layout_options = models.TextField(null=True, blank=True, help_text="key1: value1, key2: value2, ...")
    node_styles = models.TextField(null=True, blank=True,
                                   default="label: 'data(id)'",
                                   help_text="key1: value1, key2: value2, ...")
    edge_styles = models.TextField(null=True, blank=True, help_text="key1: value1, key2: value2, ...")
    parent_styles = models.TextField(null=True, blank=True, help_text="key1: value1, key2: value2, ...")

    quest_styles = "'shape': 'roundrectangle'," \
                   "'color': '#000'," \
                   "'background-color':'#ccc'," \
                   ""

    badge_styles = "'shape': 'rectangle'," \
                   "'color': '#000'," \
                   "'background-color':'#fff'," \
                   ""

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('djcytoscape:detail', kwargs={'scape_id': self.pk})

    objects = CytoScapeManager()

    def json(self):
        elements = CytoElement.objects.all_for_scape(self)

        json_str = "cytoscape({ \n"
        json_str += "  container: document.getElementById('" + self.container_element_id + "'), \n"
        json_str += "  elements: [ \n"
        for element in elements:
            json_str += element.json()
        json_str += "  ], \n"
        json_str += "  layout: { \n"
        json_str += "    name: '" + self.layout_name + "', \n"
        if self.layout_options:
            json_str += self.layout_options
        json_str += "  }, \n"
        json_str += "  style: [ \n"
        if self.node_styles:
            json_str += self.get_selector_styles_json('node', self.node_styles)
        if self.edge_styles:
            json_str += self.get_selector_styles_json('edge', self.edge_styles)
        if self.parent_styles:
            json_str += self.get_selector_styles_json('parent', self.parent_styles)
        json_str += self.get_selector_styles_json('.Quest', self.quest_styles)
        json_str += self.get_selector_styles_json('.Badge', self.badge_styles)
        json_str += "  ], \n"
        json_str += "});"

        return json_str

    def get_selector_styles_json(self, selector, styles):
        json_str = "    { \n"
        json_str += "      selector: '" + selector + "', \n"
        json_str += "      style: { \n"
        json_str += styles
        json_str += "      } \n"
        json_str += "    }, \n"
        return json_str

    def add_reliant(self, current_obj, current_node):
        reliant_objects = current_obj.get_reliant_objects()
        for obj in reliant_objects:
            post = ""
            if hasattr(obj, 'xp'):
                post = " (" + str(obj.xp) + ")"

            pre = ""
            if type(obj) is Badge:
                pre = "Badge: "

            # If node already exists connect to it, else create a new one
            new_node, created = CytoElement.objects.get_or_create(
                scape=self,
                group=CytoElement.NODES,
                label=pre + str(obj) + post,
                classes=type(obj).__name__,
                # defaults={'attribute': value},
            )

            # node_list.append(new_node)
            edge = CytoElement(
                scape=self, group=CytoElement.EDGES,
                data_source=current_node,
                data_target=new_node,
            )
            edge.save()

            # If repeatable, add circular edge
            if hasattr(obj, 'max_repeats'):
                if obj.max_repeats != 0:
                    repeat_edge = CytoElement(
                        scape=self, group=CytoElement.EDGES,
                        data_source=new_node,
                        data_target=new_node,
                    )
                    repeat_edge.save()

            # recursive, continuing adding
            self.add_reliant(obj, new_node)

    @staticmethod
    def generate_map(starting_object, name, container_element_id="cy", layout_name="dagre"):

        layout_options = "'directed': 'true', "\
                        "'spacingFactor': '1.5', "\
                        "'padding': '100', "\
                        "'nodeSep': '25', "\
                        "'rankSep': '25', "\
                        ""

        node_styles = "label: 'data(label)'," \
                      "'shape': 'roundrectangle'," \
                      "'background-opacity': '1'," \
                      "'background-color':'lightgray'," \
                      "'border-color': 'black', " \
                      "'border-width': '1', " \
                      "'padding-top': '10px', " \
                      "'padding-bottom': '10px', " \
                      "'padding-left': '10px', " \
                      "'padding-right': '10px', " \
                      "'text-valign': 'center', "\
                      "'width': 'label', " \
                      "'height': 'label', " \
                      ""



        edge_styles = "'width': '1px', "\
                      "'curve-style':'bezier', " \
                      "'line-color': 'black', " \
                      "'line-style': 'solid', "\
                      "'target-arrow-shape': 'triangle-backcurve', "\
                      "'target-arrow-color':'black', "\
                      "'haystack-radius': 1, "\
                      "'text-rotation': 'autorotate', "\
                      ""

        parent_styles = ""

        scape = CytoScape(
            name=name,
            container_element_id=container_element_id,
            layout_name=layout_name,
            layout_options=layout_options,
            node_styles=node_styles,
            edge_styles=edge_styles,
            parent_styles=parent_styles,
        )
        scape.save()

        # generate starting node
        mother_node = CytoElement(scape=scape,
                                  group=CytoElement.NODES,
                                  label=str(starting_object),
                                  classes=type(starting_object).__name__,
                                  )
        mother_node.save()

        # node_list = [mother_node]

        scape.add_reliant(starting_object, mother_node)

        return scape




