from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.decorators import method_decorator
from django.views.generic import ListView
from django.views.generic.edit import UpdateView, DeleteView
from django.urls import reverse_lazy
from djcytoscape.forms import GenerateQuestMapForm

from .models import CytoScape


class ScapeUpdate(UpdateView):
    model = CytoScape
    fields = '__all__'

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super(ScapeUpdate, self).dispatch(*args, **kwargs)


class ScapeDelete(DeleteView):
    model = CytoScape
    success_url = reverse_lazy('djcytoscape:list')

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super(ScapeDelete, self).dispatch(*args, **kwargs)


class ScapeList(ListView):
    model = CytoScape


def index(request):
    scape_list = CytoScape.objects.all()

    context = {
        'scape_list': scape_list,
    }
    return render(request, 'djcytoscape/index.html', context)


def quest_map(request, scape_id):
    scape = get_object_or_404(CytoScape, id=scape_id)
    return render(request, 'djcytoscape/quest_map.html', {'scape': scape,
                                                          'cytoscape_json': scape.json(),
                                                          'fullscreen': True,
                                                          })


def quest_map_interlink(request, ct_id, obj_id, originating_scape_id):
    try:
        scape = CytoScape.objects.get(initial_content_type=ct_id, initial_object_id=obj_id)
        return quest_map(request, scape.id)
    except ObjectDoesNotExist:
        if request.user.is_staff:
            # the map doesn't exist, so ask to generate it.
            return generate_map(request, ct_id=ct_id, obj_id=obj_id, scape_id=originating_scape_id)
        else:
            raise Http404


def primary(request):
    try:
        scape = CytoScape.objects.get(is_the_primary_scape=True)
        return quest_map(request, scape.id)
    except ObjectDoesNotExist:
        return generate_map(request)


@staff_member_required
def generate_map(request, ct_id=None, obj_id=None, scape_id=None, autobreak=True):
    """
    :param request:
    :param ct_id: Content Type for Generic Foreign Key (initial object)
    :param obj_id: Object ID for Generic Foreign Key (initial object)
    :param scape_id: originating scape/quest
    :return:
    """
    interlink = False
    if request.method == 'POST':
        form = GenerateQuestMapForm(request.POST)
        # check whether it's valid:
        if form.is_valid():
            ct = form.cleaned_data['initial_content_type']
            obj_id = form.cleaned_data['initial_object_id']
            scape = form.cleaned_data['scape']
            name = form.cleaned_data['name']
            obj = ct.get_object_for_this_type(id=obj_id)
            if not name:
                name = str(obj)
            new_scape = CytoScape.generate_map(initial_object=obj, name=name, parent_scape=scape, autobreak=autobreak)
            return redirect('djcytoscape:quest_map', scape_id=new_scape.id)

    else:

        initial = {}
        if ct_id and obj_id:
            ct = get_object_or_404(ContentType, pk=ct_id)
            initial['initial_content_type'] = ct
            initial['initial_object_id'] = obj_id
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
    return redirect('djcytoscape:quest_map', scape_id=scape.id)


@staff_member_required
def regenerate_all(request):
    for scape in CytoScape.objects.all():
        scape.regenerate()
    messages.success(request, "All quest maps have been regenerated.")
    return redirect('djcytoscape:primary')
