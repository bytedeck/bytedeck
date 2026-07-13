import json

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from model_bakery import baker

from competencies.import_export import load_bundled_set
from competencies.models import Competency
from hackerspace_online.tests.utils import ViewTestUtilsMixin
from siteconfig.models import SiteConfig

User = get_user_model()


class CompetencyViewsFeatureFlagTest(ViewTestUtilsMixin, TenantTestCase):
    """ With enable_competencies off (the default), every competencies URL 404s
    for everyone — students and staff alike see no change or difference. """

    def setUp(self):
        self.client = TenantClient(self.tenant)

    def test_all_views_404_when_disabled(self):
        self.assertFalse(SiteConfig.get().enable_competencies)

        for user in [None, baker.make(User), baker.make(User, is_staff=True)]:
            if user:
                self.client.force_login(user)
            self.assert404('competencies:list')
            self.assert404('competencies:import')
            self.assert404('competencies:import_preview')
            self.assert404('competencies:export')
            self.client.logout()

    def test_sidebar_link_hidden_when_disabled(self):
        staff = baker.make(User, is_staff=True)
        self.client.force_login(staff)
        response = self.client.get(reverse('quests:quests'))
        self.assertNotContains(response, reverse('competencies:list'))


class CompetencyViewsEnabledTest(ViewTestUtilsMixin, TenantTestCase):

    def setUp(self):
        self.client = TenantClient(self.tenant)
        config = SiteConfig.get()
        config.enable_competencies = True
        config.save()

        self.student = baker.make(User)
        self.staff = baker.make(User, is_staff=True)

    def test_all_views_require_staff(self):
        # anonymous users are redirected to login
        self.assertRedirectsLogin('competencies:list')
        self.assertRedirectsLogin('competencies:import')

        # students get a 403
        self.client.force_login(self.student)
        self.assert403('competencies:list')
        self.assert403('competencies:import')
        self.assert403('competencies:import_preview')
        self.assert403('competencies:export')

    def test_sidebar_link_shown_to_staff(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('quests:quests'))
        self.assertContains(response, reverse('competencies:list'))

    def test_list_view(self):
        self.client.force_login(self.staff)
        baker.make(Competency, name='Think critically')
        response = self.assert200('competencies:list')
        self.assertContains(response, 'Think critically')

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
        self.client.force_login(self.staff)
        self.client.post(reverse('competencies:import'), data={'bundled_set': 'bc-core-competencies'})
        self.client.post(reverse('competencies:import_preview'), data={'entries': ['0', '1']})
        self.assertEqual(Competency.objects.count(), 2)

    def test_import_flow__nothing_selected(self):
        self.client.force_login(self.staff)
        self.client.post(reverse('competencies:import'), data={'bundled_set': 'bc-core-competencies'})
        response = self.client.post(reverse('competencies:import_preview'), data={}, follow=True)
        self.assertRedirects(response, reverse('competencies:import_preview'))
        self.assertWarningMessage(response)
        self.assertEqual(Competency.objects.count(), 0)

    def test_import_flow__json_upload(self):
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
        self.client.force_login(self.staff)
        upload = SimpleUploadedFile(
            'my-set.csv', b"name,category\nCSV competency,Some strand\n", content_type='text/csv')

        response = self.client.post(reverse('competencies:import'), data={'file': upload})
        self.assertRedirects(response, reverse('competencies:import_preview'))

        self.client.post(reverse('competencies:import_preview'), data={'entries': ['0']})
        competency = Competency.objects.get(name='CSV competency')
        self.assertEqual(competency.category, 'Some strand')

    def test_import_form__malformed_file_shows_error(self):
        self.client.force_login(self.staff)
        upload = SimpleUploadedFile('broken.json', b'{not json', content_type='application/json')
        response = self.client.post(reverse('competencies:import'), data={'file': upload})

        self.assertEqual(response.status_code, 200)  # re-renders the form with errors
        self.assertContains(response, 'not valid JSON')

    def test_import_form__requires_exactly_one_source(self):
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
        self.client.force_login(self.staff)
        baker.make(Competency, name='Exportable', category='Cat')

        response = self.client.get(reverse('competencies:export') + '?format=csv')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        content = response.content.decode()
        self.assertTrue(content.startswith('name,category,description,source_id'))
        self.assertIn('Exportable', content)

    def test_export__unknown_format_404s(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('competencies:export') + '?format=xml')
        self.assertEqual(response.status_code, 404)
