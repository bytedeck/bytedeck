from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse_lazy
from django.shortcuts import render, get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from .models import Badge
from .forms import BadgeForm

@login_required
def list(request):

    badges = Badge.objects.all()

    context = {
        "heading": "Achievements",
        "badges": badges,
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
