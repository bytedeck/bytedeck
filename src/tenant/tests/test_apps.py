from unittest.mock import patch

from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.http import Http404, HttpResponseRedirect
from django.test import RequestFactory

from badges.models import Badge

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from tenant.apps import _shortcut


class ShortcutMonkeyPatchTest(ByteDeckTenantTestCase):
    """Tests for tenant.apps._shortcut, the tenant-aware replacement for
    django.contrib.contenttypes.views.shortcut (the "view on site" redirect).

    The stock Django view pulls the domain from django.contrib.sites, which is
    not installed per tenant; _shortcut strips that out and simply redirects to
    the object's get_absolute_url. These tests drive every branch directly, since
    nothing in the normal test flow hits the patched view.
    """

    def setUp(self):
        """Provide a throwaway request and a seeded badge to redirect to."""
        self.request = RequestFactory().get("/")
        self.badge = Badge.objects.first()
        self.badge_ct = ContentType.objects.get_for_model(Badge)

    def test_shortcut__relative_url_redirects_to_object(self):
        """A found object redirects to its (relative) get_absolute_url."""
        response = _shortcut(self.request, self.badge_ct.pk, self.badge.pk)
        self.assertIsInstance(response, HttpResponseRedirect)
        self.assertEqual(response.url, self.badge.get_absolute_url())

    def test_shortcut__absolute_url_redirects_unchanged(self):
        """When get_absolute_url already includes a scheme/host, it is used as-is."""
        absolute = "http://example.com/somewhere/"
        with patch.object(Badge, "get_absolute_url", return_value=absolute):
            response = _shortcut(self.request, self.badge_ct.pk, self.badge.pk)
        self.assertIsInstance(response, HttpResponseRedirect)
        self.assertEqual(response.url, absolute)

    def test_shortcut__unknown_content_type_raises_404(self):
        """A content-type id with no matching ContentType raises Http404."""
        missing_ct_pk = ContentType.objects.order_by("-pk").first().pk + 1000
        with self.assertRaises(Http404):
            _shortcut(self.request, missing_ct_pk, self.badge.pk)

    def test_shortcut__content_type_without_model_raises_404(self):
        """A stale ContentType whose model class no longer exists raises Http404."""
        stale_ct = ContentType.objects.create(app_label="ghost_app", model="ghostmodel")
        self.assertIsNone(stale_ct.model_class())  # sanity: truly no backing model
        with self.assertRaises(Http404):
            _shortcut(self.request, stale_ct.pk, 1)

    def test_shortcut__missing_object_raises_404(self):
        """A valid content type but non-existent object id raises Http404."""
        missing_obj_pk = (Badge.objects.order_by("-pk").first().pk) + 1000
        with self.assertRaises(Http404):
            _shortcut(self.request, self.badge_ct.pk, missing_obj_pk)

    def test_shortcut__object_without_get_absolute_url_raises_404(self):
        """An object whose model has no get_absolute_url raises Http404.

        Group is a real model with instances but no get_absolute_url method.
        """
        group = Group.objects.create(name="No Absolute URL Group")
        group_ct = ContentType.objects.get_for_model(Group)
        with self.assertRaises(Http404):
            _shortcut(self.request, group_ct.pk, group.pk)
