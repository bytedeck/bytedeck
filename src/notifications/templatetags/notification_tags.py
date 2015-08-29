from django import template

from notifications.models import Notification

register = template.Library()

@register.filter
def notification_unread(target, user):
    if not user or not target:
        return None
    return Notification.objects.get_user_target_unread(user, target)

@register.filter
def notification_url(target, user):
    if not user or not target:
        return None
    note = Notification.objects.get_user_target(user, target)
    return note.get_url()
