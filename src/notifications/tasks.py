import logging
import smtplib
from datetime import timedelta
from email.utils import formataddr
from urllib.parse import urlsplit

from django.conf import settings
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

User = get_user_model()

logger = logging.getLogger(__name__)


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


@app.task(name='notifications.tasks.email_notifications_to_users_on_schema', bind=True, max_retries=5)
def email_notifications_to_users_on_schema(self, root_url, only_usernames=None):
    """Email each user's unread-notification digest for one deck, one message at a time.

    Sending per message keeps one rejected message from aborting the rest of
    the deck's batch (a mid-batch SMTP error used to lose every digest after
    it). Failures are sorted by SMTP class: a permanent (5xx) refusal drops
    that user's digest with a log line, while a temporary one (4xx, like
    Gmail's 451 rate-limit rejection, or a dropped connection or timeout)
    collects the user for a retry of the UNSENT remainder only, with
    exponential backoff, so nobody already emailed gets a duplicate. If the
    retries run out, celery surfaces the failure to monitoring, and the
    affected notifications remain unread, so they roll into the next daily
    digest rather than being lost.

    Args:
        root_url: The deck's root URL; names the deck in the subject and sender.
        only_usernames: Retry plumbing: build digests only for these users.
            None (the nightly run) means every eligible user.

    Returns:
        str: A short summary for the worker log.
    """
    notification_emails = get_notification_emails(root_url, only_usernames=only_usernames)
    # one backend instance; each send opens and closes its own short SMTP
    # session, so a connection killed by one failure can't poison the next send
    connection = mail.get_connection()
    sent = 0
    dropped = 0
    retry_usernames = []
    for email in notification_emails:
        try:
            connection.send_messages([email])
            sent += 1
        except smtplib.SMTPResponseException as e:
            # one status code for the message: 4xx means "try again later"
            if 400 <= e.smtp_code < 500:
                retry_usernames.append(email.recipient_username)
            else:
                dropped += 1
                logger.warning(
                    "notification email to %s permanently refused: %s %s",
                    email.to, e.smtp_code, e.smtp_error)
        except smtplib.SMTPRecipientsRefused as e:
            # every recipient refused, each with its own status (a digest has
            # exactly one recipient, but the exception is shaped as a mapping)
            codes = [code for code, _ in e.recipients.values()]
            if any(400 <= code < 500 for code in codes):
                retry_usernames.append(email.recipient_username)
            else:
                dropped += 1
                logger.warning("notification email to %s refused: %s", email.to, e.recipients)
        except (smtplib.SMTPException, ConnectionError, TimeoutError) as e:
            # the session itself failed (disconnected, timed out): temporary
            logger.info("notification email to %s hit a transient send failure: %s", email.to, e)
            retry_usernames.append(email.recipient_username)

    summary = f"Sent {sent} notification emails"
    if dropped:
        summary += f", dropped {dropped} permanently refused"
    if retry_usernames:
        # 5, 10, 20, 40, then 80 minutes; raises Retry, so the summary so far
        # travels in the retry's own log line
        raise self.retry(
            kwargs={'root_url': root_url, 'only_usernames': retry_usernames},
            countdown=300 * (2 ** self.request.retries),
        )
    return summary


def get_notification_emails(root_url, only_usernames=None):
    """Build the digest emails for every user on the deck's notification mailing list.

    Args:
        root_url: The deck's root URL, passed through to the per-user builder.
        only_usernames: When given, build only these users' digests (the send
            task's retry path re-sends just the users whose sends failed
            temporarily). None means the whole mailing list.

    Returns:
        list: EmailMultiAlternatives objects, each tagged with the recipient's
        username as ``recipient_username`` so a failed send can name the user
        to retry without reverse-mapping their email address.
    """
    users_to_email = Profile.objects.get_mailing_list(for_notification_email=True)

    notification_emails = []

    for user in users_to_email:
        if only_usernames is not None and user.username not in only_usernames:
            continue
        email = generate_notification_email(user, root_url)
        if email:
            email.recipient_username = user.username
            notification_emails.append(email)

    return notification_emails


def generate_notification_email(user, root_url):
    """Build the daily unread-notifications digest email for a single user.

    Args:
        user: The recipient User; their unread notifications (and, for staff, submissions
            awaiting approval) make up the email, and their email is the To address.
        root_url: The deck's root URL; its host names the deck in the subject and sender.

    Returns:
        EmailMultiAlternatives ready to send, or None when there is nothing to send:
        a non-staff user not currently enrolled, or a user with no unread notifications
        and (for staff) no submissions awaiting approval.
    """
    html_template = get_template('notifications/email_notifications.html')
    # Name the deck the email is from so recipients can tell decks apart even when a deck
    # hasn't customised its logo (#2338). root_url is the deck's root URL, so its host is
    # the deck's domain (e.g. "deckname.bytedeck.com"); .hostname drops any scheme/port.
    deck_domain = urlsplit(root_url).hostname or root_url
    subject = f'Notifications from {deck_domain}'
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
        # Show the deck's domain as the sender name so a recipient can tell which deck an
        # email is from at a glance, while keeping the actual sending address (the one the
        # mail server is authorised for) unchanged (#2338). Fall back to the default sender
        # when DEFAULT_FROM_EMAIL isn't configured.
        from_email = formataddr((deck_domain, settings.DEFAULT_FROM_EMAIL)) if settings.DEFAULT_FROM_EMAIL else None
        email_msg = EmailMultiAlternatives(subject, text_content, from_email=from_email, to=[to_email_address])
        email_msg.attach_alternative(html_content, "text/html")

        return email_msg
    else:
        return None
