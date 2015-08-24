from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.urlresolvers import reverse_lazy, reverse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import ListView
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from notifications.signals import notify

from .models import Announcement
from .forms import AnnouncementForm

#function based views...
@login_required
def list(request, id=None):
    object_list = Announcement.objects.get_active()
    paginator = Paginator(object_list, 15)
    page = request.GET.get('page')
    active_id = 0
    # we want the page of a specific object
    if id is not None:
        active_obj = get_object_or_404(Announcement, pk=id)
        for pg in paginator.page_range:
            object_list = paginator.page(pg)
            if active_obj in object_list:
                page = pg
                active_id = int(id)
                break

    try:
        object_list = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        object_list = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        object_list = paginator.page(paginator.num_pages)

    context = {
        'object_list': object_list,
        'active_id': active_id,
    }
    return render(request, 'announcements/list.html', context)

@staff_member_required
def copy(request, id):
    new_ann = get_object_or_404(Announcement, pk=id)
    new_ann.pk = None # autogen a new primary key (quest_id by default)
    new_ann.title = "Copy of " + new_ann.title

    form = AnnouncementForm(request.POST or None, instance = new_ann)
    if form.is_valid():
        new_announcement = form.save(commit=False)
        new_announcement.author = request.user
        new_announcement.datetime_created = timezone.now
        new_announcement.save()
        form.save()

        affected_users = User.objects.all().filter(is_active=True)
        notify.send(
            request.user,
            action=new_announcement,
            target=new_announcement,
            recipient=request.user,
            affected_users=affected_users,
            verb='posted')
        # return redirect('announcements:list', id=new_announcement.id)
        return redirect(new_announcement)
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
    template_name = 'announcements/form.html'

    def form_valid(self, form):
        new_announcement = form.save(commit=False)
        new_announcement.author = self.request.user
        new_announcement.save()

        affected_users = User.objects.all().filter(is_active=True)
        notify.send(
            self.request.user,
            # action=new_announcement,
            target=new_announcement,
            recipient=self.request.user,
            affected_users=affected_users,
            icon="<i class='fa fa-lg fa-newspaper-o text-info'></i>",
            verb='posted')

        return super(Create, self).form_valid(form)

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(Create, self).get_context_data(**kwargs)
        # Add in a QuerySet of all the books
        context['heading'] = "Create New Announcement"
        context['action_value']= ""
        context['submit_btn_value']= "Publish"
        return context

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super(Create, self).dispatch(*args, **kwargs)

class Update(UpdateView):
    model = Announcement
    form_class = AnnouncementForm
    template_name = 'announcements/form.html'

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(Update, self).get_context_data(**kwargs)
        # Add in a QuerySet of all the books
        context['heading'] = "Edit Announcement"
        context['action_value']= ""
        context['submit_btn_value']= "Update"
        return context

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super(Update, self).dispatch(*args, **kwargs)

class Delete(DeleteView):
    model = Announcement
    template_name = 'announcements/delete.html'
    success_url = reverse_lazy('announcements:list')

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super(Delete, self).dispatch(*args, **kwargs)
