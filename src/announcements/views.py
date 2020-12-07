from datetime import timedelta

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.messages.views import SuccessMessageMixin
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.shortcuts import Http404, get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from comments.forms import CommentForm
from comments.models import Comment
from notifications.signals import notify
from tenant.utils import get_root_url
from tenant.views import NonPublicOnlyViewMixin, non_public_only_view

from .forms import AnnouncementForm
from .models import Announcement
from .tasks import publish_announcement, send_notifications


@non_public_only_view
@login_required
def comment(request, ann_id):
    announcement = get_object_or_404(Announcement, pk=ann_id)
    origin_path = announcement.get_absolute_url()

    if request.method == "POST":

        form = CommentForm(request.POST)

        if form.is_valid():
            comment_text = form.cleaned_data.get('comment_text')
            if not comment_text:
                comment_text = ""
            comment_new = Comment.objects.create_comment(
                user=request.user,
                path=origin_path,
                text=comment_text,
                target=announcement,
            )

            if 'comment_button' in request.POST:
                note_verb = "commented on"
                # icon = "<i class='fa fa-lg fa-comment-o text-info'></i>"
                icon = "<span class='fa-stack'>" + \
                       "<i class='fa fa-newspaper-o fa-stack-1x'></i>" + \
                       "<i class='fa fa-comment-o fa-stack-2x text-info'></i>" + \
                       "</span>"
                if request.user.is_staff:
                    # get other commenters on this announcement
                    affected_users = None
                else:  # student comment
                    affected_users = User.objects.filter(is_staff=True)
            else:
                raise Http404("unrecognized submit button")

            notify.send(
                request.user,
                action=comment_new,
                target=announcement,
                recipient=request.user,
                affected_users=affected_users,
                verb=note_verb,
                icon=icon,
            )
            messages.success(request, ("Announcement " + note_verb))
            return redirect(origin_path)
        else:
            messages.error(request, "There was an error with your comment.")
            return redirect(origin_path)
    else:
        raise Http404


@non_public_only_view
@login_required
def list2(request, ann_id=None):
    return list(request, ann_id, template='announcements/list2.html')


@non_public_only_view
@login_required
def list(request, ann_id=None, template='announcements/list.html'):
    archived = '/archived/' in request.path_info
    if request.user.is_staff:
        if archived:
            object_list = Announcement.objects.get_archived()
        else:
            object_list = Announcement.objects.get_active()
    else:
        object_list = Announcement.objects.get_for_students()

    paginator = Paginator(object_list, 20)
    page = request.GET.get('page')
    active_id = 0
    # we want the page of a specific object
    if ann_id is not None:
        active_obj = get_object_or_404(Announcement, pk=ann_id)
        for pg in paginator.page_range:
            object_list = paginator.page(pg)
            if active_obj in object_list:
                page = pg
                active_id = int(ann_id)
                break

    try:
        object_list = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        object_list = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        object_list = paginator.page(paginator.num_pages)

    comment_form = CommentForm(request.POST or None, label="")

    context = {
        'comment_form': comment_form,
        'object_list': object_list,
        'active_id': active_id,
        'archived': archived,
    }
    return render(request, template, context)


@non_public_only_view
@staff_member_required
def copy(request, ann_id):
    new_ann = get_object_or_404(Announcement, pk=ann_id)
    new_ann.pk = None  # autogen a new primary key (quest_id by default)
    new_ann.title = "Copy of " + new_ann.title
    new_ann.draft = True
    new_ann.datetime_released = new_ann.datetime_released + timedelta(days=7)

    form = AnnouncementForm(request.POST or None, instance=new_ann)
    if form.is_valid():
        new_announcement = form.save(commit=False)
        new_announcement.author = request.user
        new_announcement.datetime_created = timezone.now()

        new_announcement.save()
        form.save()

        if not new_announcement.draft:
            send_notifications.apply_async(args=[request.user.id, new_announcement.id], queue='default')
        return redirect(new_announcement)

    context = {
        "title": "",
        "heading": "Copy an Announcement",
        "form": form,
        "submit_btn_value": "Create",
    }
    return render(request, "announcements/form.html", context)


@non_public_only_view
@staff_member_required
def publish(request, ann_id):
    publish_announcement.apply_async(args=[request.user.id, ann_id, get_root_url()], queue='default')

    return redirect('announcements:list', ann_id=ann_id)


class Create(NonPublicOnlyViewMixin, SuccessMessageMixin, CreateView):
    model = Announcement
    form_class = AnnouncementForm
    template_name = 'announcements/form.html'

    def form_valid(self, form):
        new_announcement = form.save(commit=False)
        new_announcement.author = self.request.user
        new_announcement.save()

        if not new_announcement.draft:
            send_notifications.apply_async(args=[self.request.user.id, new_announcement.id], queue='default')

        return super(Create, self).form_valid(form)

    def get_success_message(self, cleaned_data):
        if self.object.draft:
            return "Draft Announcement created."
        else:
            return "New Announcement published and broadcast to students!"

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(Create, self).get_context_data(**kwargs)
        # Add in a QuerySet of all the books
        context['heading'] = "Create New Announcement"
        context['submit_btn_value'] = "Save"
        return context

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super(Create, self).dispatch(*args, **kwargs)


class Update(NonPublicOnlyViewMixin, SuccessMessageMixin, UpdateView):
    model = Announcement
    form_class = AnnouncementForm
    template_name = 'announcements/form.html'

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(Update, self).get_context_data(**kwargs)
        # Add in a QuerySet of all the books
        context['heading'] = "Edit Announcement"
        context['submit_btn_value'] = "Update"
        return context

        # return super(Update, self).form_valid(form)

    def get_success_message(self, cleaned_data):
        if self.object.draft:
            return "Draft Announcement updated."
        else:
            return "Announcement updated but NOT (re-)broadcasted to students."

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super(Update, self).dispatch(*args, **kwargs)


class Delete(NonPublicOnlyViewMixin, DeleteView):
    model = Announcement
    template_name = 'announcements/delete.html'
    success_url = reverse_lazy('announcements:list')

    @method_decorator(staff_member_required)
    def dispatch(self, *args, **kwargs):
        return super(Delete, self).dispatch(*args, **kwargs)
