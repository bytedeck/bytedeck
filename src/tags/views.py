from django.urls import reverse_lazy
from django.http import JsonResponse
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

from tenant.views import NonPublicOnlyViewMixin

from django_select2.views import AutoResponseView
from taggit.models import Tag
from .models import get_quest_submission_by_tag, get_badge_assertion_by_tags, total_xp_by_tags

User = get_user_model()


class TaggitAutoResponseView(AutoResponseView):
    """
    Override `django_select2.views.AutoResponseView` class
    to work with taggit's TagField.

    The view only supports HTTP's GET method.
    """

    def get(self, request, *args, **kwargs):
        """
        Override `get` method to return a list of tags (slugs)
        instead of primary keys.

        This is needed because `django_select2.views.AutoResponseView`
        returns primary keys of selected options, and the taggit's TagField
        expects tag names.

        Return a :class:`.django.http.JsonResponse`.

        Example::
            {
                'results': [
                    {
                        'text': "foo",
                        'id': "foo"
                    }
                ],
                'more': true
            }
        """
        self.widget = self.get_widget_or_404()
        self.term = kwargs.get('term', request.GET.get('term', ''))
        self.object_list = self.get_queryset()
        context = self.get_context_data()
        return JsonResponse(
            {
                'results': [
                    # render slug (tag) instead of primary key
                    {'text': self.widget.label_from_instance(obj), 'id': obj.slug}
                    for obj in context['object_list']
                ],
                'more': context['page_obj'].has_next(),
            },
        )

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return self.queryset.none()

        return super().get_queryset().order_by("name")


class TagList(NonPublicOnlyViewMixin, LoginRequiredMixin, ListView):
    model = Tag
    template_name = 'tags/list.html'


class TagDetail(NonPublicOnlyViewMixin, LoginRequiredMixin, DetailView):
    """ abstract view for TagDetailStudent and TagDetailStaff """
    model = Tag
    template_name = 'tags/detail.html'


class TagDetailStudent(TagDetail):

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

    def get_quest_submissions(self):
        submissions = get_quest_submission_by_tag(self.user, [self.object.name]).order_by('quest', 'ordinal')

        # inject 'is_multiple' var into QuestSubmission object (basically the same as annotate)
        # conditional if there are multiple submissions pointing to quest
        for submission in submissions:
            ordinal_check = submission.ordinal > 1
            multiple = submissions.filter(quest__id=submission.quest.id).count() > 1

            submission.is_multiple = ordinal_check or multiple

        return submissions

    def get_badge_assertions(self):
        assertions = get_badge_assertion_by_tags(self.user, [self.object.name]).order_by('badge', 'ordinal')

        # inject 'is_multiple' var into BadgeAssertion object (basically the same as annotate)
        # conditional if there are multiple assertions pointing to badge
        for assertion in assertions:
            ordinal_check = assertion.ordinal > 1
            multiple = assertions.filter(badge__id=assertion.badge.id).count() > 1

            assertion.is_multiple = ordinal_check or multiple

        return assertions

    def get_context_data(self, **kwargs):
        kwargs['user_obj'] = self.user
        kwargs['user_xp_by_this_tag'] = total_xp_by_tags(self.user, [self.object])

        submissions = self.get_quest_submissions()
        kwargs['quest_submissions'] = submissions
        kwargs['quest_submission_length'] = len(submissions)

        assertions = self.get_badge_assertions()
        kwargs['badge_assertions'] = assertions
        kwargs['badge_assertion_length'] = len(assertions)

        return super().get_context_data(**kwargs)


@method_decorator(staff_member_required, name='dispatch')
class TagDetailStaff(TagDetail):

    def get_context_data(self, **kwargs):
        kwargs['view'] = 'staff'

        quests = Quest.objects.filter(tags__name=self.object.name)
        kwargs['quests'] = quests
        kwargs['quest_length'] = len(quests)

        badges = Badge.objects.filter(tags__name=self.object.name)
        kwargs['badges'] = badges
        kwargs['badge_length'] = len(badges)

        return super().get_context_data(**kwargs)


@method_decorator(staff_member_required, name='dispatch')
class TagCreate(NonPublicOnlyViewMixin, CreateView):
    model = Tag
    form_class = TagForm
    template_name = 'tags/form.html'
    success_url = reverse_lazy('tags:list')

    def get_context_data(self, **kwargs):
        kwargs['heading'] = f'Create {SiteConfig.get().custom_name_for_tag}'
        kwargs['submit_btn_value'] = 'Create'

        return super().get_context_data(**kwargs)


@method_decorator(staff_member_required, name='dispatch')
class TagUpdate(NonPublicOnlyViewMixin, UpdateView):
    model = Tag
    form_class = TagForm
    template_name = 'tags/form.html'
    success_url = reverse_lazy('tags:list')

    def get_context_data(self, **kwargs):
        kwargs['heading'] = f'Update {SiteConfig.get().custom_name_for_tag}'
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
