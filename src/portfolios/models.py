import uuid

from django.core.urlresolvers import reverse
from django.db import models
from django.conf import settings


class Portfolio(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, primary_key=True, on_delete=models.CASCADE)
    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    shared = models.BooleanField(default=True)

    def __str__(self):
        return str(self.user)

    def get_absolute_url(self):
        return reverse('portfolios:detail', kwargs={'user_id': self.pk})


class Artwork(models.Model):
    title = models.CharField(max_length=50)
    description = models.TextField(null=True, blank=True)
    file = models.FileField(upload_to='portfolios/%Y/%m/%d')
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE)
    datetime = models.DateTimeField()





