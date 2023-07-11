from django.http import HttpResponseRedirect
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404, reverse
from django.utils.decorators import method_decorator
from django.views.generic import ListView
from django.views.generic.edit import UpdateView, DeleteView, FormView
from django.urls import reverse_lazy

from hackerspace_online.decorators import staff_member_required

from quest_manager.models import QuestSubmission, Quest
from tenant.views import NonPublicOnlyViewMixin, non_public_only_view

from .models import CytoScape
from .forms import GenerateQuestMapForm, QuestMapForm
from .tasks import regenerate_all_maps

User = get_user_model()


@method_decorator(staff_member_required, name='dispatch')
class ScapeUpdate(NonPublicOnlyViewMixin, UpdateView):
    model = CytoScape
    form_class = QuestMapForm

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


@method_decorator(staff_member_required, name='dispatch')
class ScapeDelete(NonPublicOnlyViewMixin, DeleteView):
    model = CytoScape
    success_url = reverse_lazy('djcytoscape:list')

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


class ScapeList(NonPublicOnlyViewMixin, LoginRequiredMixin, ListView):
    model = CytoScape


@non_public_only_view
@login_required
def index(request):
    scape_list = CytoScape.objects.all()

    context = {
        'scape_list': scape_list,
    }
    return render(request, 'djcytoscape/index.html', context)


@non_public_only_view
@login_required
def quest_map(request, scape_id):
    return quest_map_personalized(request, scape_id, None)


@non_public_only_view
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

        if scape.class_styles_json is None or scape.class_styles_json is None:
            scape.update_cache()

        context = {
            'scape': scape,
            'elements': scape.elements_json,
            'class_styles': scape.class_styles_json,
            'completed_quests': quest_ids,
            'fullscreen': True,
            'personalized_user': personalized_user,
        }

        return render(request, 'djcytoscape/quest_map.html', context)
    else:
        raise Http404()


@non_public_only_view
@login_required
def quest_map_interlink(request, ct_id, obj_id, originating_scape_id):
    try:
        scape = CytoScape.objects.get(initial_content_type=ct_id, initial_object_id=obj_id)
        return quest_map(request, scape.id)
    except ObjectDoesNotExist:
        if request.user.is_staff:
            # the map doesn't exist, so ask to generate it.
            return ScapeGenerateMap.as_view()(request, ct_id=ct_id, obj_id=obj_id, scape_id=originating_scape_id)
        else:
            raise Http404


@non_public_only_view
@login_required
def primary(request):
    # Check if a map has been created, if not, generate it from the default Welcome quest
    # the Welcome quests should have been created via data migration when the tenant was created
    if not CytoScape.objects.exists() and Quest.objects.filter(import_id='bee53060-c332-4f75-85e1-6a8f9503ebe1').exists():
        welcome_quest = Quest.objects.get(import_id='bee53060-c332-4f75-85e1-6a8f9503ebe1')
        CytoScape.generate_map(welcome_quest, 'Main')

    try:
        scape = CytoScape.objects.get(is_the_primary_scape=True)
        return quest_map(request, scape.id)
    except ObjectDoesNotExist:
        return ScapeGenerateMap.as_view()(request)


class ScapeGenerateMap(NonPublicOnlyViewMixin, FormView):
    form_class = GenerateQuestMapForm
    template_name = 'djcytoscape/generate_new_form.html'

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        """
        :param request:
        :param ct_id: Content Type for Generic Foreign Key (initial object)
        :param obj_id: Object ID for Generic Foreign Key (initial object)
        :param scape_id: originating scape/quest
        :return:
        """
        self.ct_id = kwargs.get('ct_id')
        self.obj_id = kwargs.get('obj_id')
        self.scape_id = kwargs.get('scape_id')
        self.autobreak = kwargs.get('autobreak', True)
        self.interlink = False

        return super().dispatch(*args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs().copy()
        kwargs['autobreak'] = self.autobreak

        if self.ct_id and self.obj_id:
            ct = get_object_or_404(ContentType, pk=self.ct_id)
            obj = get_object_or_404(ct.model_class(), pk=self.obj_id)
            kwargs['initial']['initial_content_object'] = obj

        if self.scape_id:
            kwargs['initial']['parent_scape'] = get_object_or_404(CytoScape, pk=self.scape_id)
            self.interlink = True

        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs).copy()
        ctx['interlink'] = self.interlink
        return ctx

    def form_valid(self, form):  # virtually the same as super().form_valid except we're caching form.save() obj for get_success_url()
        self.object = form.save()
        messages.success(
            self.request,
            f"New map {self.object.name} was successfully generated."
        )
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('djcytoscape:quest_map', args=[self.object.id])


@non_public_only_view
@staff_member_required
def regenerate(request, scape_id):
    scape = get_object_or_404(CytoScape, id=scape_id)
    try:
        scape.regenerate()
    except scape.InitialObjectDoesNotExist:
        messages.warning(request, f"The initial object for the {scape.name} Map no longer exists. The map has now been removed too.")
        return redirect('djcytoscape:primary')

    return redirect('djcytoscape:quest_map', scape_id=scape.id)


@non_public_only_view
@staff_member_required
def regenerate_all(request):
    scapes = CytoScape.objects.all()
    if scapes.count() > 5:
        messages.warning(request, "You have a lot of maps, so the map regeneration is being processed in the background. It may take a few minutes.")  # noqa
        regenerate_all_maps.apply_async(args=[request.user.id], queue='default')
    else:
        for scape in CytoScape.objects.all():
            try:
                scape.regenerate()
            except scape.InitialObjectDoesNotExist:
                messages.warning(request, f"The initial object for the '{scape.name} Map' no longer exists. The map has now been removed too.")

        messages.success(request, "All valid quest maps have been regenerated.")

    return redirect('djcytoscape:primary')
