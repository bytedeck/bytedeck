import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import Http404, HttpResponse
from django.test import RequestFactory
from django.urls import reverse

from model_bakery import baker

from competencies.import_export import load_bundled_set
from competencies.models import Competency
from competencies.views import competencies_enabled
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from siteconfig.models import SiteConfig

User = get_user_model()


class CompetencyViewsFeatureFlagTest(ByteDeckTenantTestCase):
    """ With enable_competencies off (the default), every competencies URL 404s
    for everyone: students and staff alike see no change or difference. """

    def test_competency_views__404_when_disabled(self):
        """ Every competencies URL 404s for anonymous, student, and staff users alike """
        self.assertFalse(SiteConfig.get().enable_competencies)

        for user in [None, baker.make(User), baker.make(User, is_staff=True)]:
            if user:
                self.client.force_login(user)
            self.assert404('competencies:list')
            self.assert404('competencies:import')
            self.assert404('competencies:import_preview')
            self.assert404('competencies:export')
            self.client.logout()

    def test_admin_menu__link_hidden_when_disabled(self):
        """ No menu shows staff a Competencies link while the flag is off """
        staff = baker.make(User, is_staff=True)
        self.client.force_login(staff)
        response = self.client.get(reverse('quests:quests'))
        self.assertNotContains(response, reverse('competencies:list'))

    def test_competencies_enabled__no_siteconfig_is_404(self):
        """ On the public schema SiteConfig.get() returns None: the flag check treats that as
        disabled and 404s, rather than raising AttributeError (a 500) """
        view = competencies_enabled(lambda request: HttpResponse('ok'))

        with patch('competencies.views.SiteConfig.get', return_value=None):
            with self.assertRaises(Http404):
                view(RequestFactory().get('/competencies/'))


class CompetencyViewsEnabledTest(ByteDeckTenantTestCase):
    """ Tests for the competencies views with the feature flag turned on. """

    def setUp(self):
        """ Enables the feature flag and creates a student and a staff user. """
        config = SiteConfig.get()
        config.enable_competencies = True
        config.full_clean()
        config.save()

        self.student = baker.make(User)
        self.staff = baker.make(User, is_staff=True)

    def test_competency_views__require_staff(self):
        """ With the flag on, anonymous users are sent to login and students get a 403 """
        # anonymous users are redirected to login
        self.assertRedirectsLogin('competencies:list')
        self.assertRedirectsLogin('competencies:import')

        # students get a 403
        self.client.force_login(self.student)
        self.assert403('competencies:list')
        self.assert403('competencies:import')
        self.assert403('competencies:import_preview')
        self.assert403('competencies:export')

    def test_admin_menu__link_under_course_setup(self):
        """ With the flag on, staff find Competencies in the top navbar's Admin menu under Course Setup,
        right after Courses, and not in the sidebar's Quests menu (the navbar renders the Admin menu
        twice, once for wide screens and once for the collapsed phone menu) """
        self.client.force_login(self.staff)
        response = self.client.get(reverse('quests:quests'))

        self.assertContains(response, f'href="{reverse("competencies:list")}"', count=2)
        self.assertRegex(
            response.content.decode(),
            rf'Courses</a></li>\s*<li><a href="{reverse("competencies:list")}">',
        )

    def test_list_view__shows_competencies(self):
        """ The list view renders the deck's competencies for staff, with their courses """
        self.client.force_login(self.staff)
        baker.make(Competency, name='Think critically', course='ADST 9')
        response = self.assert200('competencies:list')
        self.assertContains(response, 'Think critically')
        self.assertContains(response, ">Course</th>")
        self.assertContains(response, "<td>ADST 9</td>")

    def test_import_form__bundled_sets_listed_by_name(self):
        """ The bundled sets are offered alphabetically by name, so a course's grades sit together """
        self.client.force_login(self.staff)
        response = self.assert200('competencies:import')

        labels = [label for key, label in response.context['form'].fields['bundled_set'].choices if key]
        self.assertEqual(labels, sorted(labels, key=str.lower))
        self.assertIn('BC Media Design 11 Curricular Competencies', labels)

    def test_import_flow__bundled_set(self):
        """ The full UI loop: pick a bundled set, preview it, import everything """
        self.client.force_login(self.staff)

        response = self.assert200('competencies:import')
        self.assertContains(response, 'BC Core Competencies')

        # step 1: choose the bundled set
        response = self.client.post(reverse('competencies:import'), data={'bundled_set': 'bc-core-competencies'})
        self.assertRedirects(response, reverse('competencies:import_preview'))

        # step 2: preview shows the entries as new
        response = self.assert200('competencies:import_preview')
        self.assertContains(response, 'Communicating')
        self.assertContains(response, 'label-success')  # "new" badges

        # confirm, selecting all entries
        num_entries = len(load_bundled_set('bc-core-competencies')['entries'])
        response = self.client.post(
            reverse('competencies:import_preview'),
            data={'entries': [str(i) for i in range(num_entries)]},
            follow=True,
        )
        self.assertRedirects(response, reverse('competencies:list'))
        self.assertSuccessMessage(response)
        self.assertEqual(Competency.objects.count(), num_entries)

        # re-importing via the UI is idempotent
        self.client.post(reverse('competencies:import'), data={'bundled_set': 'bc-core-competencies'})
        response = self.assert200('competencies:import_preview')
        self.assertContains(response, 'label-info')  # "update" badges
        self.client.post(
            reverse('competencies:import_preview'),
            data={'entries': [str(i) for i in range(num_entries)]},
        )
        self.assertEqual(Competency.objects.count(), num_entries)

    def test_import_flow__partial_selection(self):
        """ Only the entries ticked on the preview are imported """
        self.client.force_login(self.staff)
        self.client.post(reverse('competencies:import'), data={'bundled_set': 'bc-core-competencies'})
        self.client.post(reverse('competencies:import_preview'), data={'entries': ['0', '1']})
        self.assertEqual(Competency.objects.count(), 2)

    def test_import_flow__nothing_selected(self):
        """ Submitting the preview with nothing selected imports nothing and warns """
        self.client.force_login(self.staff)
        self.client.post(reverse('competencies:import'), data={'bundled_set': 'bc-core-competencies'})
        response = self.client.post(reverse('competencies:import_preview'), data={}, follow=True)
        self.assertRedirects(response, reverse('competencies:import_preview'))
        self.assertWarningMessage(response)
        self.assertEqual(Competency.objects.count(), 0)

    def test_import_flow__json_upload(self):
        """ A .json competency-set upload flows through preview to import """
        self.client.force_login(self.staff)
        content = json.dumps({
            'format': 'bytedeck-competency-set',
            'version': 1,
            'name': 'Uploaded set',
            'entries': [{'source_id': 'x:1', 'name': 'Uploaded competency', 'description': '', 'category': 'Cat'}],
        }).encode()
        upload = SimpleUploadedFile('my-set.json', content, content_type='application/json')

        response = self.client.post(reverse('competencies:import'), data={'file': upload})
        self.assertRedirects(response, reverse('competencies:import_preview'))

        self.client.post(reverse('competencies:import_preview'), data={'entries': ['0']})
        self.assertTrue(Competency.objects.filter(name='Uploaded competency').exists())

    def test_import_flow__csv_upload(self):
        """ A .csv upload flows through preview to import, preserving the category """
        self.client.force_login(self.staff)
        upload = SimpleUploadedFile(
            'my-set.csv', b"name,category\nCSV competency,Some strand\n", content_type='text/csv')

        response = self.client.post(reverse('competencies:import'), data={'file': upload})
        self.assertRedirects(response, reverse('competencies:import_preview'))

        self.client.post(reverse('competencies:import_preview'), data={'entries': ['0']})
        competency = Competency.objects.get(name='CSV competency')
        self.assertEqual(competency.category, 'Some strand')

    def test_import_form__malformed_file_shows_error(self):
        """ A malformed upload re-renders the form with the parser's error """
        self.client.force_login(self.staff)
        upload = SimpleUploadedFile('broken.json', b'{not json', content_type='application/json')
        response = self.client.post(reverse('competencies:import'), data={'file': upload})

        self.assertEqual(response.status_code, 200)  # re-renders the form with errors
        self.assertContains(response, 'not valid JSON')

    def test_import_form__requires_exactly_one_source(self):
        """ The form rejects neither/both of bundled set and file upload """
        self.client.force_login(self.staff)

        response = self.client.post(reverse('competencies:import'), data={})
        self.assertContains(response, 'Choose a bundled competency set or upload a file')

        upload = SimpleUploadedFile('x.csv', b'name\na\n', content_type='text/csv')
        response = self.client.post(
            reverse('competencies:import'), data={'bundled_set': 'bc-core-competencies', 'file': upload})
        self.assertContains(response, 'Choose a bundled competency set or upload a file')

    def test_import_preview__redirects_without_session(self):
        """ Jumping straight to the preview page without uploading redirects back """
        self.client.force_login(self.staff)
        self.assertRedirects(self.client.get(reverse('competencies:import_preview')), reverse('competencies:import'))
        self.assertRedirects(self.client.post(reverse('competencies:import_preview')), reverse('competencies:import'))

    def test_export__json(self):
        """ The export view returns the competencies as a JSON attachment by default """
        self.client.force_login(self.staff)
        baker.make(Competency, name='Exportable', category='Cat', source_id='x:1')

        response = self.client.get(reverse('competencies:export'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertIn('attachment', response['Content-Disposition'])

        data = json.loads(response.content)
        self.assertEqual(data['format'], 'bytedeck-competency-set')
        self.assertEqual(data['entries'][0]['name'], 'Exportable')

    def test_export__csv(self):
        """ The export view returns a CSV attachment when ?format=csv """
        self.client.force_login(self.staff)
        baker.make(Competency, name='Exportable', category='Cat')

        response = self.client.get(reverse('competencies:export') + '?format=csv')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        content = response.content.decode()
        self.assertTrue(content.startswith('course,category,name,description,source_id'))
        self.assertIn('Exportable', content)

    def test_export__unknown_format_404s(self):
        """ An unrecognized ?format= 404s """
        self.client.force_login(self.staff)
        response = self.client.get(reverse('competencies:export') + '?format=xml')
        self.assertEqual(response.status_code, 404)
