from io import BytesIO
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.contrib.auth import get_user_model

from model_bakery import baker

from hackerspace_online.tests.utils import ViewTestUtilsMixin

User = get_user_model()


def generate_test_png():
    """ Returns an InMemoryUploadedFile object containing a minimally viable PNG image of a single transparent pixel."""

    # Define the binary pixel data for a 1x1 black pixel PNG
    pixel_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90\x8d3E\x00\x00\x00\x06PLTE\xff\xff\xff\x00\x00\x00\x00\x00\x00xQ]\x00\x00\x00\x02tRNS\xff\xff\x00O\xde@\x00\x00\x00\x0fIDATx\x9cc```\x00\x00\x00\x05\x00\x01\x1d\x0b\x8c\x02\x00\x00\x00\x00IEND\xaeB`\x82'  # noqa

    # Create an in-memory file
    output = BytesIO(pixel_data)

    # Create the InMemoryUploadedFile object
    uploaded_file = InMemoryUploadedFile(
        file=output,
        field_name=None,
        name="minimal.png",
        content_type="image/png",
        size=output.tell(),
        charset=None
    )
    return uploaded_file


class PortfolioViewTests(ViewTestUtilsMixin, TenantTestCase):
    """ url(r'^$', views.PortfolioList.as_view(), name='list'),
        url(r'^public/$', views.public_list, name='public_list'),
        url(r'^create/$', views.PortfolioCreate.as_view(), name='create'),
        url(r'^(?P<pk>[0-9]+)/$', views.detail, name='detail'),
        url(r'^detail/$', views.detail, name='current_user'),
        url(r'^(?P<uuid>[0-9a-z-]+)/$', views.public, name='public'),
        # url(r'^(?P<pk>[0-9]+)/update/$', views.PortfolioUpdate.as_view(), name='update'),
        url(r'^(?P<pk>[0-9]+)/edit/$', views.edit, name='edit'),

        url(r'^art/(?P<pk>[0-9]+)/create/$', views.ArtworkCreate.as_view(), name='art_create'),

        url(r'^art/create/(?P<doc_id>[0-9]+)$', views.art_add, name='art_add'),
        url(r'^art/(?P<pk>[0-9]+)/delete/$', views.ArtworkDelete.as_view(), name='art_delete'),
        url(r'^art/(?P<pk>[0-9]+)/edit/$', views.ArtworkUpdate.as_view(), name='art_update'),
    """

    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.test_student = baker.make(User)
        self.portfolio = baker.make('portfolios.Portfolio', user=self.test_student)
        self.art = baker.make('portfolios.Artwork', image_file=generate_test_png(), portfolio=self.portfolio)
        self.doc = baker.make('comments.Document', docfile=generate_test_png(), comment=baker.make('comments.Comment', user=self.test_student))

    def test_all_portfolio_view_status_codes_for_anonymous(self):
        ''' If not logged in then all views should redirect to login, EXCEPT the public list and public urls '''

        self.assert200('portfolios:public_list')
        self.assert200('portfolios:public', args=[self.portfolio.uuid])

        self.assertRedirectsLogin('portfolios:list')
        self.assertRedirectsLogin('portfolios:create')
        self.assertRedirectsLogin('portfolios:detail', args=[self.portfolio.pk])
        self.assertRedirectsLogin('portfolios:current_user')
        self.assertRedirectsLogin('portfolios:edit', args=[self.portfolio.pk])
        self.assertRedirectsLogin('portfolios:art_add', args=[self.doc.pk])
        self.assertRedirectsLogin('portfolios:art_delete', args=[self.art.pk])

        self.assert404('portfolios:art_create', args=[self.portfolio.pk])
        self.assert404('portfolios:art_update', args=[self.art.pk])

    def test_all_portfolio_view_status_codes_for_students__own_portfolio(self):

        self.client.force_login(self.test_student)

        self.assert200('portfolios:public_list')
        self.assert200('portfolios:public', args=[self.portfolio.uuid])

        self.assert200('portfolios:list')
        # self.assert200('portfolios:create') # Already exists, created in setUp, Test in own method below
        self.assert200('portfolios:detail', args=[self.portfolio.pk])
        self.assert200('portfolios:current_user')
        self.assert200('portfolios:edit', args=[self.portfolio.pk])
        self.assert200('portfolios:art_delete', args=[self.art.pk])
        self.assert200('portfolios:art_create', args=[self.portfolio.pk])
        self.assert200('portfolios:art_update', args=[self.art.pk])

        # after adding art via quest comment file, redirects to their portfolio
        self.assertRedirects(
            response=self.client.get(reverse('portfolios:art_add', args=[self.doc.pk])),
            expected_url=reverse('portfolios:detail', args=[self.portfolio.pk])
        )

    def test_all_portfolio_view_status_codes_for_students__others_portfolio(self):

        # create a new user and try to access the test student's portfolio and art
        self.client.force_login(baker.make(User))

        self.assert200('portfolios:public_list')
        self.assert200('portfolios:public', args=[self.portfolio.uuid])

        self.assert200('portfolios:list')
        self.assert200('portfolios:current_user')
        # self.assert200('portfolios:create')  # This user doesn't have one yet so should be created (302?)

        # Can't access another user's portfolio (not shared)
        self.assert404('portfolios:detail', args=[self.portfolio.pk])
        self.assert404('portfolios:edit', args=[self.portfolio.pk])
        # self.assert200('portfolios:art_delete', args=[self.art.pk])  # BAD!  Can't delete other user's art!!!
        self.assert404('portfolios:art_create', args=[self.portfolio.pk])
        self.assert404('portfolios:art_update', args=[self.art.pk])
        self.assert404('portfolios:art_add', args=[self.doc.pk])

    def test_all_portfolio_view_status_codes_for_staff(self):

        self.client.force_login(baker.make(User, is_staff=True))

        self.assert200('portfolios:public_list')
        self.assert200('portfolios:public', args=[self.portfolio.uuid])

        self.assert200('portfolios:list')
        # self.assert200('portfolios:create') # Already exists, created in setUp, Test in own method below
        self.assert200('portfolios:detail', args=[self.portfolio.pk])
        self.assert200('portfolios:current_user')
        self.assert200('portfolios:edit', args=[self.portfolio.pk])
        self.assert200('portfolios:art_delete', args=[self.art.pk])
        self.assert200('portfolios:art_create', args=[self.portfolio.pk])
        self.assert200('portfolios:art_update', args=[self.art.pk])

        # after adding art via quest comment file, redirects to their portfolio
        self.assertRedirects(
            response=self.client.get(reverse('portfolios:art_add', args=[self.doc.pk])),
            expected_url=reverse('portfolios:detail', args=[self.portfolio.pk])
        )
