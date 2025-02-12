from datetime import timedelta
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.template.loader import get_template
from django_tenants.utils import get_tenant_model, tenant_context

from hackerspace_online.celery import app
from quest_manager.models import QuestSubmission
from notifications.models import Notification

from profile_manager.models import Profile

from siteconfig.models import SiteConfig

User = get_user_model()


@app.task(name='notifications.tasks.delete_old_notifications_for_all_tenants')
def delete_old_notifications_for_all_tenants():
    """Delete notifications older than three months for all tenants (schemas)."""
    for tenant in get_tenant_model().objects.exclude(schema_name='public'):
        with tenant_context(tenant):
            delete_old_notifications.apply_async(queue='default')

    return "Scheduled notifications.tasks.delete_old_notifications for all schemas/tenants"


@app.task(name='notifications.tasks.delete_old_notifications')
def delete_old_notifications():
    three_months_ago = timezone.now() - timedelta(days=90)
    deleted_count, _ = Notification.objects.filter(timestamp__lt=three_months_ago).delete()
    return f"Deleted {deleted_count} notifications."


@app.task(name='notifications.tasks.email_notification_to_users_on_all_schemas')
def email_notification_to_users_on_all_schemas():
    for tenant in get_tenant_model().objects.exclude(schema_name='public'):
        with tenant_context(tenant):
            root_url = tenant.get_root_url()
            email_notifications_to_users_on_schema.apply_async(args=[root_url], queue='default')

    return "Scheduled email_notifications_to_users_on_schema for all schemas"


@app.task(name='notifications.tasks.email_notifications_to_users_on_schema')
def email_notifications_to_users_on_schema(root_url):

    notification_emails = get_notification_emails(root_url)
    connection = mail.get_connection()
    connection.send_messages(notification_emails)
    # send_email_notification_tenant.delay(root_url)

    return f"Sent {len(notification_emails)} notification emails"


def get_notification_emails(root_url):
    users_to_email = Profile.objects.get_mailing_list(for_notification_email=True)

    notification_emails = []

    for user in users_to_email:
        email = generate_notification_email(user, root_url)
        if email:
            notification_emails.append(email)

    return notification_emails


def generate_notification_email(user, root_url):
    """Generate an email notification from user"""
    html_template = get_template('notifications/email_notifications.html')
    subject = f'{SiteConfig.get().site_name_short} Notifications'
    to_email_address = user.email
    unread_notifications = Notification.objects.all_unread(user)
    submissions_awaiting_approval = None

    if user.is_staff:
        submissions_awaiting_approval = QuestSubmission.objects.all_awaiting_approval(teacher=user)

    # Do not generate email notification for users that are not currently enrolled
    if not user.is_staff and not user.profile.has_current_course:
        return None

    if unread_notifications or submissions_awaiting_approval:
        text_content = str(unread_notifications)

        html_content = html_template.render({
            'user': user,
            'notifications': unread_notifications,
            'submissions': submissions_awaiting_approval,
            'root_url': root_url,
            'profile_edit_url': reverse('profiles:profile_edit_own')
        })
        email_msg = EmailMultiAlternatives(subject, text_content, to=[to_email_address])
        email_msg.attach_alternative(html_content, "text/html")

        return email_msg
    else:
        return None
