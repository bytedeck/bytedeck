from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse_lazy
from django.shortcuts import render, get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from notifications.signals import notify

from .models import Badge, BadgeType, BadgeAssertion
from .forms import BadgeForm, BadgeAssertionForm

@login_required
def list(request):

    # badge_type_dicts = Badge.objects.get_type_dicts()
    badge_types = BadgeType.objects.all()

    # earned_badges = Badge.objects.user_earned_badges(request.user)
    #http://stackoverflow.com/questions/32421214/django-queryset-all-model1-objects-where-a-model2-exists-with-a-model1-and-the
    earned_badges = Badge.objects.filter(badgeassertion__user=request.user)

    context = {
        "heading": "Achievements",
        # "badge_type_dicts": badge_type_dicts,
        "badge_types": badge_types,
        "earned_badges": earned_badges,
    }
    return render(request, "badges/list.html" , context)

class BadgeDelete(DeleteView):
    model = Badge
    success_url = reverse_lazy('badges:list')

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super(BadgeDelete, self).dispatch(*args, **kwargs)

class BadgeUpdate(UpdateView):
    model = Badge
    form_class = BadgeForm
    # template_name = ''

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(BadgeUpdate, self).get_context_data(**kwargs)
        context['heading'] = "Update Achievment"
        context['action_value']= ""
        context['submit_btn_value']= "Update"
        return context

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super(BadgeUpdate, self).dispatch(*args, **kwargs)

@staff_member_required
def badge_create(request):
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

@staff_member_required
def badge_copy(request, badge_id):
    new_badge = get_object_or_404(Badge, pk=badge_id)
    new_badge.pk = None # autogen a new primary key (quest_id by default)
    new_badge.name = "Copy of " + new_badge.name
    # print(quest_to_copy)
    # print(new_quest)
    # new_quest.save()

    form =  BadgeForm(request.POST or None, instance = new_badge)
    if form.is_valid():
        form.save()
        return redirect('badges:list')
    context = {
        "heading": "Copy a Badge",
        "form": form,
        "submit_btn_value": "Create",
    }
    return render(request, "badges/badge_form.html", context)

@login_required
def detail(request, badge_id):
    #if there is an active submission, get it and display accordingly

    badge = get_object_or_404(Badge, pk=badge_id)
    # active_submission = QuestSubmission.objects.quest_is_available(request.user, q)

    context = {
        "heading": badge.name,
        "badge": badge,
    }
    return render(request, 'badges/detail.html', context)

########### Badge Assertion Views #########################

@staff_member_required
def assertion_create(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    form = BadgeAssertionForm(request.POST or None, initial={'user': user})

    if form.is_valid():
        new_assertion = form.save(commit=False)
        new_assertion.issued_by = request.user
        new_assertion.ordinal = BadgeAssertion.objects.get_assertion_ordinal(
                                    new_assertion.user, new_assertion.badge)
        new_assertion.save()

        notify.send(
            new_assertion.issued_by,
            # action=...,
            target=new_assertion,
            recipient=new_assertion.user,
            affected_users=[new_assertion.user,],
            icon="<i class='fa fa-fw fa-lg fa-trophy text-warning'></i>",
            verb='granted')

        messages.success(request, ("Achievement " + str(new_assertion) + " granted to " + str(new_assertion.user)))

        return redirect('badges:list')

    context = {
        "heading": "Grant an Achievment",
        "form": form,
        "submit_btn_value": "Grant",
    }

    return render(request, "badges/assertion_form.html", context)

@staff_member_required
def assertion_delete(request, assertion_id):
    assertion = get_object_or_404(BadgeAssertion, pk=assertion_id)

    if request.method=='POST':
        user = assertion.user
        notify.send(
            request.user,
            # action=...,
            target=assertion.badge,
            recipient=user,
            affected_users=[user,],
            icon="<span class='fa-stack'>" + \
                "<i class='fa fa-trophy fa-stack-1x text-warning'></i>" + \
                "<i class='fa fa-ban fa-stack-2x text-danger'></i>" + \
                "</span>",
            verb='revoked')

        messages.success(request,
                            ("Badge " + str(assertion) + " revoked from " + str(assertion.user)
                        ))
        assertion.delete()
        return redirect('profiles:profile_detail', pk = user.id)

    template_name='badges/assertion_confirm_delete.html'
    return render(request, template_name, {'object':assertion})


@staff_member_required
def grant(request, badge_id, user_id):

    badge = get_object_or_404(Badge, pk=badge_id)
    user = get_object_or_404(User, pk=user_id)
    issued_by = request.user
    new_assertion= BadgeAssertion.objects.create_assertion(user, badge, issued_by)
    if new_assertion is None:
        print("This achievement is not available, why is it showing up?")
        raise Http404 #shouldn't get here
    return redirect('profiles:profile_detail', pk = user_id)
