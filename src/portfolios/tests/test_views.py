from django.utils import timezone
from io import BytesIO
from django.urls import reverse
from django.core.files.uploadedfile import InMemoryUploadedFile, SimpleUploadedFile
from django.contrib.auth import get_user_model

from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase, TempMediaRootMixin
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


class PortfolioViewTests(TempMediaRootMixin, ByteDeckTenantTestCase):
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

    def added_artwork(self):
        """The one artwork a test added, told apart from the fixture's own.

        Not looked up by title: the title comes from the file name, and Django's storage
        dedupes a repeated name (minimal.png becomes minimal_XXXX.png) across tests that
        share this class's MEDIA_ROOT, so a title assertion would pass for the first test
        to run and fail for the rest.

        Returns:
            Artwork: the artwork created during the test.
        """
        return Artwork.objects.exclude(pk=self.art.pk).get(portfolio=self.portfolio)

    def answer_with_file(self, uploaded_file, user=None):
        """A published file answer, the way a completed submission leaves one behind.

        Args:
            uploaded_file: the file to store as the answer's response_file.
            user (User): whose submission it is; defaults to self.test_student.

        Returns:
            QuestionSubmission: the published answer row.
        """
        user = user or self.test_student
        quest_submission = baker.make('quest_manager.QuestSubmission', user=user)
        return baker.make(
            'questions.QuestionSubmission',
            quest_submission=quest_submission,
            question=baker.make('questions.Question', quest=quest_submission.quest, type='file_upload'),
            response_file=uploaded_file,
            # an explicit target keeps model_bakery from filling the comment's content type
            # with a random installed model (see CLAUDE.md on GenericForeignKeys)
            comment=baker.make('comments.Comment', user=user, target_object=quest_submission),
        )

    def test_art_add_answer__student_adds_their_own_image_answer(self):
        """A student's image answer to a file_upload question goes into their portfolio (#2573).

        Before this, the identical file attached to the comment box one section lower had an
        Add to Portfolio button and the answer had none, so asking for work as a question
        quietly removed the only route into a portfolio.
        """
        answer = self.answer_with_file(generate_test_png_file())
        self.client.force_login(self.test_student)

        response = self.client.get(reverse('portfolios:art_add_answer', args=[answer.pk]))

        self.assertRedirects(response, reverse('portfolios:detail', args=[self.portfolio.pk]))
        artwork = self.added_artwork()
        self.assertTrue(artwork.image_file)
        self.assertFalse(artwork.video_file)
        self.assertEqual(artwork.portfolio, self.portfolio)

    def test_art_add_answer__video_answer_creates_video_artwork(self):
        """A video answer becomes a video artwork, not an image one."""
        answer = self.answer_with_file(
            SimpleUploadedFile("clip.mp4", b"fake-video-bytes", content_type="video/mp4"))
        self.client.force_login(self.test_student)

        response = self.client.get(reverse('portfolios:art_add_answer', args=[answer.pk]))

        self.assertEqual(response.status_code, 302)
        artwork = self.added_artwork()
        self.assertTrue(artwork.video_file)
        self.assertFalse(artwork.image_file)

    def test_art_add_answer__staff_add_it_to_the_students_portfolio(self):
        """A teacher may add a student's answer, and it lands in the student's portfolio.

        The marker sees the button beside the answer they are marking, so it has to add the
        work to the person who did it, not to whoever clicked.
        """
        answer = self.answer_with_file(generate_test_png_file())
        teacher = baker.make(User, is_staff=True)
        self.client.force_login(teacher)

        response = self.client.get(reverse('portfolios:art_add_answer', args=[answer.pk]))

        self.assertRedirects(response, reverse('portfolios:detail', args=[self.portfolio.pk]))
        self.assertEqual(self.added_artwork().portfolio, self.portfolio)
        self.assertFalse(Portfolio.objects.filter(user=teacher).exists())

    def test_art_add_answer__another_student_is_refused(self):
        """Someone else's answer is not theirs to publish, so the view 404s and adds nothing."""
        answer = self.answer_with_file(generate_test_png_file())
        self.client.force_login(baker.make(User))

        self.assert404('portfolios:art_add_answer', args=[answer.pk])
        self.assertFalse(Artwork.objects.exclude(pk=self.art.pk).exists())

    def test_art_add_answer__anonymous_redirects_to_login(self):
        """The view is login-only, like every other portfolio view."""
        answer = self.answer_with_file(generate_test_png_file())
        self.assertRedirectsLogin('portfolios:art_add_answer', args=[answer.pk])

    def test_art_add_answer__unsupported_format_returns_404(self):
        """An answer that is neither an image nor a video is not artwork."""
        answer = self.answer_with_file(
            SimpleUploadedFile("notes.txt", b"not media", content_type="text/plain"))
        self.client.force_login(self.test_student)

        self.assert404('portfolios:art_add_answer', args=[answer.pk])

    def test_art_add_answer__text_answer_has_nothing_to_add(self):
        """A text answer has no file, so the view refuses it rather than failing on an empty one."""
        quest_submission = baker.make('quest_manager.QuestSubmission', user=self.test_student)
        answer = baker.make(
            'questions.QuestionSubmission',
            quest_submission=quest_submission,
            question=baker.make('questions.Question', quest=quest_submission.quest, type='short_answer'),
            response_text="not a file",
            comment=baker.make('comments.Comment', user=self.test_student, target_object=quest_submission),
        )
        self.client.force_login(self.test_student)

        self.assert404('portfolios:art_add_answer', args=[answer.pk])

    def test_art_add_answer__a_draft_row_is_dated_from_its_own_creation(self):
        """An answer with no comment yet is still dated, rather than failing on the missing one.

        Drafts have no published comment, and the button is only ever rendered on published
        answers, so this is the defensive path: it must not 500 if the URL is visited directly.
        """
        quest_submission = baker.make('quest_manager.QuestSubmission', user=self.test_student)
        answer = baker.make(
            'questions.QuestionSubmission',
            quest_submission=quest_submission,
            question=baker.make('questions.Question', quest=quest_submission.quest, type='file_upload'),
            response_file=generate_test_png_file(),
            comment=None,
        )
        self.client.force_login(self.test_student)

        response = self.client.get(reverse('portfolios:art_add_answer', args=[answer.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.added_artwork().date, answer.datetime_created.date())

    def test_art_add__unsupported_format_returns_404(self):
        """Adding art from a comment document that is neither an image nor a video is rejected (404)."""
        self.client.force_login(self.test_student)
        text_doc = baker.make(
            'comments.Document',
            docfile=SimpleUploadedFile("notes.txt", b"not media", content_type="text/plain"),
            comment=baker.make('comments.Comment', user=self.test_student),
        )

        self.assert404('portfolios:art_add', args=[text_doc.pk])
