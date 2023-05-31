import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import RedirectView
from django.views.generic.edit import CreateView, DeleteView, UpdateView
from django.views.generic.list import ListView

from hackerspace_online.decorators import staff_member_required

from notifications.signals import notify
from prerequisites.views import ObjectPrereqsFormView
from siteconfig.models import SiteConfig
from tenant.views import NonPublicOnlyViewMixin, non_public_only_view

from .forms import BadgeAssertionForm, BadgeForm, BulkBadgeAssertionForm
from .models import Badge, BadgeAssertion, BadgeType


class AchievementRedirectView(NonPublicOnlyViewMixin, LoginRequiredMixin, RedirectView):
    def dispatch(self, request):
        return redirect(request.path_info.replace("achievements", "badges", 1))


@non_public_only_view
@login_required
def badge_list(request):
    badge_types = BadgeType.objects.all()
    inactive_badges = Badge.objects.all().filter(active=False)

    # http://stackoverflow.com/questions/32421214/django-queryset-all-model1-objects-where-a-model2-exists-with-a-model1-and-the
    earned_badges = Badge.objects.filter(badgeassertion__user=request.user)

    context = {
        "heading": f"{SiteConfig.get().custom_name_for_badge}s",
        # "badge_type_dicts": badge_type_dicts,
        "badge_types": badge_types,
        "earned_badges": earned_badges,
        "inactive_badges": inactive_badges
    }
    return render(request, "badges/list.html", context)


class BadgePrereqsUpdate(ObjectPrereqsFormView):
    model = Badge


class BadgeDelete(NonPublicOnlyViewMixin, DeleteView):
    model = Badge
    success_url = reverse_lazy('badges:list')

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


class BadgeUpdate(NonPublicOnlyViewMixin, UpdateView):
    model = Badge
    form_class = BadgeForm

    # template_name = ''

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super().get_context_data(**kwargs)
        context['heading'] = f"Update {SiteConfig.get().custom_name_for_badge}"
        context['submit_btn_value'] = "Update"
        return context

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


@non_public_only_view
@staff_member_required
def badge_create(request):
    form = BadgeForm(request.POST or None, request.FILES or None)

    if form.is_valid():
        form.save()
        return redirect('badges:list')
    context = {
        "heading": f"Create New {SiteConfig.get().custom_name_for_badge}",
        "form": form,
        "submit_btn_value": "Create",
    }
    return render(request, "badges/badge_form.html", context)


@non_public_only_view
@staff_member_required
def badge_copy(request, badge_id):
    original_badge = get_object_or_404(Badge, pk=badge_id)  # prevent: Badge objects need to have a primary key value before you can access their tags
    new_badge = get_object_or_404(Badge, pk=badge_id)
    new_badge.pk = None  # autogen a new primary key (quest_id by default)
    new_badge.import_id = uuid.uuid4()
    new_badge.name = "Copy of " + new_badge.name

    form = BadgeForm(request.POST or None, instance=new_badge, initial={'tags': original_badge.tags.all()})
    if form.is_valid():
        form.save()
        return redirect('badges:list')
    context = {
        "heading": f"Copy another {SiteConfig.get().custom_name_for_badge}",
        "form": form,
        "submit_btn_value": "Create",
    }
    return render(request, "badges/badge_form.html", context)


@non_public_only_view
@login_required
def detail(request, badge_id):
    # if there is an active submission, get it and display accordingly

    badge = get_object_or_404(Badge, pk=badge_id)
    # active_submission = QuestSubmission.objects.quest_is_available(request.user, q)

    context = {
        "heading": badge.name,
        "badge": badge,
        "assertions_of_this_badge": BadgeAssertion.objects.all_for_user_badge(request.user, badge, False)
    }
    return render(request, 'badges/detail.html', context)


# ########## Badge Type Views ##############################

@method_decorator(staff_member_required, name='dispatch')
class BadgeTypeList(NonPublicOnlyViewMixin, LoginRequiredMixin, ListView):
    model = BadgeType


@method_decorator(staff_member_required, name='dispatch')
class BadgeTypeCreate(NonPublicOnlyViewMixin, CreateView):
    fields = ('name', 'sort_order', 'fa_icon')
    model = BadgeType
    success_url = reverse_lazy('badges:badge_types')

    def get_context_data(self, **kwargs):

        kwargs['heading'] = f'Create New {SiteConfig.get().custom_name_for_badge} Type'
        kwargs['submit_btn_value'] = 'Create'

        return super().get_context_data(**kwargs)


@method_decorator(staff_member_required, name='dispatch')
class BadgeTypeUpdate(NonPublicOnlyViewMixin, UpdateView):
    fields = ('name', 'sort_order', 'fa_icon')
    model = BadgeType
    success_url = reverse_lazy('badges:badge_types')

    def get_context_data(self, **kwargs):

        kwargs['heading'] = f'Update {SiteConfig.get().custom_name_for_badge} Type'
        kwargs['submit_btn_value'] = 'Update'

        return super().get_context_data(**kwargs)


@method_decorator(staff_member_required, name='dispatch')
class BadgeTypeDelete(NonPublicOnlyViewMixin, DeleteView):
    model = BadgeType
    success_url = reverse_lazy('badges:badge_types')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        badge_type_badge_qs = Badge.objects.filter(badge_type=self.get_object())
        context["has_badges"] = badge_type_badge_qs.exists()
        return context

    def post(self, request, *args, **kwargs):
        # make sure no data can be passed in POST if populated
        # makes sure to prevent 404/delete (because deletion still goes off)
        has_badges = Badge.objects.filter(badge_type=self.get_object()).exists()
        if has_badges:
            return self.get(request, *args, **kwargs)

        return super().post(request, *args, **kwargs)


# ########## Badge Assertion Views #########################

@non_public_only_view
@staff_member_required
def bulk_assertion_create(request, badge_id=None):
    initial = {}
    if badge_id:
        badge = get_object_or_404(Badge, pk=badge_id)
        initial['badge'] = badge

    form = BulkBadgeAssertionForm(request.POST or None, initial=initial)

    if form.is_valid():
        badge = form.cleaned_data['badge']
        # TODO: Why does this form use Profile model instead of User model?
        profiles = form.cleaned_data['students']

        result_message = f"{SiteConfig.get().custom_name_for_badge} {str(badge)} granted to "
        for profile in profiles:
            BadgeAssertion.objects.create_assertion(profile.user, badge)
            result_message += profile.preferred_full_name() + "; "

        messages.success(request, result_message)
        return redirect('badges:list')

    context = {
        "heading": f"Grant {SiteConfig.get().custom_name_for_badge} in Bulk",
        "form": form,
        "submit_btn_value": "Grant",
    }

    return render(request, "badges/assertion_form.html", context)


@non_public_only_view
@staff_member_required
def assertion_create(request, user_id, badge_id):
    initial = {}
    if int(user_id) > 0:
        user = get_object_or_404(User, pk=user_id)
        initial['user'] = user
    if int(badge_id) > 0:
        badge = get_object_or_404(Badge, pk=badge_id)
        initial['badge'] = badge

    form = BadgeAssertionForm(request.POST or None, initial=initial)

    if form.is_valid():
        new_ass = form.save(commit=False)
        BadgeAssertion.objects.create_assertion(new_ass.user, new_ass.badge, transfer=new_ass.do_not_grant_xp)
        messages.success(request, f"{SiteConfig.get().custom_name_for_badge} {str(new_ass)} granted to {str(new_ass.user)}")
        return redirect('badges:list')

    context = {
        "heading": "Grant an Achievment",
        "form": form,
        "submit_btn_value": "Grant",
    }

    return render(request, "badges/assertion_form.html", context)


@non_public_only_view
@staff_member_required
def assertion_delete(request, assertion_id):
    assertion = get_object_or_404(BadgeAssertion, pk=assertion_id)

    if request.method == 'POST':
        user = assertion.user
        notify.send(
            request.user,
            # action=...,
            target=assertion.badge,
            recipient=user,
            affected_users=[user, ],
            icon="<span class='fa-stack'>" + \
                 "<i class='fa fa-certificate fa-stack-1x text-warning'></i>" + \
                 "<i class='fa fa-ban fa-stack-2x text-danger'></i>" + \
                 "</span>",
            verb='revoked')

        messages.success(request,
                         ("Badge " + str(assertion) + " revoked from " + str(assertion.user)
                          ))
        assertion.delete()
        return redirect('profiles:profile_detail', pk=user.profile.id)

    template_name = 'badges/assertion_confirm_delete.html'
    return render(request, template_name, {'object': assertion})
