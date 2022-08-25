from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin

from django.views.generic import DetailView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.views.generic.list import ListView

from hackerspace_online.decorators import staff_member_required

from badges.models import Badge
from quest_manager.models import Quest
from siteconfig.models import SiteConfig

from tags.forms import TagForm

# from utilities.forms import TagForm, 
from tenant.views import NonPublicOnlyViewMixin

# from dal import autocomplete
from taggit.models import Tag
from .models import get_quest_submission_by_tag, get_badge_assertion_by_tags

# USE GENERIC utilities.views.ModelAutoComplete instead, might need this in the future if further customization is needed
# class TagAutocomplete(autocomplete.Select2QuerySetView):
#     """ https://django-autocomplete-light.readthedocs.io/en/master/taggit.html#view-example
#     """
#     def get_queryset(self):
#         # Don't forget to filter out results depending on the visitor !
#         if not self.request.user.is_authenticated:
#             return Tag.objects.none()

#         # order_by() added to prevent this warning:
#         # UnorderedObjectListWarning: Pagination may yield inconsistent results with an unordered object_list: <class 'taggit.models.Tag'> QuerySet.
#         qs = Tag.objects.all().order_by('name')

#         if self.q:
#             qs = qs.filter(name__istartswith=self.q)

#         return qs

User = get_user_model()


class TagList(NonPublicOnlyViewMixin, LoginRequiredMixin, ListView):
    model = Tag
    template_name = 'tags/list.html'


class TagDetail(NonPublicOnlyViewMixin, LoginRequiredMixin, DetailView):
    """ abstract view for TagDetailStudent and TagDetailStaff """
    model = Tag
    template_name = 'tags/detail.html'
    view = None

    def get_context_data(self, **kwargs):
        kwargs['view'] = self.view
        kwargs['quests'] = self.get_quest_queryset()
        kwargs['badges'] = self.get_badge_queryset()

        return super().get_context_data(**kwargs)


class TagDetailStudent(TagDetail):
    view = 'student'

    def get_object(self):
        pk = self.request.GET.get('tag_pk')
        return Tag.objects.get(pk=pk)

    def get_user_object(self):
        pk = self.request.GET.get('user_pk')
        return User.objects.get(pk=pk)

    def get(self, *args, **kwargs):
        self.request.GET = kwargs
        self.object = self.get_object()
        self.user = self.get_user_object()

        return super().get(*args, **kwargs)

    def get_quest_queryset(self):
        # returns all quest objects related to tag and user
        quest_submissions = get_quest_submission_by_tag(self.user, [self.object.name]).order_by('quest__id')

        # calculate total xp per quest
        xp = {}
        for submission in quest_submissions:
            quest = submission.quest
            xp_amount = submission.xp_requested or quest.xp 
            xp[quest.id] = xp.get(quest.id, 0) + xp_amount

        xp = xp.values()
        # order has to be the same as badge_assertions
        quest = Quest.objects.filter(id__in=quest_submissions.values('quest__id')).order_by('id')

        return list(zip(quest, xp))

    def get_badge_queryset(self):
        # returns all badge objects related to tag and user
        badge_assertions = get_badge_assertion_by_tags(self.user, [self.object.name]).order_by('badge__id')

        # calculate total xp per badge
        xp = {}
        for assertion in badge_assertions:
            badge = assertion.badge
            xp[badge.id] = xp.get(badge.id, 0) + badge.xp 

        xp = xp.values()
        # order has to be the same as badge_assertions
        badge = Badge.objects.filter(id__in=badge_assertions.values('badge__id')).order_by('id')

        return list(zip(badge, xp))

    def get_context_data(self, **kwargs):
        kwargs['user_obj'] = self.user
        return super().get_context_data(**kwargs) 


@method_decorator(staff_member_required, name='dispatch')
class TagDetailStaff(TagDetail):
    view = 'staff'

    def get_quest_queryset(self):
        return Quest.objects.filter(tags__name=self.object.name)

    def get_badge_queryset(self):
        return Badge.objects.filter(tags__name=self.object.name)


@method_decorator(staff_member_required, name='dispatch')
class TagCreate(NonPublicOnlyViewMixin, CreateView):
    model = Tag
    form_class = TagForm
    template_name = 'tags/form.html'
    success_url = reverse_lazy('tags:list')

    def get_context_data(self, **kwargs):
        kwargs['heading'] = f'Create {SiteConfig.objects.get().custom_name_for_tag}'
        kwargs['submit_btn_value'] = 'Create'

        return super().get_context_data(**kwargs)


@method_decorator(staff_member_required, name='dispatch')
class TagUpdate(NonPublicOnlyViewMixin, UpdateView):
    model = Tag
    form_class = TagForm
    template_name = 'tags/form.html'
    success_url = reverse_lazy('tags:list')

    def get_context_data(self, **kwargs):
        kwargs['heading'] = f'Update {SiteConfig.objects.get().custom_name_for_tag}'
        kwargs['submit_btn_value'] = 'Update'

        return super().get_context_data(**kwargs)


@method_decorator(staff_member_required, name='dispatch')
class TagDelete(NonPublicOnlyViewMixin, DeleteView):
    model = Tag
    template_name = 'tags/delete.html'
    success_url = reverse_lazy('tags:list')

    def get_context_data(self, **kwargs):
        kwargs['quests'] = Quest.objects.filter(tags__id=self.object.id)
        kwargs['badges'] = Badge.objects.filter(tags__id=self.object.id)
        return super().get_context_data(**kwargs)
