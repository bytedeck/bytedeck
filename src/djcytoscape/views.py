from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.decorators import method_decorator
from django.views.generic.edit import UpdateView, DeleteView
from django.core.urlresolvers import reverse_lazy
from djcytoscape.forms import GenerateQuestMapForm
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


def quest_map(request, quest_id, originating_scape_id=None):
    try:
        scape = CytoScape.objects.get(initial_quest_id=quest_id)
    except ObjectDoesNotExist:
        if request.user.is_staff:
            # the map doesn't exist, so ask to generate it.
            return generate_map(request, quest_id=quest_id, scape_id=originating_scape_id)
        else:
            raise Http404

    cytoscape_json = scape.json()
    return render(request, 'djcytoscape/quest_map.html', {'scape': scape,
                                                          'cytoscape_json': cytoscape_json,
                                                          'fullscreen': True,
                                                          })


def primary(request):
    try:
        scape = CytoScape.objects.get(is_the_primary_scape=True)
        return quest_map(request, scape.initial_quest.id)
    except ObjectDoesNotExist:
        return generate_map(request)


@staff_member_required
def generate_map(request, quest_id=None, scape_id=None):
    interlink = False
    if request.method == 'POST':
        form = GenerateQuestMapForm(request.POST)
        # check whether it's valid:
        if form.is_valid():
            quest = form.cleaned_data['quest']
            scape = form.cleaned_data['scape']
            name = form.cleaned_data['name']
            if not name:
                name = str(quest)
            cyto_test = CytoScape.generate_map(initial_quest=quest, name=name, parent_scape=scape)
            return redirect('djcytoscape:quest_map', quest_id=cyto_test.initial_quest_id)

    else:

        initial = {}
        if quest_id:
            quest = get_object_or_404(Quest, pk=quest_id)
            initial['quest'] = quest
        if scape_id:
            scape = get_object_or_404(CytoScape, pk=scape_id)
            initial['scape'] = scape
            interlink = True

        form = GenerateQuestMapForm(initial=initial)

    context = {
        'form': form,
        'interlink': interlink,
    }

    return render(request, 'djcytoscape/generate_new_form.html', context)


@staff_member_required
def regenerate(request, scape_id):
    scape = get_object_or_404(CytoScape, id=scape_id)
    scape.regenerate()
    return redirect('djcytoscape:quest_map', quest_id=scape.initial_quest_id)



