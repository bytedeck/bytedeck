from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse_lazy
from django.shortcuts import render, get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views.generic import ListView
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from notifications.signals import notify

from .models import Announcement
from .forms import AnnouncementForm

#function based views...
@login_required
def list(request):
    object_list = Announcement.objects.get_active()
    context = {
        'object_list': object_list,
    }
    return render(request, 'announcements/list.html', context)

@login_required
def copy(request, id):
    new_ann = get_object_or_404(Announcement, pk=id)
    new_ann.pk = None # autogen a new primary key (quest_id by default)
    new_ann.title = "Copy of " + new_ann.title
    # print(quest_to_copy)
    # print(new_quest)
    # new_quest.save()

    form = AnnouncementForm(request.POST or None, instance = new_ann)
    if form.is_valid():
        form.save()
        return redirect('announcements:list')
    context = {
        "title": "",
        "heading": "Copy an Announcement",
        "form": form,
        "submit_btn_value": "Create",
    }
    return render(request, "announcements/form.html", context)


# class based views
# class List(ListView):
#     model = Announcement
#     template_name = 'announcements/list.html'

# def create(request):
#     form = AnnouncementForm(request.POST or None)
#
#     context = {
#         "form": form,
#         "heading": "Create New Announcement",
#         "action_value": "/",
#         "submit_btn_value": "Publish"
#     }
#
#     return render(request, "announcements/form.html", context)

class Create(CreateView):
    model = Announcement
    form_class = AnnouncementForm
    # template_name = 'announcements/form.html'

    template_name = 'announcements/form.html'

    def form_valid(self, form):
        data = form.save(commit=False)
        data.author = self.request.user
        data.save()
        # notify.send(self.request.user, user="somerandomuser", action="New Announcement!")
        return super(Create, self).form_valid(form)

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(Create, self).get_context_data(**kwargs)
        # Add in a QuerySet of all the books
        context['heading'] = "Create New Announcement"
        context['action_value']= ""
        context['submit_btn_value']= "Publish"
        return context

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super(Create, self).dispatch(*args, **kwargs)

class Update(UpdateView):
    model = Announcement
    form_class = AnnouncementForm
    template_name = 'announcements/form_update.html'

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super(Update, self).dispatch(*args, **kwargs)

class Delete(DeleteView):
    model = Announcement
    template_name = 'announcements/delete.html'
    success_url = reverse_lazy('announcements:list')

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super(Create, self).dispatch(*args, **kwargs)
