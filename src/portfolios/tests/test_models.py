from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.templatetags.static import static

from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from portfolios.models import Artwork, Portfolio

User = get_user_model()

YOUTUBE_URL = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
VIMEO_URL = 'https://vimeo.com/123456789'


class PortfolioModelTest(ByteDeckTenantTestCase):
    """Tests for the Portfolio model's url helpers."""

    def test_str_and_urls(self):
        student = baker.make(User)
        portfolio = baker.make(Portfolio, user=student)

        self.assertEqual(str(portfolio), str(student))
        self.assertIn(str(portfolio.pk), portfolio.get_absolute_url())
        self.assertIn(str(portfolio.uuid), portfolio.get_public_url())


class ArtworkGetLinkTest(ByteDeckTenantTestCase):
    """Tests for Artwork.get_link()'s video_url / video_file / image_file precedence."""

    def test_get_link__prefers_video_url(self):
        art = Artwork(video_url=YOUTUBE_URL)
        self.assertEqual(art.get_link(), YOUTUBE_URL)

    def test_get_link__falls_back_to_video_file(self):
        art = baker.make(Artwork, video_url='', video_file='portfolios/video/clip.mp4')
        self.assertEqual(art.get_link(), art.video_file.url)

    def test_get_link__falls_back_to_image_file(self):
        art = baker.make(Artwork, video_url='', video_file='', image_file='portfolios/video/pic.png')
        self.assertEqual(art.get_link(), art.image_file.url)


class ArtworkGetImageUrlTest(ByteDeckTenantTestCase):
    """Tests for Artwork.get_image_url()'s image_file / video_url / default precedence."""

    def test_get_image_url__prefers_image_file(self):
        art = baker.make(Artwork, image_file='portfolios/video/pic.png', video_url='')
        self.assertEqual(art.get_image_url(), art.image_file.url)

    def test_get_image_url__uses_video_thumbnail_when_only_video_url(self):
        art = Artwork(image_file='', video_url=YOUTUBE_URL)
        with patch.object(Artwork, 'get_embed_video_thumbnail', return_value='THUMB') as mock_thumb:
            self.assertEqual(art.get_image_url(), 'THUMB')
        mock_thumb.assert_called_once()

    def test_get_image_url__defaults_to_static_icon(self):
        art = Artwork(image_file='', video_url='', video_file='')
        self.assertEqual(art.get_image_url(), static('img/icon.png'))


class ArtworkGetEmbedVideoThumbnailTest(ByteDeckTenantTestCase):
    """Tests for Artwork.get_embed_video_thumbnail()."""

    def test_delegates_to_backend_thumbnail_url(self):
        """The thumbnail comes from the embed_video backend for the video url.

        The backend is mocked because embed_video's real YouTube backend makes an
        outbound HEAD request to pick the highest-res thumbnail, which we don't want
        in tests.
        """
        art = Artwork(video_url=YOUTUBE_URL)
        fake_backend = MagicMock()
        fake_backend.get_thumbnail_url.return_value = 'http://img.youtube.com/vi/dQw4w9WgXcQ/0.jpg'
        with patch('portfolios.models.detect_backend', return_value=fake_backend) as mock_detect:
            self.assertEqual(art.get_embed_video_thumbnail(), 'http://img.youtube.com/vi/dQw4w9WgXcQ/0.jpg')
        mock_detect.assert_called_once_with(YOUTUBE_URL)


class ArtworkGetArtTypeTest(ByteDeckTenantTestCase):
    """Tests for Artwork.get_art_type()."""

    def test_get_art_type__video_url_returns_source(self):
        art = Artwork(video_url=YOUTUBE_URL)
        self.assertEqual(art.get_art_type(), "YouTube")

    def test_get_art_type__video_file_returns_video(self):
        art = Artwork(video_url='', video_file='portfolios/video/clip.mp4')
        self.assertEqual(art.get_art_type(), "Video")

    def test_get_art_type__image_returns_image(self):
        art = Artwork(video_url='', video_file='', image_file='portfolios/video/pic.png')
        self.assertEqual(art.get_art_type(), "Image")


class ArtworkGetEmbedUrlSourceTest(ByteDeckTenantTestCase):
    """Tests for Artwork.get_embed_url_source()."""

    def test_youtube(self):
        self.assertEqual(Artwork(video_url=YOUTUBE_URL).get_embed_url_source(), "YouTube")

    def test_vimeo(self):
        self.assertEqual(Artwork(video_url=VIMEO_URL).get_embed_url_source(), "Vimeo")

    def test_no_video_url_returns_none(self):
        self.assertIsNone(Artwork(video_url='').get_embed_url_source())


class ArtworkIsVideoTest(ByteDeckTenantTestCase):
    """Tests for Artwork.is_video()."""

    def test_is_video__true_for_video_url(self):
        self.assertTrue(Artwork(video_url=YOUTUBE_URL).is_video())

    def test_is_video__true_for_video_file(self):
        self.assertTrue(Artwork(video_url='', video_file='portfolios/video/clip.mp4').is_video())

    def test_is_video__false_for_image(self):
        self.assertFalse(Artwork(video_url='', video_file='', image_file='portfolios/video/pic.png').is_video())
