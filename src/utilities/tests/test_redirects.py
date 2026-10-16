from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from utilities.redirects import redirect_back, safe_local_url, where_from


class SafeLocalUrlTest(SimpleTestCase):
    """safe_local_url, which only lets a url through when it stays on this site."""

    def setUp(self):
        """A request to this site, as the test client's host."""
        self.request = RequestFactory().get('/quests/')

    def test_safe_local_url__a_path_or_this_hosts_url_is_kept(self):
        """A path on this site, or a full url naming this host, may be gone to."""
        self.assertEqual(safe_local_url(self.request, '/quests/approvals/flagged/'), '/quests/approvals/flagged/')
        self.assertEqual(safe_local_url(self.request, 'http://testserver/quests/drafts/'), 'http://testserver/quests/drafts/')

    def test_safe_local_url__another_site_or_nothing_is_refused(self):
        """Another site's url, or none at all, gives None, so a view can't be used as an open redirect."""
        self.assertIsNone(safe_local_url(self.request, 'https://elsewhere.example/'))
        self.assertIsNone(safe_local_url(self.request, '//elsewhere.example/'))
        self.assertIsNone(safe_local_url(self.request, ''))
        self.assertIsNone(safe_local_url(self.request, None))

    def test_safe_local_url__https_is_not_downgraded(self):
        """For a request that came over https, an http url on this host is refused."""
        request = RequestFactory().get('/quests/', secure=True)

        self.assertIsNone(safe_local_url(request, 'http://testserver/quests/'))
        self.assertEqual(safe_local_url(request, 'https://testserver/quests/'), 'https://testserver/quests/')


class WhereFromTest(SimpleTestCase):
    """where_from, the page an action was taken from (#2859)."""

    def test_where_from__the_referring_page(self):
        """With no `next`, it's the page the browser sent the request from."""
        request = RequestFactory().get('/quests/1/hide/', HTTP_REFERER='http://testserver/quests/completed/')

        self.assertEqual(where_from(request), 'http://testserver/quests/completed/')

    def test_where_from__next_comes_first(self):
        """A posted `next`, then one in the query string, comes before the referring page: a page
        that passes the action through a confirmation of its own names where it started."""
        factory = RequestFactory()
        posted = factory.post('/drop/?next=/b/', {'next': '/a/'}, HTTP_REFERER='/c/')
        in_query = factory.get('/drop/?next=/b/', HTTP_REFERER='/c/')

        self.assertEqual(where_from(posted), '/a/')
        self.assertEqual(where_from(in_query), '/b/')

    def test_where_from__skips_another_site_and_avoided_pages(self):
        """A `next` on another site, or a page in `avoid`, is passed over for the next candidate,
        and with none left there's nowhere to go back to."""
        request = RequestFactory().post('/drop/', {'next': 'https://elsewhere.example/'},
                                        HTTP_REFERER='http://testserver/quests/submission/3/')

        self.assertIsNone(where_from(request, avoid={'/quests/submission/3/'}))
        self.assertEqual(where_from(request), 'http://testserver/quests/submission/3/')


class RedirectBackTest(SimpleTestCase):
    """redirect_back, which sends the user back where they were, or to a fallback."""

    def test_redirect_back__to_the_referring_page(self):
        """The response goes back to the page the action came from."""
        request = RequestFactory().get('/x/', HTTP_REFERER='/quests/approvals/flagged/')

        self.assertEqual(redirect_back(request, '/quests/').url, '/quests/approvals/flagged/')

    def test_redirect_back__to_the_fallback_when_there_is_nowhere_to_go_back_to(self):
        """With no page to return to, it goes to the fallback, with its arguments."""
        request = RequestFactory().get('/x/')

        self.assertEqual(redirect_back(request, '/quests/').url, '/quests/')
        self.assertEqual(redirect_back(request, 'quests:quest_detail', 7).url, reverse('quests:quest_detail', args=[7]))
