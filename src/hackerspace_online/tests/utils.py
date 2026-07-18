from django.contrib import messages
from django.conf import settings
from django.core import serializers
from django.core.cache import cache
from django.db import connection
from django.shortcuts import reverse

from django_tenants.test.cases import TenantTestCase
from django_tenants.utils import get_tenant_model, get_tenant_domain_model

from model_bakery import baker

import json
import re
import warnings


class ByteDeckTenantTestCase(TenantTestCase):
    """A TenantTestCase that reuses one test schema across classes and runs ``setUpTestData``.

    Two problems with django-tenants' ``TenantTestCase`` are fixed here:

    1. **``setUpTestData`` never runs.** ``TenantTestCase.setUpClass`` doesn't call
       ``super().setUpClass()``, so Django ``TestCase``'s class-level setup — the
       class-wide atomic transaction and the ``setUpTestData`` hook — is skipped
       entirely. A ``setUpTestData`` defined on a plain ``TenantTestCase`` subclass
       is silently never called.

    2. **The schema is rebuilt for every test class.** ``TenantTestCase`` creates a
       fresh schema, replays *all* tenant-app migrations, and re-seeds the tenant's
       initial data in ``setUpClass``, then drops it in ``tearDownClass`` — once per
       test class. With ~160 tenant test classes that migrate/seed cost dominates
       the suite's runtime.

    This class instead creates the ``test`` schema **once per process** (the first
    test class to run migrates and seeds it, committed outside any transaction so it
    persists) and every later class reuses it, mirroring django-tenants'
    ``FastTenantTestCase``. It then runs Django's ``TestCase.setUpClass`` so
    ``setUpTestData`` executes once per class inside a class-wide atomic that is
    rolled back in ``tearDownClass``.

    **Isolation is preserved.** Each test still runs inside a savepoint that is
    rolled back afterwards, and each class's ``setUpTestData`` is rolled back when
    the class finishes, so every class starts from the same pristine seed data and
    no ``setUpTestData`` or per-test writes leak between classes. Since Django 3.2
    each test also gets a fresh deep copy of objects assigned in ``setUpTestData``.
    The one observable difference from per-class schema rebuilds is that
    auto-increment sequences are **not** reset between classes, so a test must not
    assert a specific absolute primary-key value for objects it creates.

    Caveats:

    * Any state committed outside the test/class transactions *would* leak, so tests
      must not commit (no ``TransactionTestCase`` semantics here) — the suite has no
      such tenant tests.
    * Under ``--keepdb`` the ``test`` schema survives between runs and is reused
      as-is; drop the test database after changing models/migrations or the tenant
      seed so it is rebuilt. A normal (non-``--keepdb``) run always starts fresh.

    Use this as the base class for all tenant tests. Fixtures that no test mutates
    beyond its own rolled-back transaction belong in ``setUpTestData``;
    ``self.client = TenantClient(self.tenant)`` and ``force_login`` calls stay in
    ``setUp``.

    **Opting out of reuse.** A few kinds of test are incompatible with a shared,
    long-lived schema and must set ``reuse_schema = False`` to get the original
    per-class fresh-schema behavior (create + migrate + seed + drop, in a private
    schema that never collides with the shared one):

    * Tests that create *additional* tenants or exercise tenant/Site/domain
      machinery — the persistent shared tenant would be enumerated by cross-tenant
      signals and break them (and such tests build their own schemas anyway, so
      they gain little from reuse).
    * Tests that ``freeze_time`` at the class level *and* depend on the tenant's
      seed data being created at that frozen time (the shared seed is created once,
      at whatever the first class's clock was).
    """

    # Set to False on a subclass to force the stock per-class fresh schema instead
    # of the shared, reused one. See the class docstring for when that's required.
    reuse_schema = True

    @classmethod
    def get_test_schema_name(cls):
        """Shared ``test`` schema when reusing; a private per-class schema otherwise."""
        if cls.reuse_schema:
            return super().get_test_schema_name()
        # A unique, valid Postgres schema name per opt-out class so its fresh schema
        # never collides with the shared "test" schema or another opt-out class.
        name = 'test_' + re.sub(r'[^a-z0-9_]', '', cls.__name__.lower())
        return name[:63]

    @classmethod
    def get_test_tenant_domain(cls):
        """Shared domain when reusing; a unique per-class domain for opt-out classes."""
        if cls.reuse_schema:
            return super().get_test_tenant_domain()
        # Domain is globally unique; keep opt-out classes from colliding with the
        # persistent shared tenant's domain (which is never dropped).
        return f'{cls.get_test_schema_name()}.test.com'

    @classmethod
    def setUpClass(cls):
        """Reuse (or first create) the test tenant, then run Django's class setup."""
        cls.add_allowed_test_domain()

        tenant_model = get_tenant_model()
        schema_name = cls.get_test_schema_name()
        # Opt-out classes always build fresh (their private schema won't pre-exist);
        # reuse classes look for the shared schema a previous class already built.
        tenant = tenant_model.objects.filter(schema_name=schema_name).first() if cls.reuse_schema else None

        if tenant is None:
            # First test class to need this schema: create, migrate, and seed it.
            # This runs before Django's class-wide atomic is entered (below), so for
            # reuse classes it is committed and persists for every later class; for
            # opt-out classes it is dropped again in tearDownClass.
            cls.sync_shared()
            # Tenant.name is unique. The shared tenant keeps the stock empty name
            # ('') for parity with django-tenants' TenantTestCase, but an opt-out
            # class's fresh tenant co-exists with that persistent shared tenant, so
            # it must take a distinct (per-schema) name to avoid a unique collision.
            tenant = tenant_model(schema_name=schema_name, name='' if cls.reuse_schema else schema_name)
            cls.setup_tenant(tenant)
            tenant.save(verbosity=cls.get_verbosity())

            domain = get_tenant_domain_model()(tenant=tenant, domain=cls.get_test_tenant_domain())
            cls.setup_domain(domain)
            domain.save()
            cls.domain = domain
        else:
            # A previous test class already built the shared schema; reuse it.
            cls.domain = get_tenant_domain_model().objects.filter(tenant=tenant).first()

        cls.tenant = tenant
        connection.set_tenant(cls.tenant)

        # Clear the process-global cache before setUpTestData reads it. The cache
        # (LocMemCache) is keyed by schema name, and the shared "test" schema keeps
        # the same key across every class. Without a rebuild between classes there
        # is nothing to invalidate a stale entry, so a SiteConfig cached by an
        # earlier class — whose active_semester was rolled back with that class —
        # would otherwise be served here and produce dangling foreign keys. See
        # _fixture_setup for the per-test clear.
        cache.clear()

        # Standard Django TestCase class setup: enters the class-wide atomic block
        # and calls setUpTestData with the tenant schema active. super(TenantTestCase,
        # cls) skips django-tenants' override (which would rebuild the schema).
        super(TenantTestCase, cls).setUpClass()

    @classmethod
    def _fixture_setup(cls):
        """Start the per-test savepoint, then clear the schema-keyed cache.

        Each test rolls back to a savepoint afterwards, but the process-global
        cache is not transactional: a test that caches a SiteConfig referencing an
        object it created (e.g. a new active Semester) would leave that reference
        cached after its rows are rolled back, so a later test in the same reused
        schema would read a SiteConfig pointing at a row that no longer exists.
        Clearing here — for every test, regardless of setUp overrides — guarantees
        each test reads cache-backed singletons fresh from its own pristine DB
        state. (Runs in addition to any cache.clear() a test's own setUp does.)

        A ``classmethod`` since Django 5.1 made ``TestCase._fixture_setup`` one;
        it is still invoked once per test method (it enters the per-test savepoint
        that ``_fixture_teardown`` rolls back), so the cache is still cleared per
        test — only the binding changed from instance to class.
        """
        super()._fixture_setup()
        cache.clear()

    @classmethod
    def tearDownClass(cls):
        """Roll back this class's setUpTestData; keep the shared schema, drop a private one."""
        # Rolls back the class-wide atomic block (everything created in
        # setUpTestData) so the next class starts from the pristine seed data.
        super(TenantTestCase, cls).tearDownClass()

        connection.set_schema_to_public()

        if cls.reuse_schema:
            # The shared ``test`` schema, its Tenant row, and its domain are
            # deliberately NOT dropped so the next test class reuses them. Django
            # destroys the whole test database at the end of the run (unless
            # --keepdb), which removes the schema. The allowed test domain is left
            # in ALLOWED_HOSTS because the tenant it points at still exists.
            return

        # Opt-out class: drop its private schema exactly like the stock TenantTestCase.
        cls.domain.delete()
        cls.tenant.delete(force_drop=True)
        cls.remove_allowed_test_domain()


def generate_form_data(model=None, model_form=None, **kwargs):
    """
        This generates valid form data that can be used for post requests. Values will default to form/model default.
        kwargs values are equal to any name in the meta fields

        This has the same limitations as baker, so anything that baker.prepare cant make this func cant make either.
        (m2m fields, null=True will make empty values, ...)
        Things like special validation should be manually set in kwargs.

        Note: things like Foreign keys, OnetoOne fields will persist after creation
        https://model-bakery.readthedocs.io/en/latest/basic_usage.html

        usage (See hackerspace_online.tests.test_utils.py for additional examples):


        EXAMPLE 1 (no validators + using forms):
        >>> form_data = generate_form_data(model_form=FormClass, name="RANDOM NAME")

        >>> form = FormClass(form_data)
        >>> form.is_valid()
        True

        >>> response = self.client.post(reverse('form-create'), data=form_data)
        >>> response.status_code
        200

        EXAMPLE 2 (with validators + using models):
        >>> form_data = self.generate_form_data(
                model=ModelClass,
                url="/url-here/",  # since urls need opening + closing slashes, you would need to manually set this
            )

        >>> form = FormClass(form_data)
        >>> form.is_valid()
        True

        >>> response = self.client.post(reverse('form-create'), data=form_data)
        >>> response.status_code
        200
    """
    if model is None and model_form is None:
        raise ValueError('one of these arguments is required: model, model_form')

    fields = []
    exclude = []
    if model_form is not None:  # should default to model_form since it has more data specifically fields + exclude
        model = model_form._meta.model  # since baker isn't compatible with forms create instance using model instead

        fields = model_form._meta.fields or []
        exclude = model_form._meta.exclude or []

    data = baker.prepare(model, **kwargs,)

    json_data = serializers.serialize('json', [data])
    json_data = json.loads(json_data)[0]["fields"]
    json_data = {key: item if item is not None else "" for key, item in json_data.items()}  # replaces None with empty string

    # keep only the fields and exclude exclude
    [json_data.pop(field_name) for field_name in json_data.copy() if fields and field_name not in fields]
    [json_data.pop(field_name) for field_name in exclude]

    return json_data


def model_to_form_data(model, model_form):
    """
        This generates valid form data that can be used for post requests.
        Values are dependant on the model instance passed through the model variable.

        The only limitations it should have are whatever serializers.serialize() can't serialize into json

        EXAMPLE:
        >>> instance = Model(var1=1, var2=2, ...)
        >>> form_data = model_to_form_data(instance, ModelForm)
        >>> form_data
        { "var1": 1, "var2": 2 }

        >>> form = ModelForm(form)
        >>> form.is_valid()
        True
    """
    fields = model_form._meta.fields or [field.name for field in model._meta.fields]
    exclude = model_form._meta.exclude or []

    json_data = serializers.serialize('json', [model])
    json_data = json.loads(json_data)[0]["fields"]

    json_data = {key: item if item is not None else "" for key, item in json_data.items()}
    [json_data.pop(field_name) for field_name in json_data.copy() if fields and field_name not in fields]
    [json_data.pop(field_name) for field_name in exclude]

    return json_data


def generate_formset_data(model_formset, prefix='form', quantity=1, **kwargs):
    """
        This generates valid form data that can be used for post requests. This has the same limitations as generate_form_data()
        Values will default to form/model default.
        kwargs values are equal to any name in the meta fields

        EXAMPLE 1:
        >>> formset_data = generate_formset_data(ModelFormset, quantity=5)
        >>> formset = ModelFormset(formset_data)
        >>> formset.is_valid()
        True

        EXAMPLE 2 (using kwargs):
        >>> formset_data = generate_formset(ModelFormset, quantity=3, name=lambda: random.choice(['name1', 'name2', 'name3']))
        >>> formset = ModelFormset(formset_data)
        >>> formset.is_valid()
        True
    """
    model = model_formset.model
    form_fields = list(model_formset.form._meta.fields)
    formset_added = ['id', 'DELETE']  # form fields im pretty sure are added by formset factory. wont do anything if it not needed anyway

    model_instances = [] if not quantity else baker.prepare(model, _quantity=quantity, **kwargs)

    json_data = serializers.serialize('json', model_instances)
    json_data = [data["fields"] for data in json.loads(json_data)]

    # format json data to formset valid data
    for index in range(quantity):
        form_data = json_data[index]

        # remove keys not in form_fields
        form_data = {name: data for name, data in form_data.items() if name in form_fields}

        # replaces None with empty string
        form_data = {name: data if data is not None else "" for name, data in form_data.items()}

        # converts existing fields to formset valid fields
        form_data = {f'{prefix}-{index}-{field}': form_data.pop(field) for field in form_fields}

        # add formset_added fields
        form_data.update({f'{prefix}-{index}-{field}': '' for field in formset_added})

        json_data[index] = form_data

    # combine everything
    formset_data = {  # management_form
        f'{prefix}-TOTAL_FORMS': quantity,
        f'{prefix}-INITIAL_FORMS': 0,
    }
    [formset_data.update(form_data) for form_data in json_data]
    return formset_data


class ViewTestUtilsMixin():
    """
    Utility methods to make cleaner tests for common response assertions.  The base class must
    be a django TestCase.
    """

    def assertRedirectsAdmin(self, url_name, *args, **kwargs):
        """
        Redirection to django admin is now deprecated.
        Use assertRedirectsLogin(self, url_name, *args, **kwargs) instead.

        Assert that a GET response to reverse(url_name, *args, **kwargs) redirected to the admin login page.
        with appropriate ?next= query string. Provide any url and path parameters as args or kwargs.

        """
        warnings.warn("Redirection to django admin is now deprecated.\nUse assertRedirectsLogin(self, url_name, *args, **kwargs) instead...",
                      stacklevel=2)
        self.assertRedirects(
            response=self.client.get(reverse(url_name, *args, **kwargs)),
            expected_url='{}?next={}'.format('/admin/login/', reverse(url_name, *args, **kwargs)),
        )

    def assertRedirectsHome(self, url_name, *args, **kwargs):
        """
        Assert that a GET response to reverse(url_name, *args, **kwargs) redirected to the home page
        with appropriate ?next= query string. Provide any url and path parameters as args or kwargs.
        """
        self.assertRedirects(
            response=self.client.get(reverse(url_name, *args, **kwargs)),
            expected_url='{}?next={}'.format(reverse('home'), reverse(url_name, *args, **kwargs)),
        )

    def assertRedirectsLogin(self, url_name, *args, **kwargs):
        """
        Assert that a GET response to reverse(url_name, *args, **kwargs) redirected to the login page
        with appropriate ?next= query string. Provide any url and path parameters as args or kwargs.
        """
        self.assertRedirects(
            response=self.client.get(reverse(url_name, *args, **kwargs)),
            expected_url=f'{reverse(settings.LOGIN_URL)}?next={reverse(url_name, *args, **kwargs)}'
        )

    def assertRedirectsLoginURL(self, url_name):
        """
            assertRedirectsLogin function without reverse() hard coded inside it

            Assert that a GET response to reverse(url_name, *args, **kwargs) redirected to the login page
            with appropriate ?next= query string. Provide any url and path parameters as args or kwargs.
        """
        self.assertRedirects(
            response=self.client.get(url_name),
            expected_url=f'{reverse(settings.LOGIN_URL)}?next={url_name}'
        )

    def assertRedirectsQuests(self, url_name, follow=False, *args, **kwargs):
        """
        Assert that a GET response to reverse(url_name, *args, **kwargs) redirected to the available quests page.
        Provide any url and path parameters as args or kwargs.

        Returns the response object.
        """
        response = self.client.get(reverse(url_name, *args, **kwargs), follow=follow)
        self.assertRedirects(
            response=response,
            expected_url=reverse('quest_manager:quests'),
        )
        return response

    def assert200(self, url_name, *args, **kwargs):
        """
        Assert that a GET response to reverse(url_name, *args, **kwargs) succeeded with a status code of 200.
        Provide any url and path parameters as args or kwargs.

        Returns the response object.
        """
        response = self.client.get(reverse(url_name, *args, **kwargs))
        self.assertEqual(
            response.status_code,
            200
        )
        return response

    def assert200URL(self, url):
        """ Assert that a GET response succeeded with a status code of 200.
        """
        response = self.client.get(url)
        self.assertEqual(
            response.status_code,
            200
        )

    def assert302(self, url_name, *args, **kwargs):
        """
        Assert that a GET response to reverse(url_name, *args, **kwargs) gives a 302 Redirect.
        For example, when an unauthenticated user attempts to access a view with the LoginRequiredMixin
        Provide any url and path parameters as args or kwargs.
        """
        response = self.client.get(reverse(url_name, *args, **kwargs))
        self.assertEqual(
            response.status_code,
            302
        )
        return response

    def assert404(self, url_name, *args, **kwargs):
        """
        Assert that a GET response to reverse(url_name, *args, **kwargs) fails with a status code of 404.
        Provide any url and path parameters as args or kwargs.

        Returns the response object.
        """
        response = self.client.get(reverse(url_name, *args, **kwargs))
        self.assertEqual(
            response.status_code,
            404
        )
        return response

    def assert404URL(self, url):
        """Assert that a GET response fails with a status code of 404."""
        response = self.client.get(url)
        self.assertEqual(
            response.status_code,
            404
        )

    def assert403(self, url_name, *args, **kwargs):
        """
        Assert that a response to reverse(url_name, *args, **kwargs) is permission denied: 403
        Provide any url and path parameters as args or kwargs.

        Returns the response object.
        """
        response = self.client.get(reverse(url_name, *args, **kwargs))
        self.assertEqual(
            response.status_code,
            403
        )
        return response

    def get_message_list(self, response):
        """ Django messages missing from context of redirected views, so get another way
        https://stackoverflow.com/questions/2897609/how-can-i-unit-test-django-messages
        https://docs.djangoproject.com/en/3.0/ref/contrib/messages/
        """
        return list(response.wsgi_request._messages)

    def assertSuccessMessage(self, response):
        """ Assert that a response, including redirects, provides a single success message
        """
        message_list = self.get_message_list(response)
        self.assertEqual(len(message_list), 1)
        self.assertEqual(message_list[0].level, messages.SUCCESS)

    def assertWarningMessage(self, response):
        """ Assert that a response, including redirects, provides a single warning message
        """
        message_list = self.get_message_list(response)
        self.assertEqual(len(message_list), 1)
        self.assertEqual(message_list[0].level, messages.WARNING)

    def assertErrorMessage(self, response):
        """ Assert that a response, including redirects, provides a single error message
        """
        message_list = self.get_message_list(response)
        self.assertEqual(len(message_list), 1)
        self.assertEqual(message_list[0].level, messages.ERROR)

    def assertInfoMessage(self, response):
        """ Assert that a response, including redirects, provides a single info message
        """
        message_list = self.get_message_list(response)
        self.assertEqual(len(message_list), 1)
        self.assertEqual(message_list[0].level, messages.INFO)
