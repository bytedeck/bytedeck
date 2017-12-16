from datetimewidget.widgets import DateWidget
from django import forms
from portfolios.models import Portfolio, Artwork


class PortfolioForm(forms.ModelForm):
    class Meta:
        model = Portfolio
        fields = ['description', 'listed_locally', 'listed_publicly', ]


class ArtworkForm(forms.ModelForm):
    class Meta:
        model = Artwork
        fields = ['title', 'description', 'date', 'image_file', 'video_file', 'video_url', ]
        widgets = {
            'date': DateWidget(attrs={'id': "date_id"},
                               options={
                                       'autoclose': 'true',
                                       'todayBtn': 'true',
                                       'todayHighlight': 'true',
                                       # 'pickerPosition': 'bottom-left',
                               },
                               usel10n=True,
                               bootstrap_version=3)
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