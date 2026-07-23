from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.shortcuts import reverse
from django.test.utils import CaptureQueriesContext

from django_tenants.test.client import TenantClient
from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase, ViewTestUtilsMixin
from notifications.models import Notification
from notifications.signals import notify

User = get_user_model()


class NotificationViewTests(ViewTestUtilsMixin, ByteDeckTenantTestCase):

    # includes some basic model data
    # fixtures = ['initial_data.json']

    @classmethod
    def setUpTestData(cls):
        """Create a teacher and two students (a teacher must exist first or profile creation fails)."""
        # need a teacher before students can be created or the profile creation will fail when trying to notify
        cls.test_teacher = User.objects.create_user('test_teacher', is_staff=True)
        cls.test_student1 = User.objects.create_user('test_student')
        cls.test_student2 = baker.make(User)

    def setUp(self):
        """Set up a tenant client for each test."""
        self.client = TenantClient(self.tenant)

    def test_notification_page_status_codes__anonymous(self):
        ''' If not logged in then all views should redirect to home page '''

        self.assertRedirectsLogin('notifications:list')
        self.assertRedirectsLogin('notifications:list_unread')
        self.assertRedirectsLogin('notifications:read', kwargs={'id': 1})
        self.assertRedirectsLogin('notifications:read_all')

        self.assert403('notifications:ajax')
        self.assert403('notifications:ajax_mark_read')
        self.assertEqual(self.client.get(reverse('notifications:ajax_mark_read'), HTTP_X_REQUESTED_WITH='XMLHttpRequest').status_code, 302)
        self.assertEqual(self.client.get(reverse('notifications:ajax'), HTTP_X_REQUESTED_WITH='XMLHttpRequest').status_code, 302)

    def test_notification_page_status_codes__students(self):
        """A logged-in student can view list pages but not the ajax-only endpoints."""
        # log in student1
        self.client.force_login(self.test_student1)

        # Accessible views:
        self.assertEqual(self.client.get(reverse('notifications:list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('notifications:list_unread')).status_code, 200)

        self.assertRedirects(
            response=self.client.get(reverse('notifications:read_all')),
            expected_url=reverse('notifications:list'),
        )

        # Inaccessible views:
        # These views require an post request via ajax
        self.assert403('notifications:ajax_mark_read')
        self.assert403('notifications:ajax')
        self.assertEqual(self.client.get(reverse('notifications:ajax_mark_read'), HTTP_X_REQUESTED_WITH='XMLHttpRequest').status_code, 404)
        self.assertEqual(self.client.get(reverse('notifications:ajax'), HTTP_X_REQUESTED_WITH='XMLHttpRequest').status_code, 404)

    def test_notification_page_status_codes__teachers(self):
        """A logged-in teacher can view list pages but not the ajax-only endpoints."""
        # log in student1
        self.client.force_login(self.test_teacher)

        # Accessible views:
        self.assertEqual(self.client.get(reverse('notifications:list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('notifications:list_unread')).status_code, 200)

        # Bad id notification read request should redirect to list view
        self.assertRedirects(
            response=self.client.get(reverse('notifications:read', args=[999])),
            expected_url=reverse('notifications:list'),
        )

        self.assertRedirects(
            response=self.client.get(reverse('notifications:read_all')),
            expected_url=reverse('notifications:list'),
        )

        # Inaccessible views:
        # These views require an post request via ajax
        self.assert403('notifications:ajax_mark_read')
        self.assert403('notifications:ajax')
        self.assertEqual(self.client.get(reverse('notifications:ajax_mark_read'), HTTP_X_REQUESTED_WITH='XMLHttpRequest').status_code, 404)
        self.assertEqual(self.client.get(reverse('notifications:ajax'), HTTP_X_REQUESTED_WITH='XMLHttpRequest').status_code, 404)

    def test_ajax_mark_read__marks_notification_read(self):
        """Marks a Notification as read via Ajax (by setting unread = FALSE)."""
        # log in student1
        self.client.force_login(self.test_student1)

        notification = baker.make(
            'notifications.Notification', recipient=self.test_student1,
            sender_content_type=ContentType.objects.get_for_model(User), sender_object_id=self.test_teacher.id,
        )
        # make sure it is unread
        self.assertTrue(notification.unread)

        # mark it as read via the view being tested
        ajax_data = {
            'id': notification.id,
        }
        response = self.client.post(
            reverse('notifications:ajax_mark_read'),
            data=ajax_data,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)

        # the notification is actually marked read, not just a 200 response
        notification.refresh_from_db()
        self.assertFalse(notification.unread)

    def test_ajax__returns_200_for_logged_in_student(self):
        """A logged-in student's ajax POST to the notifications endpoint returns 200."""
        # log in student1
        self.client.force_login(self.test_student1)

        response = self.client.post(
            reverse('notifications:ajax'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)

    def test_ajax__query_count_does_not_grow_with_notifications(self):
        """The dropdown AJAX prefetches each notification's sender/target/action
        generic FKs, so its query count stays flat as unread notifications grow
        (get_link() reads three generic FKs per row)."""
        self.client.force_login(self.test_student1)
        url = reverse('notifications:ajax')

        # every notification shares the same sender (a User) and target (a Quest)
        # content types, so prefetching collapses their generic-FK reads to a
        # fixed number of queries regardless of the notification count
        target = baker.make('quest_manager.Quest')

        def notify_student(times):
            for _ in range(times):
                notify.send(
                    self.test_teacher,
                    target=target,
                    recipient=self.test_student1,
                    affected_users=[self.test_student1],
                    verb="did",
                )

        # warm per-request caches (SiteConfig, content types, session) so the two
        # measurements below differ only by the number of notifications rendered
        notify_student(2)
        self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        with CaptureQueriesContext(connection) as few_queries:
            self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        notify_student(5)  # 7 unread total, still under the 15-item cap
        with CaptureQueriesContext(connection) as many_queries:
            self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        # without the prefetch each extra notification adds several generic-FK queries
        self.assertEqual(len(many_queries.captured_queries), len(few_queries.captured_queries))

    def test_read_all__marks_all_read_and_sets_time_read(self):
        """The read_all view marks every unread notification read and stamps
        time_read, then redirects to the notifications list."""
        self.client.force_login(self.test_student1)
        baker.make(
            Notification, recipient=self.test_student1, unread=True, time_read=None, _quantity=3,
        )
        self.assertEqual(Notification.objects.all_unread(self.test_student1).count(), 3)

        response = self.client.get(reverse('notifications:read_all'))
        # don't fetch the target: baker-made notifications have random generic FKs
        # that the list template would try to render
        self.assertRedirects(response, reverse('notifications:list'), fetch_redirect_response=False)

        self.assertEqual(Notification.objects.all_unread(self.test_student1).count(), 0)
        for note in Notification.objects.filter(recipient=self.test_student1):
            self.assertIsNotNone(note.time_read)

    def test_list__non_integer_page_returns_first_page(self):
        """A non-integer ?page= falls back to the first page (PageNotAnInteger)."""
        self.client.force_login(self.test_student1)
        response = self.client.get(reverse('notifications:list'), {'page': 'notanumber'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['notifications'].number, 1)

    def test_list__out_of_range_page_returns_last_page(self):
        """An out-of-range ?page= falls back to the last page (EmptyPage)."""
        # The list paginates at 15/page; send >15 notifications with a real target
        # (so the list template can render them) to produce a distinguishable 2nd page.
        target = baker.make('quest_manager.Quest')
        for _ in range(16):
            notify.send(
                self.test_teacher, target=target, recipient=self.test_student1,
                affected_users=[self.test_student1], verb="did",
            )
        self.client.force_login(self.test_student1)

        response = self.client.get(reverse('notifications:list'), {'page': 9999})

        self.assertEqual(response.status_code, 200)
        page = response.context['notifications']
        self.assertGreater(page.paginator.num_pages, 1)
        self.assertEqual(page.number, page.paginator.num_pages)

    def test_read__marks_own_notification_read_and_redirects_to_list(self):
        """Reading one's own notification marks it read (unread=False, time_read set) and
        redirects to the list when no ?next is given."""
        self.client.force_login(self.test_student1)
        note = baker.make(
            Notification, recipient=self.test_student1, unread=True, time_read=None,
            sender_content_type=ContentType.objects.get_for_model(User), sender_object_id=self.test_teacher.id,
        )

        response = self.client.get(reverse('notifications:read', args=[note.id]))

        self.assertRedirects(response, reverse('notifications:list'), fetch_redirect_response=False)
        note.refresh_from_db()
        self.assertFalse(note.unread)
        self.assertIsNotNone(note.time_read)

    def test_read__redirects_to_next_when_provided(self):
        """Reading one's own notification with ?next= redirects to that url."""
        self.client.force_login(self.test_student1)
        note = baker.make(
            Notification, recipient=self.test_student1, unread=True,
            sender_content_type=ContentType.objects.get_for_model(User), sender_object_id=self.test_teacher.id,
        )

        response = self.client.get(reverse('notifications:read', args=[note.id]), {'next': '/quests/available/'})

        self.assertRedirects(response, '/quests/available/', fetch_redirect_response=False)

    def test_read__other_users_notification_raises_404(self):
        """Reading a notification that belongs to another user is a 404 (not readable)."""
        self.client.force_login(self.test_student1)
        note = baker.make(
            Notification, recipient=self.test_student2, unread=True,
            sender_content_type=ContentType.objects.get_for_model(User), sender_object_id=self.test_teacher.id,
        )

        response = self.client.get(reverse('notifications:read', args=[note.id]))

        self.assertEqual(response.status_code, 404)
