import uuid

import embed_video
from django.templatetags.static import static
from django.urls import reverse
from django.db import models
from django.conf import settings
from django.utils import timezone
from embed_video.backends import detect_backend
from embed_video.fields import EmbedVideoField


class Portfolio(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, primary_key=True, on_delete=models.CASCADE)
    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    description = models.TextField(null=True, blank=True, help_text='A description to display with your portfolio.')
    listed_locally = models.BooleanField(default=False, help_text="Your portfolio will be listed on the Students page "
                                                                  "and other students will be able to see it.")
    listed_publicly = models.BooleanField(default=False, help_text="Your portfolio can be listed publicly by your teacher.")

    def __str__(self):
        return str(self.user)

    def get_absolute_url(self):
        return reverse('portfolios:detail', kwargs={'pk': self.pk})

    def get_public_url(self):
        return reverse('portfolios:public', kwargs={'uuid': self.uuid})


class Artwork(models.Model):
    title = models.CharField(max_length=50, help_text='The name of this piece of art.')
    description = models.TextField(null=True, blank=True, help_text='A description of the meaning of this art, '
                                                                    'how the art was made, or any other info you would '
                                                                    'like to share about this portfolio piece')
    date = models.DateField(default=timezone.now, help_text='The date this art was created or completed')
    image_file = models.ImageField(upload_to='portfolios/video/%Y/%m', null=True, blank=True,
                                   help_text="OPTION 1. Your artwork or photograph to display. "
                                             "If a video file is also uploaded, "
                                             "this will be used as the video's preview image.")
    # TODO: set custom validator: https://docs.djangoproject.com/en/1.10/ref/validators/
    video_file = models.FileField(upload_to='portfolios/video/%Y/%m', null=True, blank=True,
                                  help_text='OPTION 2. HTML5 Video types supported by all browsers are: '
                                            'MP4 (H.264 video +AAC or +MP3 audio) and WebM (VP8 video +Vorbis audio).'
                                            'You can upload other video types, but they may not play when you try '
                                            'to view your portfolio.')
    video_url = EmbedVideoField(blank=True, null=True,
                                help_text='OPTION 3. You can also add YouTube or Vimeo videos to your Portfolio '
                                          'by providing the link here.  If a link is provided, the image and video'
                                          'files will be ignored.')
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE)

    def __str__(self):
        return str(self.title)

    def get_absolute_url(self):
        return reverse('portfolios:detail', kwargs={'pk': self.portfolio.pk})

    def get_link(self):
        if self.video_url:
            return self.video_url
        elif self.video_file:
            return self.video_file.url
        else:
            return self.image_file.url

    def get_image_url(self):
        if self.image_file:
            return self.image_file.url
        elif self.video_url:
            return self.get_embed_video_thumbnail()
        else:
            return static('img/icon.png')

    def get_embed_video_thumbnail(self):
        be = detect_backend(self.video_url)
        return be.get_thumbnail_url()

    def get_art_type(self):
        if self.video_url:
            return self.get_embed_url_source()
        elif self.video_file:
            return "Video"
        else:
            return "Image"

    def get_embed_url_source(self):
        if self.video_url:
            backed_class = type(detect_backend(self.video_url))
            if backed_class is embed_video.backends.YoutubeBackend:
                return "YouTube"
            elif backed_class is embed_video.backends.VimeoBackend:
                return "Vimeo"
        else:
            return None

    def is_video(self):
        if self.video_url or self.video_file:
            return True
        return False

    @staticmethod
    def create(title, image_file, video_file, portfolio, date):
        art = Artwork(
            title=title,
            image_file=image_file,
            video_file=video_file,
            portfolio=portfolio,
            date=date,
        )
        art.save()
