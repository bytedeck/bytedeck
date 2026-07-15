from django.contrib import messages
from django.conf import settings
from django.core import serializers
from django.db import connection
from django.shortcuts import reverse

from django_tenants.test.cases import TenantTestCase
from django_tenants.utils import get_tenant_model, get_tenant_domain_model

from model_bakery import baker

import json
import warnings


class ByteDeckTenantTestCase(TenantTestCase):
    """A TenantTestCase whose ``setUpTestData`` hook actually runs.

    django-tenants' ``TenantTestCase.setUpClass`` never calls ``super().setUpClass()``,
    which silently skips all of Django ``TestCase``'s class-level setup — most
    importantly the class-wide atomic transaction and the ``setUpTestData`` hook.
    A ``setUpTestData`` method defined on a plain ``TenantTestCase`` subclass is
    therefore never called, and tests depending on its data fail (or worse, pass
    while asserting nothing).

    This class restores the standard Django behavior: it performs the same tenant
    setup as ``TenantTestCase.setUpClass`` (creating and migrating the ``test``
    schema, then pointing the connection at it), and *then* runs Django's
    ``TestCase.setUpClass``, so ``setUpTestData`` executes once per class inside a
    class-level transaction with the tenant schema active. Django rolls each test
    back to a savepoint, and (since Django 3.2) hands each test a fresh deep copy
    of in-memory objects assigned in ``setUpTestData``, so per-test isolation is
    preserved exactly as documented for regular Django ``TestCase``.

    Use this as the base class for all tenant tests. Fixtures that no test needs
    to rebuild per-method belong in ``setUpTestData``; ``self.client = TenantClient
    (self.tenant)`` and ``force_login`` calls stay in ``setUp``.
    """

    @classmethod
    def setUpClass(cls):
        """Create/migrate the test tenant, then run Django's class-level setup."""
        # Tenant setup below is copied verbatim from django-tenants 3.10's
        # TenantTestCase.setUpClass (which we can't call, because it both skips
        # TestCase.setUpClass and can't have it run *before* the tenant exists).
        cls.sync_shared()
        cls.add_allowed_test_domain()
        cls.tenant = get_tenant_model()(schema_name=cls.get_test_schema_name())
        cls.setup_tenant(cls.tenant)
        cls.tenant.save(verbosity=cls.get_verbosity())

        tenant_domain = cls.get_test_tenant_domain()
        cls.domain = get_tenant_domain_model()(tenant=cls.tenant, domain=tenant_domain)
        cls.setup_domain(cls.domain)
        cls.domain.save()

        connection.set_tenant(cls.tenant)

        # Standard Django TestCase class setup: enters the class-wide atomic
        # block and calls setUpTestData with the tenant schema active.
        # super(TenantTestCase, cls) skips django-tenants' override.
        super(TenantTestCase, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        """Roll back class-level data, then drop the test tenant."""
        # Rolls back the class-wide atomic block (i.e. everything created in
        # setUpTestData) before the schema is dropped.
        super(TenantTestCase, cls).tearDownClass()

        connection.set_schema_to_public()
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
