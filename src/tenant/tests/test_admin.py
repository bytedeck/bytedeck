# With help from https://stackoverflow.com/questions/6498488/testing-admin-modeladmin-in-django
from unittest.mock import patch
from datetime import date

from django.conf import settings
from django.contrib import admin
from django.core import mail
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.admin.models import DELETION, LogEntry
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_permission_codename
from django.contrib.auth.models import Permission
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.test import RequestFactory, override_settings
# from django.core.exceptions import ValidationError
from django.urls import path, reverse
from django.utils import timezone


from allauth.socialaccount.models import SocialApp
from allauth.account.models import EmailAddress
from django_tenants.utils import tenant_context, schema_exists
from django_tenants.test.client import TenantClient

from hackerspace_online.celery import app
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from siteconfig.models import SiteConfig
from tenant.admin import TenantAdmin, TenantAdminForm
from tenant.models import Tenant

User = get_user_model()


def response_error_handler(request, exception=None):
    """ for raising error exceptions """
    return HttpResponse("Error handler content", status=403)


urlpatterns = [
    path("admin/", admin.site.urls)
]

handler403 = response_error_handler


def get_perm(Model, codename):
    """Return the permission object, for the Model"""
    ct = ContentType.objects.get_for_model(Model, for_concrete_model=False)
    return Permission.objects.get(content_type=ct, codename=codename)


class NonPublicTenantAdminTest(ByteDeckTenantTestCase):
    """For testing non-public tenants

    TenantTestCase comes with a `self.tenant`

    From docs: https://django-tenant-schemas.readthedocs.io/en/latest/test.html
        If you want a test to happen at any of the tenant’s domain, you can use the test case TenantTestCase.
        It will automatically create a tenant for you, set the connection’s schema to tenant’s schema and
        make it available at `self.tenant`

    """

    def test_save_model__non_public_schema_raises(self):
        """save_model raises when a tenant is created outside the public schema."""
        tenant_model_admin = TenantAdmin(model=Tenant, admin_site=AdminSite())

        # Can't create tenant outside the `public` schema. Current schema is `test`, so should throw exception
        with self.assertRaises(TypeError):  # Why is this a TypeError and not a ProgrammingError?
            tenant_model_admin.save_model(obj=Tenant, request=None, form=None, change=None)


class PublicTenantTestAdminPublic(ByteDeckTenantTestCase):
    """TenantTestCase comes with a tenant: tenant.test.com"""

    @classmethod
    def setUpTestData(cls):
        """Build the public schema with a superuser and an extra tenant, and seed owner emails (verified/unverified)."""
        # create the public schema
        cls.public_tenant = Tenant(schema_name="public", name="public")
        with tenant_context(cls.public_tenant):
            # create superuser account
            cls.superuser = User.objects.create_superuser(
                username="admin",
                password=settings.TENANT_DEFAULT_ADMIN_PASSWORD,
            )
            # Hack to create the public tenant without triggering the signals,
            # avoiding triggering django signals (post_save and pre_save)
            # can save us a lot of time.
            Tenant.objects.bulk_create([cls.public_tenant])
            cls.public_tenant.refresh_from_db()
            # create domain object manually, since we avoided triggering the signals
            cls.public_tenant.domains.create(domain="localhost", is_primary=True)

            # create a "real" (like superuser do in admin) tenant object for testing purpose
            cls.extra_tenant = Tenant(
                schema_name="extra",
                name="extra",
            )
            cls.extra_tenant.paid_until = date(2032, 1, 1)
            cls.extra_tenant.trial_end_date = date(2022, 1, 1)
            cls.extra_tenant.save()

        # update "owner" and add *unverified* email address
        with tenant_context(cls.tenant):
            config = SiteConfig.get()
            if config.deck_owner is not None and not config.deck_owner.email:
                # using different name/email to test fallback feature
                config.deck_owner.first_name = "Jane"
                config.deck_owner.last_name = "Doe"
                config.deck_owner.save()
                # add *unverified* email address (done via allauth)
                email_address = EmailAddress.objects.add_email(
                    request=None, user=config.deck_owner, email="jane@doe.com")
                email_address.set_as_primary()
                email_address.save()
            # the changelist displays CACHED owner fields; refresh them explicitly, as the
            # nightly deck_status_check task does in production (the changelist no longer
            # refreshes on page load -- #1729 PR 2)
            cls.tenant.update_cached_fields()

        # update "owner" and add missing email address
        with tenant_context(cls.extra_tenant):
            config = SiteConfig.get()
            if config.deck_owner is not None and not config.deck_owner.email:
                # using different name/email to test fallback feature
                config.deck_owner.first_name = "John"
                config.deck_owner.last_name = "Doe"
                config.deck_owner.save()
                # make email address verified and primary (done via allauth)
                email_address = EmailAddress.objects.add_email(
                    request=None, user=config.deck_owner, email="john@doe.com")
                email_address.set_as_primary()
                email_address.verified = True
                email_address.save()
            # see the matching comment above: cached fields refresh explicitly now
            cls.extra_tenant.update_cached_fields()

    def setUp(self):
        """Build a TenantAdmin instance and a public-tenant client for each test."""
        self.tenant_model_admin = TenantAdmin(model=Tenant, admin_site=AdminSite())
        self.client = TenantClient(self.public_tenant)

    def test_get_queryset__does_not_refresh_cached_fields(self):
        """Loading the changelist must NOT refresh each deck's cached fields anymore --
        that per-row refresh was an N+1 across every tenant schema on every page load;
        the nightly deck_status_check task is the canonical refresher now (#1729 PR 2)."""
        # anonymous request first: it moves the client's connection to the public
        # schema so force_login stores its session there (same dance as the
        # changelist-display tests in this class)
        self.client.get(reverse("admin:{}_{}_changelist".format("tenant", "tenant")))
        self.client.force_login(self.superuser)
        with patch("tenant.models.Tenant.update_cached_fields") as mock_update:
            response = self.client.get(reverse("admin:{}_{}_changelist".format("tenant", "tenant")))
        self.assertEqual(response.status_code, 200)
        mock_update.assert_not_called()

    def test_owner_full_name_text__shown_in_changelist(self):
        """
        Test whether content of custom column "owner_full_name_text" is present in admin list view or not.
        """
        # first case, access /admin/tenant/ page as anonymous user
        # should returns 302 (login required)
        response = self.client.get(reverse("admin:{}_{}_changelist".format("tenant", "tenant")))
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.superuser)

        # second case, access /admin/tenant/ page as authenticated superuser
        # should returns 200 (ok)
        response = self.client.get(reverse("admin:{}_{}_changelist".format("tenant", "tenant")))
        self.assertEqual(response.status_code, 200)
        # assert the content of custom column is present on changelist page
        self.assertContains(response, "John Doe")

    def test_owner_email_text__shown_in_changelist(self):
        """
        Test whether content of custom column "owner_email_text" is present in admin list view or not.
        """
        # first case, access /admin/tenant/ page as anonymous user
        # should returns 302 (login required)
        response = self.client.get(reverse("admin:{}_{}_changelist".format("tenant", "tenant")))
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.superuser)

        # second case, access /admin/tenant/ page as authenticated superuser
        # should returns 200 (ok)
        response = self.client.get(reverse("admin:{}_{}_changelist".format("tenant", "tenant")))
        self.assertEqual(response.status_code, 200)
        # assert the content of custom column is present on changelist page (both verified and unverified emails)
        self.assertContains(response, "john@doe.com")  # verified email
        self.assertContains(response, "jane@doe.com")  # unverified email

    def test_paid_until_text__shown_in_changelist(self):
        """
        Test whether content of htmlized column "paid_until_text" is present in admin list view or not.
        """
        # first case, access /admin/tenant/ page as anonymous user
        # should returns 302 (login required)
        response = self.client.get(reverse("admin:{}_{}_changelist".format("tenant", "tenant")))
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.superuser)

        # second case, access /admin/tenant/ page as authenticated superuser
        # should returns 200 (ok)
        response = self.client.get(reverse("admin:{}_{}_changelist".format("tenant", "tenant")))
        self.assertEqual(response.status_code, 200)
        # assert the content of custom column is present on changelist page
        self.assertContains(response, "<span data-date=\"2032-01-01\">Jan. 1, 2032</span>")

    def test_trial_end_date_text__shown_in_changelist(self):
        """
        Test whether content of htmlized column "trial_end_date" is present in admin list view or not.
        """
        # first case, access /admin/tenant/ page as anonymous user
        # should returns 302 (login required)
        response = self.client.get(reverse("admin:{}_{}_changelist".format("tenant", "tenant")))
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.superuser)

        # second case, access /admin/tenant/ page as authenticated superuser
        # should returns 200 (ok)
        response = self.client.get(reverse("admin:{}_{}_changelist".format("tenant", "tenant")))
        self.assertEqual(response.status_code, 200)
        # assert the content of custom column is present on changelist page
        self.assertContains(response, "<span data-date=\"2022-01-01\">Jan. 1, 2022</span>")

    def test_search__on_custom_fields(self):
        """
        Test whether content of custom fields is searchable in admin list view or not.
        """
        # first case, access /admin/tenant/ page as anonymous user
        # should returns 302 (login required)
        response = self.client.get(reverse("admin:{}_{}_changelist".format("tenant", "tenant")))
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.superuser)

        response = self.client.get(
            reverse("admin:{}_{}_changelist".format("tenant", "tenant")) + "?q="
        )

        # This code is commented out because it is failing test ran with initdb (or which ever one adding the library tenant)
        # Although, it works fine if ran isolated.

        # FIX:
        # despite filtering specifically for library schema does not seem to exist
        # hence not adding the +1 making an assertion error
        # This could possibly be revisited in a separate PR

        # # We need to check if library tenant exist
        # # Since library is created elsewhere it will fail only if full tests are ran
        # # See Issue https://github.com/bytedeck/bytedeck/issues/1590 for more details
        # lib = 1 if Tenant.objects.filter(schema_name='library').exists() else 0

        # # confirm the search by an empty query returned all (test, public and extra) objects
        # # check as library tenant is created somewhere else
        # self.assertContains(response, f"{str(3 + lib)} total")

        # ORIGINAL:
        # # confirm the search by an empty query returned all (test, public and extra) objects
        # self.assertContains(response, "3 total")

        response = self.client.get(
            reverse("admin:{}_{}_changelist".format("tenant", "tenant")) + "?q=John+Doe"
        )
        # confirm the search returned one object (by full name)
        self.assertContains(response, "1 result")

        response = self.client.get(
            reverse("admin:{}_{}_changelist".format("tenant", "tenant")) + "?q=doe.com"
        )
        # confirm the search returned two objects (by email address, both verified and unverified)
        self.assertContains(response, "2 result")

        response = self.client.get(
            reverse("admin:{}_{}_changelist".format("tenant", "tenant")) + "?q=Taylor+Swift"
        )
        # confirm the search returned zero objects (by full name)
        self.assertContains(response, "0 result")

    @patch("tenant.admin.messages.add_message")
    def test_enable_google_signin__without_public_config(self, mock_add_message):
        """
        Test where we attempt to enable google sign in but the public tenant has not yet configured
        the Google Provider Social App
        """

        request = RequestFactory().get('/')
        queryset = Tenant.objects.exclude(pk=self.public_tenant.pk)

        admin = User.objects.create_superuser(username="test_admin", email="admin@gmail.com", password="password")
        public_client = TenantClient(self.public_tenant)
        public_client.force_login(admin)

        self.tenant_model_admin.enable_google_signin(request=request, queryset=queryset)
        mock_add_message.assert_called()

        for tenant in queryset:
            with tenant_context(tenant):
                config = SiteConfig.get()

                self.assertIsNotNone(config)
                self.assertFalse(config.enable_google_signin)

    # Need to patch add_message since the messages framework thinks that it isn't in the INSTALLED_APPS
    # during tests..
    # Getting this error django.contrib.messages.api.MessageFailure:
    #           You cannot add messages without installing django.contrib.messages.middleware.MessageMiddleware
    @patch("tenant.admin.messages.add_message")
    def test_enable_and_disable_google_signin__via_admin(self, mock_add_message):
        """
        Test where we enable/disable google signin for clients via admin
        """

        request = RequestFactory().get('/')
        queryset = Tenant.objects.exclude(pk=self.public_tenant.pk)

        admin = User.objects.create_superuser(username="test_admin", email="admin@gmail.com", password="password")
        public_client = TenantClient(self.public_tenant)
        public_client.force_login(admin)

        for tenant in queryset:
            with tenant_context(tenant):
                config = SiteConfig.get()

                self.assertIsNotNone(config)
                self.assertFalse(config.enable_google_signin)

                with self.assertRaises(SocialApp.DoesNotExist):
                    SocialApp.objects.get(provider='google')

        with tenant_context(self.public_tenant):
            app = SocialApp.objects.create(
                provider='google',
                name='Test Google App',
                client_id='test_client_id',
                secret='test_secret',
            )
            app.sites.add(Site.objects.get_current())
            self.tenant_model_admin.enable_google_signin(request=request, queryset=queryset)

        # Google sign in should now be enabled
        for tenant in queryset:
            with tenant_context(tenant):
                config = SiteConfig.get()

                self.assertIsNotNone(config)
                self.assertTrue(config.enable_google_signin)

                sc = SocialApp.objects.get(provider='google')
                self.assertIsNotNone(sc)

        # Disable google sign in
        queryset = Tenant.objects.exclude(pk=self.public_tenant.pk)
        with tenant_context(self.public_tenant):
            self.tenant_model_admin.disable_google_signin(request=request, queryset=queryset)

        # Everything should now be disabled
        for tenant in queryset:
            with tenant_context(tenant):
                config = SiteConfig.get()

                self.assertIsNotNone(config)
                self.assertFalse(config.enable_google_signin)

        mock_add_message.assert_called()

    def test_save_model__public_tenant_creates_schema(self):
        """save_model on the public tenant creates a new tenant with a sanitized schema name."""
        with tenant_context(self.public_tenant):
            non_public_tenant = Tenant(
                name="Non-Public",  # Not a valid name, but not validated in this test
            )

            # public tenant should be able to create new tenant/schemas
            self.tenant_model_admin.save_model(obj=non_public_tenant, request=None, form=None, change=None)
            self.assertIsInstance(non_public_tenant, Tenant)
            # schema names should be all lower case and dashes converted to underscores
            self.assertEqual(non_public_tenant.schema_name, "non_public")

        # TODO: Not working, can't figure out why?
        # When try to use client.get() the context switches back to the public tenant
        # WHY!?!?

        # make sure we can access and sign-in to the new tenant
        # with tenant_context(non_public_tenant):
        #     from django.db import connection
        #     from django.contrib.auth import get_user_model
        #     from django.urls import reverse

        #     client = TenantClient(non_public_tenant)
        #     connection.set_tenant(non_public_tenant)
        #     print(connection.schema_name)  # non_public
        #     response = client.get(reverse('account_login'))
        #     print(connection.schema_name)  # public

        #     # self.assertEqual(response.status_code, 200)
        #     print(connection.schema_name)

        #     test_teacher = get_user_model().objects.create_user('test_teacher', password="password", is_staff=True)
        #     client = TenantClient(non_public_tenant)
        #     client.force_login(test_teacher)
        #     response = client.get(reverse('quests:quests'))
        #     self.assertEqual(response.status_code, 200)

    # FIXME:
    # def test_public_tenant_admin_save_new_tenant_with_bad_names(self):
    #
    #     with tenant_context(self.public_tenant):
    #         # tenant names with spaces should be rejected:
    #         with self.assertRaises(ValidationError):
    #             non_public_tenant_bad_name = Tenant(name="Non Public")
    #             self.tenant_model_admin.save_model(obj=non_public_tenant_bad_name, request=None, form=None, change=None)
    #         # also other alpha-numeric characters except dashes and underscores
    #         with self.assertRaises(ValidationError):
    #             non_public_tenant_bad_name = Tenant(name="Non*Public")
    #             self.tenant_model_admin.save_model(obj=non_public_tenant_bad_name, request=None, form=None, change=None)


class TenantAdminFormTest(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Build baseline valid form data reused across the form validation tests."""
        cls.form_data = {
            'name': 'test',  # This is the name of the already existing test tenant
            # 'owner_full_name': None,
            # 'owner_email': None,
            'max_active_users': 50,
            'max_quests': 100,
            # 'paid_until': None,
            'trial_end_date': timezone.now()
        }

    def test_clean__public_tenant_not_editable(self):
        """The reserved 'public' name is rejected by the admin form."""
        self.form_data["name"] = "public"
        form = TenantAdminForm(self.form_data)
        self.assertFalse(form.is_valid())

    def test_clean__new_non_public_tenant_valid(self):
        """A new non-public tenant name validates on the admin form."""
        self.form_data["name"] = "non-public"
        form = TenantAdminForm(self.form_data)
        self.assertTrue(form.is_valid())

    def test_clean__existing_non_public_tenant_valid(self):
        """ test tenant already exists as a part of the TenantTestCase """
        form = TenantAdminForm(self.form_data)
        form.instance = Tenant.get()  # test tenant with schema 'test'
        self.assertTrue(form.is_valid())

    def test_clean__billing_dates_can_be_blanked(self):
        """An admin can clear both trial_end_date and paid_until, putting the deck in
        the comped/unmanaged state that is never suspended (fails without blank=True
        on trial_end_date)."""
        self.form_data['trial_end_date'] = ''
        self.form_data['paid_until'] = ''
        form = TenantAdminForm(self.form_data)
        form.instance = Tenant.get()
        self.assertTrue(form.is_valid())
        self.assertIsNone(form.cleaned_data['trial_end_date'])

    def test_clean__cant_change_existing_name(self):
        """Renaming an existing tenant via the admin form is rejected."""
        # test tenant already exists and is connected in TenantTestCase
        self.form_data["name"] = "nottest"
        form = TenantAdminForm(self.form_data)
        form.instance = Tenant.get()  # test tenant with schema 'test'
        self.assertFalse(form.is_valid())

    def test_clean__cant_create_if_schema_still_exists(self):
        """
        Creating new tenant object with a name of existing schema, should fail with form (validation) error
        """
        # delete test tenant object without dropping schema
        Tenant.get().delete(force_drop=False)
        # trying to create new tenant, with name of existing schema
        form = TenantAdminForm(self.form_data)
        self.assertFalse(form.is_valid())


class TenantAdminViewPermissionsTest(ByteDeckTenantTestCase):
    """Tests for TenandAdmin views permissions."""

    @classmethod
    def setUpTestData(cls):
        """Build the public schema plus view/add/change/delete staff users with matching permissions and an extra tenant."""
        # create the public schema
        cls.public_tenant = Tenant(schema_name="public", name="public")
        with tenant_context(cls.public_tenant):
            cls.viewuser = User.objects.create_user(
                username="viewuser",
                password="sekret",
                is_staff=True,
            )
            cls.adduser = User.objects.create_user(
                username="adduser",
                password="sekret",
                is_staff=True,
            )
            cls.changeuser = User.objects.create_user(
                username="changeuser",
                password="sekret",
                is_staff=True,
            )
            cls.deleteuser = User.objects.create_user(
                username="deleteuser",
                password="sekret",
                is_staff=True,
            )
            # Setup permissions, for our users who can add, change, and delete.
            opts = Tenant._meta

            # User who can view Tenants
            cls.viewuser.user_permissions.add(
                get_perm(Tenant, get_permission_codename("view", opts))
            )
            # User who can add Tenants
            cls.adduser.user_permissions.add(
                get_perm(Tenant, get_permission_codename("add", opts))
            )
            # User who can change Tenants
            cls.changeuser.user_permissions.add(
                get_perm(Tenant, get_permission_codename("change", opts))
            )
            # User who can delete Tenants
            cls.deleteuser.user_permissions.add(
                get_perm(Tenant, get_permission_codename("delete", opts))
            )

            # Hack to create the public tenant without triggering the signals,
            # avoiding triggering django signals (post_save and pre_save)
            # can save us a lot of time.
            Tenant.objects.bulk_create([cls.public_tenant])
            cls.public_tenant.refresh_from_db()
            # create domain object manually, since we avoided triggering the signals
            cls.public_tenant.domains.create(domain="localhost", is_primary=True)

            # create a "real" (like superuser do in admin) tenant object for testing purpose
            cls.extra_tenant = Tenant(
                schema_name="extra",
                name="extra",
            )
            cls.extra_tenant.save()

        # We need to check if library tenant exist
        # Since library is created elsewhere it will fail only if full tests are ran
        # See Issue https://github.com/bytedeck/bytedeck/issues/1590 for more details
        cls.lib = 1 if Tenant.objects.filter(schema_name='library').exists() else 0

    def setUp(self):
        """Build a public-tenant client for each test."""
        self.client = TenantClient(self.public_tenant)

    # NOTE: this test's name sorts first in the class on purpose. It opens with an
    # anonymous request through the public TenantClient, which leaves the DB
    # connection on the public schema so the sibling tests' force_login() (their
    # first DB touch) resolves the public-schema users. Renaming it to sort after a
    # force_login-first sibling reintroduces "Save with update_fields did not affect
    # any rows" on update_last_login.
    @override_settings(ROOT_URLCONF=__name__)
    def test_delete_view__enforces_permissions(self):
        """
        Delete view should restrict access and actually delete items.

        Django comes with a built-in permissions system. It provides a way to assign permissions to
        specific users and groups of users, and it’s used by the Django admin site.

        The Django admin site uses permissions as follows:

        * Access to view objects is limited to users with the “view” or “change” permission for that type of object.
        * Access to view the “add” form and add an object is limited to users with the “add” permission for
          that type of object.
        * Access to view the change list, view the “change” form and change an object is limited to users
          with the “change” permission for that type of object.
        * Access to delete an object is limited to users with the “delete” permission for that type of object.

        Note: A superuser is a user type in Django that has every permission in the system.
        Whether custom permissions or Django-created permissions, superusers have access to every permission.
        A staff user is just like any other user in your system BUT with the added advantage of being
        able to access the Django Admin interface.

        """
        delete_dict = {"post": "yes", "confirmation": "owner/extra"}
        delete_url = reverse("admin:tenant_tenant_delete", args=(self.extra_tenant.pk,))

        # first case, access /admin/tenant/<pk>/delete/ page as anonymous user
        # should returns 302 (login required)
        response = self.client.get(delete_url)
        self.assertEqual(response.status_code, 302)

        # second case, add user should not be able to delete tenants
        # should returns 403 (no permission)
        self.client.force_login(self.adduser)
        response = self.client.get(delete_url)
        self.assertEqual(response.status_code, 403)
        post = self.client.post(delete_url, delete_dict)
        self.assertEqual(post.status_code, 403)
        self.assertEqual(Tenant.objects.count(), 3 + self.lib)  # no changes
        self.client.logout()

        # third case, view user should not be able to delete tenants
        # should returns 403 (no permission)
        self.client.force_login(self.viewuser)
        response = self.client.get(delete_url)
        self.assertEqual(response.status_code, 403)
        post = self.client.post(delete_url, delete_dict)
        self.assertEqual(post.status_code, 403)
        self.assertEqual(Tenant.objects.count(), 3 + self.lib)  # no changes
        self.client.logout()

        # fourth case, delete user can delete, but using incorrect confirmation keyword/phrase
        # should returns 200 (same page, but with errors)
        self.client.force_login(self.deleteuser)
        response = self.client.get(delete_url)
        self.assertEqual(response.status_code, 200)
        post = self.client.post(delete_url, {"post": "yes", "confirmation": "stranger/something"})
        self.assertEqual(post.status_code, 200)
        self.assertEqual(Tenant.objects.count(), 3 + self.lib)  # no changes
        self.assertContains(
            post, "The confirmation does not match the keyword"
        )

        # fifth case, delete user can delete, using correct confirmation keyword/phrase
        # should returns 302 (redirect to admin homepage)
        response = self.client.get(delete_url)
        self.assertContains(response, f"tenant/tenant/{self.extra_tenant.pk}/")
        self.assertContains(response, "Summary")
        self.assertContains(response, "Tenants: 1")
        post = self.client.post(delete_url, delete_dict)
        self.assertRedirects(post, reverse("admin:index"))
        self.assertEqual(Tenant.objects.count(), 2 + self.lib)
        tenant_ct = ContentType.objects.get_for_model(Tenant)
        logged = LogEntry.objects.get(content_type=tenant_ct, action_flag=DELETION)
        self.assertEqual(logged.object_id, str(self.extra_tenant.pk))

    def test_delete_view__uses_delete_model(self):
        """
        The delete view uses ModelAdmin.delete_model() method, that delete items, but leaves schemas in database.
        """
        delete_dict = {"post": "yes", "confirmation": "owner/extra"}
        delete_url = reverse("admin:tenant_tenant_delete", args=(self.extra_tenant.pk,))

        # assert number of tenants, should be three objects (test, public and extra)
        self.assertEqual(Tenant.objects.count(), 3 + self.lib)

        self.client.force_login(self.deleteuser)
        post = self.client.post(delete_url, delete_dict)
        self.assertRedirects(post, reverse("admin:index"))
        # tenant object was removed (extra tenant is gone)
        self.assertEqual(Tenant.objects.count(), 2 + self.lib)
        # ...but schema still in database
        self.assertTrue(schema_exists("extra"))

    def test_delete_view__nonexistent_obj(self):
        """Deleting a nonexistent tenant redirects to the admin index with a not-found message."""
        self.client.force_login(self.deleteuser)
        url = reverse("admin:tenant_tenant_delete", args=("nonexistent",))
        response = self.client.get(url, follow=True)
        self.assertRedirects(response, reverse("admin:index"))
        self.assertEqual(
            [m.message for m in response.context["messages"]],
            ["tenant with ID “nonexistent” doesn’t exist. Perhaps it was deleted?"],
        )


class TenantAdminActionsTest(ByteDeckTenantTestCase):
    """TenantAdmin class is shipped with various admin actions"""

    @classmethod
    def setUpTestData(cls):
        """Build the public schema, a superuser, an extra tenant, and seed owner emails (verified/unverified)."""
        # create the public schema
        cls.public_tenant = Tenant(schema_name="public", name="public")
        with tenant_context(cls.public_tenant):
            # create superuser account
            cls.superuser = User.objects.create_superuser(
                username="admin",
                password=settings.TENANT_DEFAULT_ADMIN_PASSWORD,
            )
            # Hack to create the public tenant without triggering the signals,
            # avoiding triggering django signals (post_save and pre_save)
            # can save us a lot of time.
            Tenant.objects.bulk_create([cls.public_tenant])
            cls.public_tenant.refresh_from_db()
            # create domain object manually, since we avoided triggering the signals
            cls.public_tenant.domains.create(domain="localhost", is_primary=True)

            # create a "real" (like superuser do in admin) tenant object for testing purpose
            cls.extra_tenant = Tenant(
                schema_name="extra",
                name="extra",
            )
            cls.extra_tenant.save()

        # update "owner" and add *unverified* email address
        with tenant_context(cls.tenant):
            config = SiteConfig.get()
            if config.deck_owner is not None and not config.deck_owner.email:
                # using different name/email to test fallback feature
                config.deck_owner.first_name = "Jane"
                config.deck_owner.last_name = "Doe"
                config.deck_owner.save()
                # add *unverified* email address (done via allauth)
                email_address = EmailAddress.objects.add_email(
                    request=None, user=config.deck_owner, email="jane@doe.com")
                email_address.set_as_primary()
                email_address.save()

        # update "owner" and add *verified* email address
        with tenant_context(cls.extra_tenant):
            config = SiteConfig.get()
            if config.deck_owner is not None and not config.deck_owner.email:
                # using different name/email to test fallback feature
                config.deck_owner.first_name = "John"
                config.deck_owner.last_name = "Doe"
                config.deck_owner.save()
                # make email address verified and primary (done via allauth)
                email_address = EmailAddress.objects.add_email(
                    request=None, user=config.deck_owner, email="john@doe.com")
                email_address.set_as_primary()
                email_address.verified = True
                email_address.save()

    def setUp(self):
        """Build a public-tenant client and force Celery tasks to run eagerly."""
        self.client = TenantClient(self.public_tenant)

        self.old_celery_always_eager = app.conf.task_always_eager
        app.conf.task_always_eager = True

    def tearDown(self):
        """Restore the original Celery eager-execution setting."""
        app.conf.task_always_eager = self.old_celery_always_eager

    def test_message_unverified_action__emails_verified_and_unverified_owners(self):
        """
        The message_unverified action on public tenant sends emails to selected tenant "owners",
        using both *verified* and *unverified* email addresses.
        """
        # first case, access /admin/tenant/ page as anonymous user
        # should returns 302 (login required)
        response = self.client.get(reverse("admin:{}_{}_changelist".format("tenant", "tenant")))
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.superuser)

        # second case, access /admin/tenant/ page as authenticated superuser
        # should returns 200 (ok)
        response = self.client.get(reverse("admin:{}_{}_changelist".format("tenant", "tenant")))
        self.assertEqual(response.status_code, 200)

        # third case, select tenants and execute "message_unverified" action
        # should returns 200 (intermediate page)
        action_data = {
            # trying to send message on multiple tenants (public, test and extra),
            # one is *verified* (extra), other not (tenant)
            ACTION_CHECKBOX_NAME: [self.public_tenant.pk, self.tenant.pk, self.extra_tenant.pk],
            "action": "message_unverified",
            "index": 0,
        }
        response = self.client.post(
            reverse("admin:{}_{}_changelist".format("tenant", "tenant")), action_data
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response, TemplateResponse)
        self.assertContains(
            response, "Send email to multiple users"
        )
        self.assertContains(response, "<h1>Write your message here</h1>")
        # two objects were selected (tenant and extra)
        self.assertContains(response, ACTION_CHECKBOX_NAME, count=2)

        # fourth case, complete "intermediate" page/form
        # should returns 302 (redirect back to "changelist" page)
        compose_confirmation_data = {
            ACTION_CHECKBOX_NAME: [self.public_tenant.pk, self.tenant.pk, self.extra_tenant.pk],
            "action": "message_unverified",
            # submit intermediate form (subject and message)
            "subject": "Greetings from a TenantAdmin action",
            "message": "Lorem ipsum dolor sit amet..",
            # click "confirmation" button
            "post": "yes",  # confirm form
        }
        response = self.client.post(
            reverse("admin:{}_{}_changelist".format("tenant", "tenant")), compose_confirmation_data
        )
        self.assertEqual(response.status_code, 302)
        # check mailbox after submitting form
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Greetings from a TenantAdmin action")
        # expecting to see recipients in BCC list
        self.assertEqual(mail.outbox[0].to, [settings.DEFAULT_FROM_EMAIL])
        # two objects were selected (tenant and extra), and both are valid recipient
        self.assertIn(
            f"{self.tenant.name} - Jane Doe <jane@doe.com>", mail.outbox[0].bcc,
        )
        self.assertIn(
            f"{self.extra_tenant.name} - John Doe <john@doe.com>", mail.outbox[0].bcc,
        )

        # fifth case, without any *verified* recipiets
        # should returns 200 (intermediate page)
        action_data = {
            # trying to send message on multiple tenants (public and tenant),
            # but without any *verified* recipients
            ACTION_CHECKBOX_NAME: [self.public_tenant.pk, self.tenant.pk],
            "action": "message_unverified",
            "index": 0,
        }
        response = self.client.post(
            reverse("admin:{}_{}_changelist".format("tenant", "tenant")), action_data
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response, TemplateResponse)
        self.assertContains(
            response, "Send email to multiple users"
        )
        self.assertContains(response, "<h1>Write your message here</h1>")
        # one *unverified* object was selected (tenant)
        self.assertContains(response, ACTION_CHECKBOX_NAME, count=1)

    def test_message_verified_action__emails_verified_owners_only(self):
        """
        The message_verified action on public tenant sends emails to selected tenant "owners",
        using *verified* only email addresses.
        """
        # first case, access /admin/tenant/ page as anonymous user
        # should returns 302 (login required)
        response = self.client.get(reverse("admin:{}_{}_changelist".format("tenant", "tenant")))
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.superuser)

        # second case, access /admin/tenant/ page as authenticated superuser
        # should returns 200 (ok)
        response = self.client.get(reverse("admin:{}_{}_changelist".format("tenant", "tenant")))
        self.assertEqual(response.status_code, 200)

        # third case, select tenants and execute "send_email_message" action
        # should returns 200 (intermediate page)
        action_data = {
            # trying to send message on multiple tenants (public, test and extra),
            # but only one is legit (extra)
            ACTION_CHECKBOX_NAME: [self.public_tenant.pk, self.tenant.pk, self.extra_tenant.pk],
            "action": "message_verified",
            "index": 0,
        }
        response = self.client.post(
            reverse("admin:{}_{}_changelist".format("tenant", "tenant")), action_data
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response, TemplateResponse)
        self.assertContains(
            response, "Send email to multiple users"
        )
        self.assertContains(response, "<h1>Write your message here</h1>")
        # two objects were selected (test and extra)
        self.assertContains(response, ACTION_CHECKBOX_NAME, count=2)

        # fourth case, complete "intermediate" page/form
        # should returns 302 (redirect back to "changelist" page)
        compose_confirmation_data = {
            ACTION_CHECKBOX_NAME: [self.public_tenant.pk, self.tenant.pk, self.extra_tenant.pk],
            "action": "message_verified",
            # submit intermediate form (subject and message)
            "subject": "Greetings from a TenantAdmin action",
            "message": "Lorem ipsum dolor sit amet..",
            # click "confirmation" button
            "post": "yes",  # confirm form
        }
        response = self.client.post(
            reverse("admin:{}_{}_changelist".format("tenant", "tenant")), compose_confirmation_data
        )
        self.assertEqual(response.status_code, 302)
        # check mailbox after submitting form
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Greetings from a TenantAdmin action")
        # expecting to see recipients in BCC list
        self.assertEqual(mail.outbox[0].to, [settings.DEFAULT_FROM_EMAIL])
        # two objects were selected (test and extra), but only one valid recipient
        self.assertEqual(mail.outbox[0].bcc, [
            f"{self.extra_tenant.name} - John Doe <john@doe.com>",
        ])

        # fifth case, no recipients found
        # should returns 302 (redirect back to "changelist" page) and show error message
        action_data = {
            # trying to send message on multiple tenants (public and test),
            # but without any valid recipients
            ACTION_CHECKBOX_NAME: [self.public_tenant.pk, self.tenant.pk],
            "action": "message_verified",
            "index": 0,
        }
        url = reverse("admin:{}_{}_changelist".format("tenant", "tenant"))
        response = self.client.post(url, action_data)
        self.assertRedirects(response, url, fetch_redirect_response=False)
        response = self.client.get(response.url)
        self.assertContains(response, "No recipients found.")
