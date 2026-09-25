import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import Http404, HttpResponseRedirect, get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from tenant.views import non_public_only_view

from hackerspace_online.decorators import xml_http_request_required
from utilities.sorting import apply_sort, resolve_sort

from .models import Notification

#: The columns the notifications list can be ordered by, keyed as its headings name them.
#: With none chosen it keeps the manager's own order, newest first.
NOTIFICATION_SORT_COLUMNS = {
    'date': 'timestamp',
    'status': 'unread',
}


def notifications_page(request, notifications):
    """Search, order and cut a page from a list of the reader's notifications (#2703).

    All of it happens here, before the page is taken, because the browser only ever holds
    one page: a search or sort applied there would answer a question about those 15
    notifications rather than about the list (#2410, #2582). `id` settles notifications
    that tie on the chosen column, newest first, so paging through a sorted list shows each
    of them exactly once.

    Args:
        request (HttpRequest): the current request, for its `q`, `sort` and `page`.
        notifications (NotificationQuerySet): the list to show, all of the reader's or only
            the unread.

    Returns:
        dict: the template's context: the page as `notifications`, the search term and how
        many matched it, and the column and direction the list is ordered by.
    """
    search_term = request.GET.get('q', '').strip()
    notifications = notifications.search(search_term)

    sort_column, sort_descending = resolve_sort(request, NOTIFICATION_SORT_COLUMNS)
    notifications = apply_sort(notifications, NOTIFICATION_SORT_COLUMNS, sort_column, sort_descending, tie_break='-id')

    # each rendered notification reads its sender/target/action generic FK
    # objects; prefetch them so the page issues a few grouped queries instead
    # of several per notification
    notifications = notifications.prefetch_related('sender_object', 'target_object', 'action_object')

    paginator = Paginator(notifications, 15)
    page = request.GET.get('page', 1)
    try:
        notifications = paginator.page(page)
    except PageNotAnInteger:
        notifications = paginator.page(1)
    except EmptyPage:
        notifications = paginator.page(paginator.num_pages)

    return {
        'notifications': notifications,
        'search_term': search_term,
        'num_matching': paginator.count,
        'sort_column': sort_column,
        'sort_descending': sort_descending,
    }


@non_public_only_view
@login_required
def list(request):
    """Every notification the reader has had, searchable, sortable and a page at a time."""
    context = notifications_page(request, Notification.objects.all_for_user(request.user))
    return render(request, 'notifications/list.html', context)


@non_public_only_view
@login_required
def list_unread(request):
    """The reader's unread notifications, searchable, sortable and a page at a time."""
    context = notifications_page(request, Notification.objects.all_unread(request.user))
    return render(request, "notifications/list.html", context)


@non_public_only_view
@login_required
def read_all(request):
    # mark every unread notification read in a single UPDATE instead of
    # saving each row individually.
    Notification.objects.all().mark_all_read(request.user)
    return redirect('notifications:list')


@non_public_only_view
@login_required
def read(request, id):
    """Mark the requester's own notification `id` as read, then redirect onward.

    `id` is the notification's primary key (from the URL). The notification is
    marked read only when it belongs to `request.user`; another user's id raises
    a 404. On success the view redirects to the `?next=` URL when that URL is
    safe, meaning a same-deck link (relative, or the current host) or one whose
    host is in `settings.NOTIFICATIONS_ALLOWED_REDIRECT_HOSTS` (github.com by
    default, for the release-announcement notice). Any other `next` (or none)
    falls back to the notifications list, so a crafted `next` can't turn this
    into an open redirect. A missing or deleted notification id also redirects
    to the list, with an error message. Returns an HttpResponseRedirect.
    """
    try:
        next = request.GET.get('next', None)
        notification = Notification.objects.get(id=id)
        if notification.recipient == request.user:
            notification.unread = False
            notification.time_read = timezone.now()
            notification.save()
            # Only follow ?next= when it stays on this deck or points at an
            # explicitly trusted host (github.com, for the release-announcement
            # notice); anything else falls back to the list so a crafted link
            # can't turn this into an open redirect.
            allowed_hosts = {request.get_host(), *settings.NOTIFICATIONS_ALLOWED_REDIRECT_HOSTS}
            if next and url_has_allowed_host_and_scheme(next, allowed_hosts=allowed_hosts, require_https=request.is_secure()):
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
        # get_link() reads the sender/action/target generic FKs of each
        # notification, so prefetch them to avoid 3 extra queries per row
        # (this endpoint fires on essentially every authenticated page load).
        notifications = Notification.objects.all_unread(request.user).prefetch_related(
            'sender_object', 'target_object', 'action_object',
        )
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
    """Mark one of the requesting user's own notifications as read.

    Scoped to the recipient so a user can't mark (and so hide) another user's
    notification, and so an id that doesn't exist is a 404 rather than an
    unhandled DoesNotExist.
    """
    if request.method == "POST":

        # the id is client-supplied: a missing or non-numeric one would raise
        # ValueError in the pk lookup below (a 500), so turn it away as a 404 first.
        try:
            id = int(request.POST.get('id', ''))
        except (TypeError, ValueError):
            raise Http404("No valid notification id provided.")

        n = get_object_or_404(Notification, id=id, recipient=request.user)
        n.mark_read()
        return JsonResponse(data={})
    else:
        raise Http404
