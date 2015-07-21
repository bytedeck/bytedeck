import datetime
from haystack import indexes
from .models import Announcement


class AnnouncementIndex(indexes.SearchIndex, indexes.Indexable):
    text = indexes.CharField(document=True, use_template=True)
    author = indexes.CharField(model_attr='author')
    datetime_released = indexes.DateTimeField(model_attr='datetime_released')

    def get_model(self):
        return Announcement

    def index_queryset(self, using=None):
        """Used when the entire index for model is updated."""
        return self.get_model().objects.filter(datetime_released__lte=datetime.datetime.now())
