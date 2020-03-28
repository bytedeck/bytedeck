from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.decorators import method_decorator
from django.views.generic import ListView
from django.views.generic.edit import UpdateView, DeleteView
from django.urls import reverse_lazy

from .models import CytoScape
from quest_manager.models import QuestSubmission
from djcytoscape.forms import GenerateQuestMapForm
from tenant.views import AllowNonPublicViewMixin, allow_non_public_view

User = get_user_model()


class ScapeUpdate(AllowNonPublicViewMixin, UpdateView):
    model = CytoScape
    fields = '__all__'

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super(ScapeUpdate, self).dispatch(*args, **kwargs)


class ScapeDelete(AllowNonPublicViewMixin, DeleteView):
    model = CytoScape
    success_url = reverse_lazy('djcytoscape:list')

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super(ScapeDelete, self).dispatch(*args, **kwargs)


class ScapeList(AllowNonPublicViewMixin, LoginRequiredMixin, ListView):
    model = CytoScape


@allow_non_public_view
@login_required
def index(request):
    scape_list = CytoScape.objects.all()

    context = {
        'scape_list': scape_list,
    }
    return render(request, 'djcytoscape/index.html', context)


@allow_non_public_view
@login_required
def quest_map(request, scape_id):
    return quest_map_personalized(request, scape_id, None)


@allow_non_public_view
@login_required
def quest_map_personalized(request, scape_id, user_id):
    if user_id is None:
        user = request.user
    else:
        user = get_object_or_404(User, id=user_id)

    # other than staff, only users can see their own personalized map
    if user == request.user or request.user.is_staff:
        # do not personalize for staff accounts
        if not user.is_staff:
            completed_qs = QuestSubmission.objects.all_completed(user=user, active_semester_only=False)
            quest_ids = completed_qs.values_list('quest__id', flat=True)
            # Evalute and remove doubels by converting to a set
            quest_ids = set(quest_ids)
            personalized_user = user
        else:
            quest_ids = None
            personalized_user = None

        scape = get_object_or_404(CytoScape, id=scape_id)
        return render(request, 'djcytoscape/quest_map.html', {'scape': scape,
                                                              'cytoscape_json': scape.json(),
                                                              'completed_quests': quest_ids,
                                                              'fullscreen': True,
                                                              'personalized_user': personalized_user,
                                                              })
    else:
        raise Http404()


@allow_non_public_view
@login_required
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


@allow_non_public_view
@login_required
def primary(request):
    try:
        scape = CytoScape.objects.get(is_the_primary_scape=True)
        return quest_map(request, scape.id)
    except ObjectDoesNotExist:
        return generate_map(request)


@allow_non_public_view
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


@allow_non_public_view
@staff_member_required
def regenerate(request, scape_id):
    scape = get_object_or_404(CytoScape, id=scape_id)
    scape.regenerate()
    return redirect('djcytoscape:quest_map', scape_id=scape.id)


@allow_non_public_view
@staff_member_required
def regenerate_all(request):
    for scape in CytoScape.objects.all():
        scape.regenerate()
    messages.success(request, "All quest maps have been regenerated.")
    return redirect('djcytoscape:primary')
