"""Tests for schema-aware user deletion (issue #691).

Deleting a user on the *public* schema used to fail because Django's deletion
collector queried ``TENANT_APPS`` tables (e.g. ``quest_manager_questsubmission``)
that don't exist there.  ``CustomUserAdmin`` routes deletion through the
schema-aware collectors on the public schema, which skip absent tables, while
remaining a no-op on tenant schemas (where every table exists and cascades must
still work).

These tests drive the *actual* admin endpoints with ``TenantClient`` -- the
delete-confirmation page, single-object delete, and bulk ``delete_selected``
action -- so they exercise the registered ``CustomUserAdmin`` overrides and would
fail if it were unregistered or dispatched incorrectly.  The public-schema setup
mirrors ``tenant.tests.test_admin.PublicTenantTestAdminPublic``.
"""
from allauth.account.models import EmailAddress

from django.conf import settings
from django.contrib import admin as django_admin
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.urls import reverse

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import tenant_context
from model_bakery import baker

from quest_manager.models import Quest, QuestSubmission
from siteconfig.models import SiteConfig
from tenant.deletion import schema_aware_get_deleted_objects
from tenant.models import Tenant

User = get_user_model()


class SchemaAwareUserDeleteAdminPublicTest(TenantTestCase):
    """Public-schema user deletion through the Django admin (issue #691).

    On the public schema the ``TENANT_APPS`` tables are absent, so the default
    admin delete cascade raises ``relation "..." does not exist``.  These tests
    confirm ``CustomUserAdmin`` makes the confirmation page and the delete paths
    succeed there.
    """

    def setUp(self):
        # Build the public tenant + a superuser to drive the admin, mirroring
        # tenant.tests.test_admin.PublicTenantTestAdminPublic.
        self.public_tenant = Tenant(schema_name="public", name="public")
        with tenant_context(self.public_tenant):
            self.superuser = User.objects.create_superuser(
                username="admin",
                password=settings.TENANT_DEFAULT_ADMIN_PASSWORD,
            )
            # Bulk-create to skip the tenant post_save/pre_save signals (fast).
            Tenant.objects.bulk_create([self.public_tenant])
            self.public_tenant.refresh_from_db()
            self.public_tenant.domains.create(domain="localhost", is_primary=True)

            # The user we'll delete, plus an allauth EmailAddress -- the original
            # #691 failure surfaced first as a missing account_emailaddress table.
            self.target = User.objects.create_user("target", "target@example.com", "pw")
            EmailAddress.objects.create(
                user=self.target, email="target@example.com", verified=True, primary=True,
            )

        self.client = TenantClient(self.public_tenant)

    def test_get_deleted_objects__public_schema_confirmation_page_renders(self):
        """The delete-confirmation page renders on the public schema (it would
        raise ``relation ... does not exist`` without the schema-aware fix)."""
        # Everything runs inside the public-schema context so force_login's
        # last_login save (and the admin request) target the schema where the
        # superuser and target actually live.
        with tenant_context(self.public_tenant):
            self.client.force_login(self.superuser)
            url = reverse("admin:auth_user_delete", args=(self.target.pk,))
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "target")

    def test_delete_model__public_schema_single_user_delete_succeeds(self):
        """POSTing the delete-confirmation form deletes the user (and its
        EmailAddress) on the public schema via ``delete_model``."""
        with tenant_context(self.public_tenant):
            self.client.force_login(self.superuser)
            uid = self.target.pk
            url = reverse("admin:auth_user_delete", args=(uid,))
            response = self.client.post(url, {"post": "yes"})

            self.assertEqual(response.status_code, 302)
            self.assertFalse(User.objects.filter(pk=uid).exists())
            self.assertFalse(EmailAddress.objects.filter(user_id=uid).exists())

    def test_delete_queryset__public_schema_bulk_delete_succeeds(self):
        """The ``delete_selected`` admin action deletes users on the public
        schema via ``delete_queryset``."""
        with tenant_context(self.public_tenant):
            self.client.force_login(self.superuser)
            uid = self.target.pk
            changelist_url = reverse("admin:auth_user_changelist")
            action_data = {
                "action": "delete_selected",
                ACTION_CHECKBOX_NAME: [str(uid)],
            }
            # First POST renders the "are you sure?" confirmation page.
            confirm = self.client.post(changelist_url, action_data)
            self.assertEqual(confirm.status_code, 200)
            self.assertContains(confirm, "target")

            # Second POST (with post=yes) actually performs the delete.
            action_data["post"] = "yes"
            response = self.client.post(changelist_url, action_data)

            self.assertEqual(response.status_code, 302)
            self.assertFalse(User.objects.filter(pk=uid).exists())

    def test_get_deleted_objects__empty_object_list_returns_empty(self):
        """``schema_aware_get_deleted_objects`` handles an empty selection
        (the ``IndexError`` guard) without touching the database."""
        with tenant_context(self.public_tenant):
            to_delete, model_count, perms_needed, protected = schema_aware_get_deleted_objects(
                [], object(), None,
            )
        self.assertEqual(to_delete, [])
        self.assertEqual(model_count, {})
        self.assertEqual(perms_needed, set())
        self.assertEqual(protected, [])

    def test_get_deleted_objects__reports_perms_needed_without_delete_permission(self):
        """When the requesting user lacks delete permission on a collected
        (admin-registered) model, its verbose name is reported in
        ``perms_needed`` -- the ``has_delete_permission`` branch."""
        with tenant_context(self.public_tenant):
            staff = User.objects.create_user("staff_nodel", "s@e.com", "pw", is_staff=True)
            request = RequestFactory().get("/")
            request.user = staff  # staff, but no auth.delete_user permission

            _, _, perms_needed, _ = schema_aware_get_deleted_objects(
                [self.target], request, django_admin.site,
            )
        self.assertIn(User._meta.verbose_name, perms_needed)

    def test_get_deleted_objects__unresolvable_change_url_falls_back_to_plain_label(self):
        """When a collected object's admin change URL can't be reversed,
        ``format_callback`` falls back to a plain (unlinked) label -- the
        ``NoReverseMatch`` guard.  An ``AdminSite`` whose URLs aren't wired into
        the URLconf makes ``reverse()`` fail for its registered models."""
        with tenant_context(self.public_tenant):
            unwired = AdminSite(name="unwired_site")
            unwired.register(User)  # registered, but "unwired_site:..." isn't in urls
            request = RequestFactory().get("/")
            request.user = self.superuser

            to_delete, _, _, _ = schema_aware_get_deleted_objects(
                [self.target], request, unwired,
            )
        # Falls back to "User: target" with no <a href> link.
        self.assertIn("target", str(to_delete))
        self.assertNotIn("href", str(to_delete))


class SchemaAwareUserDeleteAdminTenantTest(TenantTestCase):
    """Regression guard: on a tenant schema every table exists, so
    ``CustomUserAdmin`` falls through to Django's default and the delete cascade
    still removes related tenant rows (e.g. QuestSubmission)."""

    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.superuser = User.objects.create_superuser(
            username="tenant_admin", email="ta@example.com", password="pw",
        )

    def test_delete_model__tenant_schema_still_cascades_to_submissions(self):
        """Deleting a user through the admin on a tenant schema cascades to the
        user's QuestSubmission rows exactly like the default admin."""
        student = baker.make(User)
        quest = baker.make(Quest)
        sub = baker.make(
            QuestSubmission, user=student, quest=quest,
            semester=SiteConfig.get().active_semester,
        )

        self.client.force_login(self.superuser)
        url = reverse("admin:auth_user_delete", args=(student.pk,))
        response = self.client.post(url, {"post": "yes"})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(pk=student.pk).exists())
        self.assertFalse(QuestSubmission.objects.filter(pk=sub.pk).exists())

    def test_delete_queryset__tenant_schema_bulk_delete_still_cascades(self):
        """The ``delete_selected`` bulk action on a tenant schema falls through
        to Django's default ``delete_queryset`` and still cascades to the
        selected users' QuestSubmission rows."""
        student = baker.make(User)
        quest = baker.make(Quest)
        sub = baker.make(
            QuestSubmission, user=student, quest=quest,
            semester=SiteConfig.get().active_semester,
        )

        self.client.force_login(self.superuser)
        changelist_url = reverse("admin:auth_user_changelist")
        action_data = {
            "action": "delete_selected",
            ACTION_CHECKBOX_NAME: [str(student.pk)],
        }
        confirm = self.client.post(changelist_url, action_data)
        self.assertEqual(confirm.status_code, 200)

        action_data["post"] = "yes"
        response = self.client.post(changelist_url, action_data)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(pk=student.pk).exists())
        self.assertFalse(QuestSubmission.objects.filter(pk=sub.pk).exists())
