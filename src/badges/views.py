import uuid

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic.edit import DeleteView, UpdateView

from notifications.signals import notify
from tenant.views import NonPublicOnlyViewMixin, non_public_only_view

from .forms import BadgeAssertionForm, BadgeForm, BulkBadgeAssertionForm
from .models import Badge, BadgeAssertion, BadgeType


@non_public_only_view
@login_required
def badge_list(request):
    badge_types = BadgeType.objects.all()
    inactive_badges = Badge.objects.all().filter(active=False)

    # http://stackoverflow.com/questions/32421214/django-queryset-all-model1-objects-where-a-model2-exists-with-a-model1-and-the
    earned_badges = Badge.objects.filter(badgeassertion__user=request.user)

    context = {
        "heading": "Badges",
        # "badge_type_dicts": badge_type_dicts,
        "badge_types": badge_types,
        "earned_badges": earned_badges,
        "inactive_badges": inactive_badges
    }
    return render(request, "badges/list.html", context)


class BadgeDelete(NonPublicOnlyViewMixin, DeleteView):
    model = Badge
    success_url = reverse_lazy('badges:list')

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super(BadgeDelete, self).dispatch(*args, **kwargs)


class BadgeUpdate(NonPublicOnlyViewMixin, UpdateView):
    model = Badge
    form_class = BadgeForm

    # template_name = ''

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(BadgeUpdate, self).get_context_data(**kwargs)
        context['heading'] = "Update Achievment"
        context['submit_btn_value'] = "Update"
        return context

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super(BadgeUpdate, self).dispatch(*args, **kwargs)


@non_public_only_view
@login_required
def badge_create(request):

    # Using `@staff_member_required(login_url='/accounts/login/')` causes a RedirectCycleErrror.
    # For example, a student that is already logged in tries to access this page,
    # They will get redirect to `/accounts/login/?next=/achievements/create/`.
    # And since they are already logged in, they will be redirected to `/achievements/create/`
    # Causing again to redirect since they are not a staff.

    # We could use `@staff_member_required(login_url='/')` but this breaks the tests
    # which requires views to be redirected to /accounts/login
    if request.user.is_active and not request.user.is_staff:
        return redirect('quests:quests')

    form = BadgeForm(request.POST or None, request.FILES or None)

    if form.is_valid():
        form.save()
        return redirect('badges:list')
    context = {
        "heading": "Create New Achievment",
        "form": form,
        "submit_btn_value": "Create",
    }
    return render(request, "badges/badge_form.html", context)


@non_public_only_view
@staff_member_required
def badge_copy(request, badge_id):
    new_badge = get_object_or_404(Badge, pk=badge_id)
    new_badge.pk = None  # autogen a new primary key (quest_id by default)
    new_badge.import_id = uuid.uuid4()
    new_badge.name = "Copy of " + new_badge.name

    form = BadgeForm(request.POST or None, instance=new_badge)
    if form.is_valid():
        form.save()
        return redirect('badges:list')
    context = {
        "heading": "Copy a Badge",
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

        result_message = "Badge " + str(badge) + " granted to "
        for profile in profiles:
            BadgeAssertion.objects.create_assertion(profile.user, badge)
            result_message += profile.preferred_full_name() + "; "

        messages.success(request, result_message)
        return redirect('badges:list')

    context = {
        "heading": "Grant Badges in Bulk",
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
        BadgeAssertion.objects.create_assertion(new_ass.user, new_ass.badge)
        messages.success(request, ("Badge " + str(new_ass) + " granted to " + str(new_ass.user)))
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
