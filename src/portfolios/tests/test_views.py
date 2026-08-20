from django.utils import timezone
from io import BytesIO
from django.urls import reverse
from django.core.files.uploadedfile import InMemoryUploadedFile, SimpleUploadedFile
from django.contrib.auth import get_user_model

from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from portfolios.models import Artwork, Portfolio
from portfolios.views import is_acceptable_vid_type

User = get_user_model()


def generate_test_png_file():
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


class PortfolioViewTests(ByteDeckTenantTestCase):
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

    @classmethod
    def setUpClass(cls):
        """Isolate MEDIA_ROOT in a per-run temp dir before any uploads happen.

        The uploads these tests make (e.g. clip.mp4) otherwise land in the
        project's real _media_uploads and stay there: on the NEXT run Django's
        storage dedupes the repeat filename to clip_XXXX.mp4, so the view titles
        the Artwork "clip_XXXX" and the get(title="clip") assertions error --
        the suite passes once, then fails on every rerun in the same workspace.
        A throwaway MEDIA_ROOT keeps runs deterministic and the repo clean.
        """
        import shutil
        import tempfile

        from django.test import override_settings

        cls._temp_media = tempfile.mkdtemp(prefix='test-media-portfolios-')
        cls._media_override = override_settings(MEDIA_ROOT=cls._temp_media)
        cls._media_override.enable()
        cls.addClassCleanup(cls._media_override.disable)
        cls.addClassCleanup(shutil.rmtree, cls._temp_media, ignore_errors=True)
        super().setUpClass()

    @classmethod
    def setUpTestData(cls):
        """Create a student with a portfolio, one artwork, and a commented document."""
        cls.test_student = baker.make(User)
        cls.portfolio = baker.make('portfolios.Portfolio', user=cls.test_student)
        cls.art = baker.make('portfolios.Artwork', image_file=generate_test_png_file(), portfolio=cls.portfolio)
        cls.doc = baker.make('comments.Document', docfile=generate_test_png_file(), comment=baker.make('comments.Comment', user=cls.test_student))

    def test_all_portfolio_view_status_codes__for_anonymous(self):
        ''' If not logged in then all views should redirect to login, EXCEPT the public list and public urls '''

        self.assert200('portfolios:public_list')
        self.assert200('portfolios:public', args=[self.portfolio.uuid])

        self.assertRedirectsLogin('portfolios:list')
        self.assertRedirectsLogin('portfolios:detail', args=[self.portfolio.pk])
        self.assertRedirectsLogin('portfolios:current_user')
        self.assertRedirectsLogin('portfolios:edit', args=[self.portfolio.pk])
        self.assertRedirectsLogin('portfolios:art_add', args=[self.doc.pk])
        self.assertRedirectsLogin('portfolios:art_delete', args=[self.art.pk])
        self.assertRedirectsLogin('portfolios:art_create', args=[self.portfolio.pk])
        self.assertRedirectsLogin('portfolios:art_update', args=[self.art.pk])

    def test_all_portfolio_view_status_codes_for_students__own_portfolio(self):
        """A student can access, edit, and add art to their own portfolio views."""
        self.client.force_login(self.test_student)

        self.assert200('portfolios:public_list')
        self.assert200('portfolios:public', args=[self.portfolio.uuid])

        self.assert200('portfolios:list')
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
        """A student cannot access another student's unshared portfolio or art views."""
        # create a new user and try to access the test student's portfolio and art
        self.client.force_login(baker.make(User))

        self.assert200('portfolios:public_list')
        self.assert200('portfolios:public', args=[self.portfolio.uuid])

        self.assert200('portfolios:list')
        self.assert200('portfolios:current_user')

        # Can't access another user's portfolio (not shared)
        self.assert404('portfolios:detail', args=[self.portfolio.pk])
        self.assert404('portfolios:edit', args=[self.portfolio.pk])
        self.assert404('portfolios:art_delete', args=[self.art.pk])
        self.assert404('portfolios:art_create', args=[self.portfolio.pk])
        self.assert404('portfolios:art_update', args=[self.art.pk])
        self.assert404('portfolios:art_add', args=[self.doc.pk])

    def test_all_portfolio_view_status_codes__for_staff(self):
        """Staff can access, edit, and add art to any student's portfolio views."""
        self.client.force_login(baker.make(User, is_staff=True))

        self.assert200('portfolios:public_list')
        self.assert200('portfolios:public', args=[self.portfolio.uuid])

        self.assert200('portfolios:list')
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

    def test_DetailView__listed_locally(self):
        """When a portfolio is listed locally, other users should be able to access it"""

        # some random user
        self.client.force_login(baker.make(User))

        # Can't access yet
        self.assert404('portfolios:detail', args=[self.portfolio.pk])

        self.portfolio.listed_locally = True
        self.portfolio.save()

        # now can access
        self.assert200('portfolios:detail', args=[self.portfolio.pk])

    def test_DetailView__no_portfolio_created(self):
        """If a portfolio doesn't already exist, it should be created when accessing the detail view"""

        user = baker.make(User)

        self.assertFalse(Portfolio.objects.filter(user=user).exists())

        self.client.force_login(user)

        self.assert200('portfolios:detail', args=[user.pk])
        self.assert200('portfolios:current_user')

        # accessing the detail page above should have created the portfolio
        self.assertTrue(Portfolio.objects.filter(user=user).exists())

    def test_UpdateView__post(self):
        """Test that the update view can be posted with valid data"""
        self.client.force_login(self.test_student)
        form_data = {
            'user': self.test_student,
        }

        # post request test
        response = self.client.post(
            reverse('portfolios:edit', args=[self.portfolio.pk]),
            data=form_data
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('portfolios:detail', args=[self.portfolio.pk]))

    def test_ArtworkCreateView__post(self):
        """Test that the ArtworkCreate view can be posted with valid data"""
        self.client.force_login(self.test_student)

        form_data = {
            'title': "Test Title",
            'portfolio': self.portfolio,
            'date': timezone.now().date(),
            # missing image or video file
        }

        # post form with missing image
        response = self.client.post(
            reverse('portfolios:art_create', args=[self.portfolio.pk]),
            data=form_data
        )
        form = response.context['form']
        self.assertIn('one of these three fields must be provided', form.errors['video_url'][0])
        self.assertFalse(form.is_valid())

        # Try again with valid form data
        form_data.update({'video_url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'})
        response = self.client.post(
            reverse('portfolios:art_create', args=[self.portfolio.pk]),
            data=form_data
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('portfolios:edit', args=[self.portfolio.pk]))

    def test_ArtworkUpdateView__post(self):
        """A valid ArtworkUpdate POST saves and redirects to the owner's portfolio edit page."""
        self.client.force_login(self.test_student)
        form_data = {
            'title': "Updated Title",
            'portfolio': self.portfolio,
            'date': timezone.now().date(),
            'video_url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
        }
        response = self.client.post(reverse('portfolios:art_update', args=[self.art.pk]), data=form_data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('portfolios:edit', args=[self.portfolio.pk]))
        self.art.refresh_from_db()
        self.assertEqual(self.art.title, "Updated Title")

    def test_ArtworkDeleteView__post(self):
        """An ArtworkDelete POST removes the art and redirects to the owner's portfolio edit page."""
        self.client.force_login(self.test_student)
        response = self.client.post(reverse('portfolios:art_delete', args=[self.art.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('portfolios:edit', args=[self.portfolio.pk]))
        self.assertFalse(Artwork.objects.filter(pk=self.art.pk).exists())

    def test_is_acceptable_vid_type__accepts_video_extensions_only(self):
        """is_acceptable_vid_type recognises video file extensions and rejects others."""
        self.assertTrue(is_acceptable_vid_type("clip.mp4"))
        self.assertTrue(is_acceptable_vid_type("clip.webm"))
        self.assertFalse(is_acceptable_vid_type("picture.png"))

    def test_art_add__video_document_creates_video_artwork(self):
        """Adding art from a video-file comment document creates an Artwork with a video (not image)."""
        self.client.force_login(self.test_student)
        video_doc = baker.make(
            'comments.Document',
            docfile=SimpleUploadedFile("clip.mp4", b"fake-video-bytes", content_type="video/mp4"),
            comment=baker.make('comments.Comment', user=self.test_student),
        )

        response = self.client.get(reverse('portfolios:art_add', args=[video_doc.pk]))

        self.assertEqual(response.status_code, 302)
        artwork = Artwork.objects.get(title="clip")
        self.assertTrue(artwork.video_file)
        self.assertFalse(artwork.image_file)

    def test_art_add__unsupported_format_returns_404(self):
        """Adding art from a comment document that is neither an image nor a video is rejected (404)."""
        self.client.force_login(self.test_student)
        text_doc = baker.make(
            'comments.Document',
            docfile=SimpleUploadedFile("notes.txt", b"not media", content_type="text/plain"),
            comment=baker.make('comments.Comment', user=self.test_student),
        )

        self.assert404('portfolios:art_add', args=[text_doc.pk])

    def _published_answer(self, filename, content_type, user=None):
        """A published file answer (comment set) owned by `user`, ready for art_add_answer.

        Args:
            filename (str): the uploaded file's name; its extension decides the media type.
            content_type (str): the upload's MIME type.
            user (User): the answering student; defaults to the class's test student.

        Returns:
            QuestionSubmission: a published answer holding the file.
        """
        user = user or self.test_student
        return baker.make(
            'questions.QuestionSubmission',
            quest_submission=baker.make('quest_manager.QuestSubmission', user=user),
            response_file=SimpleUploadedFile(filename, b"file_content", content_type=content_type),
            comment=baker.make('comments.Comment', user=user),
        )

    def test_art_add_answer__anonymous_redirects_to_login(self):
        """Adding an answer to a portfolio requires being logged in."""
        answer = self._published_answer("anon-sketch.png", "image/png")
        self.assertRedirectsLogin('portfolios:art_add_answer', args=[answer.pk])

    def test_art_add_answer__own_image_answer_creates_artwork(self):
        """A student's published image file answer lands in their portfolio, like the same
        file attached to a comment would (#2573)."""
        self.client.force_login(self.test_student)
        answer = self._published_answer("own-sketch.png", "image/png")

        response = self.client.get(reverse('portfolios:art_add_answer', args=[answer.pk]))

        self.assertRedirects(response, reverse('portfolios:detail', args=[self.portfolio.pk]))
        artwork = Artwork.objects.get(title="own-sketch")
        self.assertTrue(artwork.image_file)
        self.assertFalse(artwork.video_file)
        self.assertEqual(artwork.portfolio, self.portfolio)
        self.assertEqual(artwork.date, answer.comment.timestamp.date())

    def test_art_add_answer__video_answer_creates_video_artwork(self):
        """A video file answer becomes a video artwork (not an image one)."""
        self.client.force_login(self.test_student)
        answer = self._published_answer("screencast.mp4", "video/mp4")

        response = self.client.get(reverse('portfolios:art_add_answer', args=[answer.pk]))

        self.assertEqual(response.status_code, 302)
        artwork = Artwork.objects.get(title="screencast")
        self.assertTrue(artwork.video_file)
        self.assertFalse(artwork.image_file)

    def test_art_add_answer__staff_adds_to_the_students_portfolio(self):
        """Staff may trigger the add, and the artwork still lands in the student's portfolio."""
        staff = baker.make(User, is_staff=True)
        self.client.force_login(staff)
        answer = self._published_answer("staff-added.png", "image/png")

        response = self.client.get(reverse('portfolios:art_add_answer', args=[answer.pk]))

        self.assertRedirects(response, reverse('portfolios:detail', args=[self.portfolio.pk]))
        self.assertEqual(Artwork.objects.get(title="staff-added").portfolio, self.portfolio)

    def test_art_add_answer__another_students_answer_returns_404(self):
        """A student cannot add someone else's answer to a portfolio."""
        other = baker.make(User)
        self.client.force_login(other)
        answer = self._published_answer("not-yours.png", "image/png")

        self.assert404('portfolios:art_add_answer', args=[answer.pk])

    def test_art_add_answer__draft_answer_returns_404(self):
        """An unpublished (draft) answer cannot be added: its file is not final and it has
        no completion comment to date the artwork by."""
        self.client.force_login(self.test_student)
        draft = baker.make(
            'questions.QuestionSubmission',
            quest_submission=baker.make('quest_manager.QuestSubmission', user=self.test_student),
            response_file=SimpleUploadedFile("draft-sketch.png", b"file_content", content_type="image/png"),
        )

        self.assert404('portfolios:art_add_answer', args=[draft.pk])

    def test_art_add_answer__unsupported_format_returns_404(self):
        """A file answer that is neither an image nor a video is rejected (404)."""
        self.client.force_login(self.test_student)
        answer = self._published_answer("answer-notes.txt", "text/plain")

        self.assert404('portfolios:art_add_answer', args=[answer.pk])
