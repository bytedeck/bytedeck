from bootstrap_datepicker_plus.widgets import DatePickerInput
from django import forms
from django_summernote.widgets import SummernoteInplaceWidget

from portfolios.models import Portfolio, Artwork


class PortfolioForm(forms.ModelForm):
    class Meta:
        model = Portfolio
        fields = ['description', 'listed_locally', 'listed_publicly', ]
        widgets = {
            'description': SummernoteInplaceWidget(),
        }


class ArtworkForm(forms.ModelForm):
    class Meta:
        model = Artwork
        fields = ['title', 'description', 'date', 'image_file', 'video_file', 'video_url', ]
        widgets = {
            'date': DatePickerInput(format='%Y-%m-%d'),
        }

    def clean(self):
        cleaned_data = super(ArtworkForm, self).clean()
        image_file = cleaned_data.get("image_file")
        video_file = cleaned_data.get("video_file")
        video_url = cleaned_data.get("video_url")

        if not (image_file or video_file or video_url):
            msg = "At least one of these three fields must be provided."
            self.add_error('image_file', msg)
            self.add_error('video_file', msg)
            self.add_error('video_url', msg)
