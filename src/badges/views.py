import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import RedirectView
from django.views.generic.edit import CreateView, DeleteView, UpdateView
from django.views.generic.list import ListView
from django.template.loader import render_to_string
from django.db.models import Count

from hackerspace_online.decorators import staff_member_required, xml_http_request_required

from notifications.signals import notify
from prerequisites.views import ObjectPrereqsFormView
from siteconfig.models import SiteConfig
from notifications.models import Notification
from djcytoscape.models import CytoScape
from tenant.views import NonPublicOnlyViewMixin, non_public_only_view
from djcytoscape.views import UpdateMapMessageMixin


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


class BadgeDelete(NonPublicOnlyViewMixin, UpdateMapMessageMixin, DeleteView):
    model = Badge
    success_url = reverse_lazy('badges:list')

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


class BadgeUpdate(NonPublicOnlyViewMixin, UpdateMapMessageMixin, UpdateView):
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

    badge = get_object_or_404(Badge, pk=badge_id)

    context = {
        "heading": badge.name,
        "badge": badge,
        "current": True,
        "assertions_of_this_badge": BadgeAssertion.objects.all_for_user_badge(request.user, badge, False),
        "user_assertion_count": BadgeAssertion.objects.user_badge_assertion_count(badge, True),
        "maps": CytoScape.objects.get_related_maps(badge),
    }
    return render(request, 'badges/detail.html', context)


@non_public_only_view
@login_required
def detail_all(request, badge_id):

    badge = get_object_or_404(Badge, pk=badge_id)

    context = {
        "heading": badge.name,
        "badge": badge,
        "current": False,
        "assertions_of_this_badge": BadgeAssertion.objects.all_for_user_badge(request.user, badge, False),
        "user_assertion_count": BadgeAssertion.objects.user_badge_assertion_count(badge, False),
        "maps": CytoScape.objects.get_related_maps(badge),
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
            icon="<span class='fa-stack'>" +
                 "<i class='fa fa-certificate fa-stack-1x text-warning'></i>" +
                 "<i class='fa fa-ban fa-stack-2x text-danger'></i>" +
                 "</span>",
            verb='revoked')

        messages.success(request,
                         ("Badge " + str(assertion) + " revoked from " + str(assertion.user)
                          ))
        assertion.delete()
        user.profile.xp_invalidate_cache()
        return redirect('profiles:profile_detail', pk=user.profile.id)

    template_name = 'badges/assertion_confirm_delete.html'
    return render(request, template_name, {'object': assertion})


# ########## Badge Ajax Views #########################

@method_decorator(xml_http_request_required, name='dispatch')
class Ajax_BadgePopup(NonPublicOnlyViewMixin, LoginRequiredMixin, View):

    def get_unread_badge_notifications(self):
        """ returns a qs of unread notifications for user with badge as target """
        notifications = Notification.objects.all_for_user(self.user).get_unread().filter(
            target_content_type=ContentType.objects.get_for_model(Badge),

            # this might have to change if the way badges are granted changes
            verb__contains="granted",
        )
        return notifications


class Ajax_OnShowBadgePopup(Ajax_BadgePopup):
    """ This is responsible for giving the html for 'ajaxNewBadgePopup' in 'javascript.js' """

    def get(self, *args, **kwargs):
        self.user = self.request.user
        json_data = self.get_json_data()
        return JsonResponse(data=json_data)

    def get_json_data(self):
        """ returns json data for ajax request """
        badges_by_type = self.get_new_badges()
        show = self._get_badges_sum(badges_by_type) != 0
        html_text = self.get_html_text(badges_by_type) if show else None

        return {
            'show': show,
            'html': html_text,
        }

    def get_html_text(self, badges_by_type):
        """ returns context filled template """
        template_name = 'badges/snippets/badge_notification_popup.html'
        context = {
            'badge_name': SiteConfig.get().custom_name_for_badge,
            'badge_total': self._get_badges_sum(badges_by_type),
            'new_badges_by_type': badges_by_type,
        }
        return render_to_string(template_name, context)

    def _get_badges_sum(self, badges_by_type):
        """ helper func to return the total amount of badges of badges_by_type """
        return sum(
            sum(badge.duplicates for badge in badges)
            for badges in badges_by_type.values()
        )

    def get_new_badges(self):
        """ returns qs of badges related to the notifications of self.get_unread_badge_notifications """
        notifications = self.get_unread_badge_notifications()

        # end queries early if no unread notifications
        if notifications.count() == 0:
            return {}

        # get the ids of each badge and count duplicates
        # follows this format { id : # of duplicates }
        badges_info = notifications.values('target_object_id').annotate(count=Count('target_object_id')).order_by()
        badges_info = {item['target_object_id']: item['count'] for item in badges_info}

        # get the the Badges using unread notifications
        badges = Badge.objects.filter(id__in=badges_info.keys())

        # group badges by their type
        badge_type_ids = badges.values_list('badge_type__id', flat=True)
        badge_types = BadgeType.objects.filter(id__in=badge_type_ids)
        badge_by_type = [badges.filter(badge_type=ba_type) for ba_type in badge_types]
        badges_by_type = dict(zip(badge_types, badge_by_type))

        # inject "duplicates" variable for each badge
        # has to be last because filter resets variable injections
        for badges in badges_by_type.values():
            for badge in badges:
                badge.duplicates = badges_info[badge.id]

        return badges_by_type


class Ajax_OnCloseBadgePopup(Ajax_BadgePopup):
    """ When user dismisses badge popup.
    Mark all badge notifications related to the popup as read """

    def get(self, *args, **kwargs):
        self.user = self.request.user
        # mark notifications as read
        self.get_unread_badge_notifications().mark_all_read(self.user)
        return JsonResponse(data={})
