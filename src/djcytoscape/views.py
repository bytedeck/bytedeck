from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic.edit import UpdateView, DeleteView
from django.core.urlresolvers import reverse_lazy
from quest_manager.models import Quest

from .models import CytoScape


class ScapeUpdate(UpdateView):
    model = CytoScape
    fields = '__all__'


class ScapeDelete(DeleteView):
    model = CytoScape
    success_url = reverse_lazy('djcytoscape:index')


def index(request):
    scape_list = CytoScape.objects.all()

    context = {
        'scape_list': scape_list,
    }
    return render(request, 'djcytoscape/index.html', context)


def detail(request, scape_id):
    scape = get_object_or_404(CytoScape, pk=scape_id)
    cytoscape_json = scape.json()
    return render(request, 'djcytoscape/detail.html', {'scape': scape, 'cytoscape_json': cytoscape_json})


def graph(request, scape_id):
    scape = get_object_or_404(CytoScape, pk=scape_id)
    cytoscape_json = scape.json()
    return render(request, 'djcytoscape/graph.html', {'cytoscape_json': cytoscape_json})


def generate(request, num_nodes):
    cyto_test = CytoScape.objects.generate_random_scape("Test", int(num_nodes))
    return redirect('djcytoscape:detail', scape_id=cyto_test.id)


def generate_tree(request, num_nodes):
    cyto_test = CytoScape.objects.generate_random_tree_scape("Test", int(num_nodes))
    return redirect('djcytoscape:detail', scape_id=cyto_test.id)


def generate_map(request):
    q = get_object_or_404(Quest, id=1)
    cyto_test = CytoScape.generate_map(starting_object=q, name="Test MAP")
    return redirect('djcytoscape:detail', scape_id=cyto_test.id)


