from django.contrib.auth import get_user_model
from django.db import connection
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from library.tests.test_views import LibraryTenantTestCaseMixin
from library.utils import (
    get_library_schema_name,
    is_library_schema_requested,
    library_schema_context,
    library_schema_if_requested,
)
from model_bakery import baker
from quest_manager.models import Quest

User = get_user_model()


class QuestLibraryUtilsTestCase(SimpleTestCase):

    def test_library_schema_context__switches_and_restores_schema(self):
        """The context manager switches to the library schema and restores the previous one on exit."""
        previous_schema = connection.schema_name

        with library_schema_context():
            self.assertEqual(connection.schema_name, 'library')

        self.assertEqual(connection.schema_name, previous_schema)


class IsLibrarySchemaRequestedTestCase(SimpleTestCase):
    """The Library flag is a boolean, and only a boolean."""

    def setUp(self):
        """Build a request factory for the POSTs each test sends."""
        self.factory = RequestFactory()

    def test_is_library_schema_requested__truthy_values(self):
        """Every form-encodable spelling of true asks for the Library."""
        for value in ('1', 'true', 'True', 'on', 'yes'):
            with self.subTest(value=value):
                request = self.factory.post('/', {'use_library_schema': value})
                self.assertTrue(is_library_schema_requested(request))

    def test_is_library_schema_requested__falsy_and_missing_values(self):
        """No flag, or a falsy one, means the caller's own deck."""
        for data in ({}, {'use_library_schema': '0'}, {'use_library_schema': ''}, {'use_library_schema': 'false'}):
            with self.subTest(data=data):
                request = self.factory.post('/', data)
                self.assertFalse(is_library_schema_requested(request))

    def test_is_library_schema_requested__schema_name_is_not_a_flag(self):
        """Posting a schema name as the flag value is not a request for that schema."""
        request = self.factory.post('/', {'use_library_schema': 'some_other_deck'})
        self.assertFalse(is_library_schema_requested(request))


class LibrarySchemaIfRequestedTestCase(LibraryTenantTestCaseMixin):
    """`library_schema_if_requested` resolves the schema itself, never from the request."""

    def setUp(self):
        """Build a request factory and attach this test's tenant to each request."""
        self.factory = RequestFactory()

    def _request(self, data):
        """Build a POST request carrying the current tenant, as the middleware would.

        Args:
            data (dict): form fields to post.

        Returns:
            HttpRequest: the POST request, with `tenant` set to the test tenant so
            the schema resolution under test has a deck to fall back to.
        """
        request = self.factory.post('/', data)
        request.tenant = connection.tenant
        return request

    def test_library_schema_if_requested__flag_set_switches_to_library(self):
        """With the flag set, the context manager enters the Library schema."""
        with library_schema_if_requested(self._request({'use_library_schema': '1'})):
            self.assertEqual(connection.schema_name, get_library_schema_name())

    def test_library_schema_if_requested__no_flag_stays_on_the_callers_deck(self):
        """Without the flag, the context manager stays on the requesting tenant's schema."""
        own_schema = connection.schema_name

        with library_schema_if_requested(self._request({})):
            self.assertEqual(connection.schema_name, own_schema)

    def test_library_schema_if_requested__arbitrary_schema_name_is_ignored(self):
        """A schema name posted under the old `use_schema` key does not switch schemas.

        Regression test: `use_schema` used to be read straight off the POST and handed to
        `schema_context`, so any authenticated user could read another deck's content by
        posting that deck's schema name. Schema names are the decks' public subdomains.
        """
        own_schema = connection.schema_name

        with library_schema_if_requested(self._request({'use_schema': get_library_schema_name()})):
            self.assertEqual(connection.schema_name, own_schema)


class AjaxQuestInfoSchemaIsolationTestCase(LibraryTenantTestCaseMixin):
    """The quest preview endpoint must not serve content from an arbitrary schema."""

    LIBRARY_MARKER = 'library-only-marker-for-schema-isolation'

    @classmethod
    def setUpTestData(cls):
        """Put a uniquely-marked quest in the Library and give the local deck a staff user."""
        with library_schema_context():
            cls.library_quest = baker.make(
                Quest,
                name='Library Isolation Quest',
                short_description=cls.LIBRARY_MARKER,
                published=True,
                archived=False,
            )
        cls.test_teacher = User.objects.create_user('isolation_teacher', is_staff=True)

    def _post_preview(self, data):
        """POST the quest-preview endpoint for the Library quest's pk.

        Args:
            data (dict): form fields to post, e.g. the schema flag under test.

        Returns:
            HttpResponse: the endpoint's response. 200 with a `quest_info_html`
            JSON body when a quest was found, 404 when none was visible.
        """
        return self.client.post(
            reverse('quests:ajax_quest_info', args=[self.library_quest.id]),
            data=data,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

    def test_ajax_quest_info__foreign_schema_name_does_not_leak_content(self):
        """Naming another schema in the POST does not serve that schema's quest.

        Regression test for the `use_schema` POST parameter, which switched the
        connection to any schema the caller named.
        """
        self.client.force_login(self.test_teacher)

        response = self._post_preview({'use_schema': get_library_schema_name()})

        # Either the pk does not exist on this deck (404) or a local quest is served,
        # but the other schema's content must never come back.
        if response.status_code == 200:
            self.assertNotIn(self.LIBRARY_MARKER, response.json()['quest_info_html'])
        else:
            self.assertEqual(response.status_code, 404)

    def test_ajax_quest_info__library_flag_still_serves_library_content(self):
        """The supported flag still renders the Library preview the accordion needs."""
        self.client.force_login(self.test_teacher)

        response = self._post_preview({'use_library_schema': 1})

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.LIBRARY_MARKER, response.json()['quest_info_html'])
