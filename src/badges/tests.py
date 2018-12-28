# Create your tests here.
from django.http import HttpRequest
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from badges.urls import urlpatterns


class PageTests(TestCase):

    fixtures = ['initial_data.json']


    def get_response_code(self, url_pattern_name, args=None):
        response = self.client.get(reverse(url_pattern_name, args))
        return response.status_code

    def test_all_badge_page_status_codes(self):



        # for url in urlpatterns:
        self.assertEquals(self.get_response_code('badges:list'), 200)
        self.assertEquals(self.get_response_code('badges:badge_create'), 200)
        self.assertEquals(self.get_response_code('badges:bulk_grant'), 200)
        self.assertEquals(self.get_response_code('badges:badge_detail', args=[1]), 200)




        # for url in urlpatterns:
        #     print(url)

    # def test_view_url_by_name(self):
    #     response = self.client.get(reverse('home'))
    #     self.assertEquals(response.status_code, 200)
    #
    # def test_view_uses_correct_template(self):
    #     response = self.client.get(reverse('home'))
    #     self.assertEquals(response.status_code, 200)
    #     self.assertTemplateUsed(response, 'home.html')
    #
    # def test_home_page_contains_correct_html(self):
    #     response = self.client.get('/')
    #     self.assertContains(response, '<h1>Homepage</h1>')
    #
    # def test_home_page_does_not_contain_incorrect_html(self):
    #     response = self.client.get('/')
    #     self.assertNotContains(
    #         response, 'Hi there! I should not be on the page.')