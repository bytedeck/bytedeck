from email.utils import formataddr
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.shortcuts import get_object_or_404
from django.template.loader import get_template
from django.urls import reverse
from django.utils import timezone

from announcements.models import Announcement
from courses.models import CourseStudent
from hackerspace_online.celery import app
from notifications.signals import notify
from siteconfig.models import SiteConfig
from profile_manager.models import Profile

User = get_user_model()


@app.task(name='announcements.tasks.send_notifications')
def send_notifications(user_id, announcement_id):
    """Notify everyone taking a course that an announcement has been published.

    This is the in-app half of publishing; send_announcement_emails() is the other. They
    reach different people on purpose: a notification goes to everyone enrolled, while the
    email adds the teachers and drops anyone who did not ask for it, has no address, or has
    not verified the one they gave.

    Args:
        user_id (int): the staff member publishing, who the notification is sent as.
        announcement_id (int): the Announcement being published.
    """
    announcement = get_object_or_404(Announcement, pk=announcement_id)
    sending_user = User.objects.get(id=user_id)
    # everyone enrolled, test accounts included, so a test account sees what a student sees
    # (issue #2434)
    affected_users = CourseStudent.objects.all_users_in_open_semesters()
    notify.send(
        sending_user,
        # action=new_announcement,
        target=announcement,
        recipient=sending_user,
        affected_users=affected_users,
        icon="<i class='fa fa-lg fa-fw fa-newspaper-o text-info'></i>",
        verb='posted'
    )


@app.task(name='announcements.tasks.send_announcement_emails')
def send_announcement_emails(content, root_url, absolute_url):
    """Send a published announcement by email to everyone on the announcement mailing list.

    Args:
        content: The announcement's HTML content (used as the email body).
        root_url: The deck's root URL; its host names the deck in the subject and sender.
        absolute_url: The announcement's absolute URL, linked from the email.

    Returns:
        list[str]: the recipient email addresses the announcement was bcc'd to.
    """
    siteconfig = SiteConfig.get()
    # Name the deck the email is from so recipients can tell decks apart even when a deck
    # hasn't customised its logo (#2338). root_url is the deck's root URL, so its host is
    # the deck's domain (e.g. "deckname.bytedeck.com"); .hostname drops any scheme/port.
    deck_domain = urlsplit(root_url).hostname or root_url
    subject = f'Announcement from {deck_domain}'
    text_content = content
    html_template = get_template('announcements/email_announcement.html')
    html_content = html_template.render({
        'content': content,
        'absolute_url': absolute_url,
        'root_url': root_url,
        'config': siteconfig,
        'profile_edit_url': reverse('profiles:profile_edit_own')
    })

    profile_emails = Profile.objects.get_mailing_list(as_emails_list=True, for_announcement_email=True)

    # Show the deck's domain as the sender name so a recipient can tell which deck an email is
    # from at a glance, keeping the actual sending address (the one the mail server is
    # authorised for) unchanged (#2338). Fall back to the default sender when unconfigured.
    from_email = formataddr((deck_domain, settings.DEFAULT_FROM_EMAIL)) if settings.DEFAULT_FROM_EMAIL else None
    email_msg = EmailMultiAlternatives(
        subject,
        body=text_content,
        from_email=from_email,
        to=['contact@bytedeck.com'],
        bcc=profile_emails,
    )
    email_msg.attach_alternative(html_content, "text/html")
    email_msg.send()

    return profile_emails
    # print("Sending {} announcement emails.".format(len(users_to_email)))


@app.task(name='announcements.tasks.publish_announcement')
def publish_announcement(user_id, announcement_id, root_url):
    """ Publish the announcement, including:
            - edit model instance
            - push notifications
            - send announcement emails
    """
    # update model instance
    announcement = get_object_or_404(Announcement, pk=announcement_id)
    announcement.datetime_released = timezone.now()
    announcement.draft = False
    announcement.auto_publish = False
    announcement.save()

    absolute_url = announcement.get_absolute_url()

    # push notifications
    send_notifications.apply_async(args=[user_id, announcement_id], queue='default')

    # Send the announcements by email to those who have ask for them, using celery
    send_announcement_emails.apply_async(args=[announcement.content, root_url, absolute_url], queue='default')
    # Email not set up anyway
