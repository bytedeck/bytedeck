from django.contrib import messages
from django.conf import settings
from django.shortcuts import reverse


class ViewTestUtilsMixin():
    """ 
    Utility methods to make cleaner tests for common response assertions.  The base class must
    be a django TestCase.
    """

    def assertRedirectsAdmin(self, url_name, *args, **kwargs):
        """
        Assert that a GET response to reverse(url_name, *args, **kwargs) redirected to the admin login page.
        with appropriate ?next= query string. Provide any url and path parameters as args or kwargs.

        """
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
            expected_url='%s?next=%s' % (reverse('home'), reverse(url_name, *args, **kwargs)),
        )

    def assertRedirectsLogin(self, url_name, *args, **kwargs):
        """
        Assert that a GET response to reverse(url_name, *args, **kwargs) redirected to the login page
        with appropriate ?next= query string. Provide any url and path parameters as args or kwargs.
        """
        self.assertRedirects(
            response=self.client.get(reverse(url_name, *args, **kwargs)),
            expected_url='%s?next=%s' % (reverse(settings.LOGIN_URL), reverse(url_name, *args, **kwargs))
        )

    def assertRedirectsQuests(self, url_name, follow=False, *args, **kwargs):
        """
        Assert that a GET response to reverse(url_name, *args, **kwargs) redirected to the available quests page.
        Provide any url and path parameters as args or kwargs.
        """
        response = self.client.get(reverse(url_name, *args, **kwargs), follow=follow)
        self.assertRedirects(
            response=response,
            expected_url=reverse('quest_manager:quests'),
        )

    def assert200(self, url_name, *args, **kwargs):
        """
        Assert that a GET response to reverse(url_name, *args, **kwargs) succeeded with a status code of 200.
        Provide any url and path parameters as args or kwargs.
        """
        response = self.client.get(reverse(url_name, *args, **kwargs))
        self.assertEqual(
            response.status_code,
            200
        )

    def assert404(self, url_name, *args, **kwargs):
        """
        Assert that a GET response to reverse(url_name, *args, **kwargs) fails with a status code of 404.
        Provide any url and path parameters as args or kwargs.
        """
        response = self.client.get(reverse(url_name, *args, **kwargs))
        self.assertEqual(
            response.status_code,
            404
        )

    def assert403(self, url_name, *args, **kwargs):
        """
        Assert that a response to reverse(url_name, *args, **kwargs) is permission denied: 403
        Provide any url and path parameters as args or kwargs.
        """
        response = self.client.get(reverse(url_name, *args, **kwargs))
        self.assertEqual(
            response.status_code,
            403
        )

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
