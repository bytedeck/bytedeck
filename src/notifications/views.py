import json

from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import Http404, HttpResponseRedirect, redirect, render
from django.urls import reverse
from django.utils import timezone
from tenant.views import non_public_only_view

from .models import Notification


@non_public_only_view
@login_required
def list(request):
    notifications_list = Notification.objects.all_for_user(request.user)

    paginator = Paginator(notifications_list, 15)
    page = request.GET.get('page', 1)

    try:
        notifications = paginator.page(page)
    except PageNotAnInteger:
        notifications = paginator.page(1)
    except EmptyPage:
        notifications = paginator.page(paginator.num_pages)

    context = {
        'notifications': notifications,
    }

    return render(request, 'notifications/list.html', context)


@non_public_only_view
@login_required
def list_unread(request):
    notifications = Notification.objects.all_unread(request.user)
    context = {
        "notifications": notifications,
    }
    return render(request, "notifications/list.html", context)


@non_public_only_view
@login_required
def read_all(request):
    notifications = Notification.objects.all_unread(request.user)

    for note in notifications:
        note.unread = False
        note.time_read = timezone.now()
        note.save()

    return redirect('notifications:list')


@non_public_only_view
@login_required
def read(request, id):
    try:
        next = request.GET.get('next', None)
        notification = Notification.objects.get(id=id)
        if notification.recipient == request.user:
            notification.unread = False
            notification.time_read = timezone.now()
            notification.save()
            if next is not None:
                return HttpResponseRedirect(next)
            else:
                return HttpResponseRedirect(reverse('notifications:list'))
        else:
            raise Http404
    except:  # noqa
        # TODO deal with this bare exception
        raise HttpResponseRedirect(reverse('notifications:list'))


@non_public_only_view
@login_required
def ajax(request):
    if request.is_ajax() and request.method == "POST":

        limit = 15
        notifications = Notification.objects.all_unread(request.user)
        count = notifications.count()
        # limit number of items else the list in the menu will go off
        # the bottom of the screen and can't get the links at the bottom...
        notifications = notifications[:limit]
        notes = []
        for note in notifications:
            removable = note.target_content_type != ContentType.objects.get(
                app_label="announcements",
                model='announcement'
            )
            notes.append(
                {
                    'link': str(note.get_link()),
                    'id': str(note.id),
                    'removable': removable,
                }
            )

        data = {
            "notifications": notes,
            "count": count,
            "limit": limit,
        }
        json_data = json.dumps(data)

        return HttpResponse(json_data, content_type='application/json')
    else:
        raise Http404


@non_public_only_view
@login_required
def ajax_mark_read(request):
    if request.is_ajax() and request.method == "POST":

        id = request.POST.get('id', None)
        n = Notification.objects.get(id=id)
        n.mark_read()
        return JsonResponse(data={})
    else:
        raise Http404

# class NotifcationOptionsForm(ModelForm):
#     class Meta:
#         model = UserNotificationOptionSet
#         fields = '__all__'
#
# def server_create(request, template_name='servers/server_form.html'):
#     form = ServerForm(request.POST or None)
#     if form.is_valid():
#         form.save()
#         return redirect('server_list')
#     return render(request, template_name, {'form':form})
#
# def server_update(request, pk, template_name='servers/server_form.html'):
#     server = get_object_or_404(Server, pk=pk)
#     form = ServerForm(request.POST or None, instance=server)
#     if form.is_valid():
#         form.save()
#         return redirect('server_list')
#     return render(request, template_name, {'form':form})
#
# def server_delete(request, pk, template_name='servers/server_confirm_delete.html'):
#     server = get_object_or_404(Server, pk=pk)
#     if request.method=='POST':
#         server.delete()
#         return redirect('server_list')
#     return render(request, template_name, {'object':server})
