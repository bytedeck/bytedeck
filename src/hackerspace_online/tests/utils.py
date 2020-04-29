from django.shortcuts import reverse
    
    
class ViewTestUtilsMixin():
    """ 
    Utility methods to make cleaner tests for common response assertions.  The base class must
    be a django TestCase.
    """

    def assertRedirectsAdmin(self, url_name, *args, **kwargs):
        """
        Assert that a response to reverse(url_name, *args, **kwargs) redirected to the admin login page.
        with appropriate ?next= query string. Provide any url and path parameters as args or kwargs.
        
        """
        self.assertRedirects(
            response=self.client.get(reverse(url_name, *args, **kwargs)),
            expected_url='{}?next={}'.format('/admin/login/', reverse(url_name, *args, **kwargs)),
        )

    def assertRedirectsHome(self, url_name, *args, **kwargs):
        """
        Assert that a response to reverse(url_name, *args, **kwargs) redirected to the home page
        with appropriate ?next= query string. Provide any url and path parameters as args or kwargs.
        """
        self.assertRedirects(
            response=self.client.get(reverse(url_name, *args, **kwargs)),
            expected_url='%s?next=%s' % (reverse('home'), reverse(url_name, *args, **kwargs)),
        )

    def assert200(self, url_name, *args, **kwargs):
        """
        Assert that a response to reverse(url_name, *args, **kwargs) succeeded with a status code of 200.
        Provide any url and path parameters as args or kwargs.
        """
        self.assertEqual(
            self.client.get(reverse(url_name, *args, **kwargs)).status_code,
            200
        )

    def assert404(self, url_name, *args, **kwargs):
        """
        Assert that a response to reverse(url_name, *args, **kwargs) fails with a status code of 404.
        Provide any url and path parameters as args or kwargs.
        """
        self.assertEqual(
            self.client.get(reverse(url_name, *args, **kwargs)).status_code,
            404
        )
