import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import Http404, HttpResponseRedirect, redirect, render
from django.urls import reverse
from django.utils import timezone
from tenant.views import non_public_only_view

from hackerspace_online.decorators import xml_http_request_required

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

    # If this view is accessed with an id argument that doesn't match an existing notification, redirect to list view and display error message
    except Notification.DoesNotExist:
        messages.error(request, "This notification doesn't exist or has been deleted.")
        return HttpResponseRedirect(reverse('notifications:list'))


@xml_http_request_required
@non_public_only_view
@login_required
def ajax(request):
    if request.method == "POST":

        limit = 15
        notifications = Notification.objects.all_unread(request.user)
        count = notifications.count()
        # limit number of items else the list in the menu will go off
        # the bottom of the screen and can't get the links at the bottom...
        notifications = notifications[:limit]
        notes = []
        for note in notifications:
            notes.append(
                {
                    'link': str(note.get_link()),
                    'id': str(note.id),
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


@xml_http_request_required
@non_public_only_view
@login_required
def ajax_mark_read(request):
    if request.method == "POST":

        id = request.POST.get('id', None)
        n = Notification.objects.get(id=id)
        n.mark_read()
        return JsonResponse(data={})
    else:
        raise Http404
