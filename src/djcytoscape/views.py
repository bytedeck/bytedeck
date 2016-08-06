from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.decorators import method_decorator
from django.views.generic.edit import UpdateView, DeleteView
from django.core.urlresolvers import reverse_lazy
from quest_manager.models import Quest

from .models import CytoScape


class ScapeUpdate(UpdateView):
    model = CytoScape
    fields = '__all__'

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super(ScapeUpdate, self).dispatch(*args, **kwargs)


class ScapeDelete(DeleteView):
    model = CytoScape
    success_url = reverse_lazy('djcytoscape:index')

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super(ScapeDelete, self).dispatch(*args, **kwargs)


def index(request):
    scape_list = CytoScape.objects.all()

    context = {
        'scape_list': scape_list,
    }
    return render(request, 'djcytoscape/index.html', context)


def quest_map(request, quest_id):
    scape = get_object_or_404(CytoScape, initial_quest_id=quest_id)
    cytoscape_json = scape.json()
    return render(request, 'djcytoscape/quest_map.html', {'scape': scape,
                                                          'cytoscape_json': cytoscape_json,
                                                          'fullscreen': True,
                                                          })

#
# def detail(request, scape_id):
#     scape = get_object_or_404(CytoScape, pk=scape_id)
#     cytoscape_json = scape.json()
#     return render(request, 'djcytoscape/detail.html', {'scape': scape, 'cytoscape_json': cytoscape_json})

#
# def generate(request, num_nodes):
#     cyto_test = CytoScape.objects.generate_random_scape("Test", int(num_nodes))
#     return redirect('djcytoscape:detail', scape_id=cyto_test.id)


#
# def generate_tree(request, num_nodes):
#     cyto_test = CytoScape.objects.generate_random_tree_scape("Test", int(num_nodes))
#     return redirect('djcytoscape:detail', scape_id=cyto_test.id)


def generate_map(request, quest_id=1):
    q = get_object_or_404(Quest, id=quest_id)
    cyto_test = CytoScape.generate_map(initial_quest=q, name=str(q))
    return redirect('djcytoscape:quest_map', quest_id=cyto_test.initial_quest_id)


def regenerate(request, scape_id):
    scape = get_object_or_404(CytoScape, id=scape_id)
    scape.regenerate()
    return redirect('djcytoscape:quest_map', quest_id=scape.initial_quest_id)


