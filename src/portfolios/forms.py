from django import forms
from portfolios.models import Portfolio, Artwork


class PortfolioForm(forms.ModelForm):
    class Meta:
        model = Portfolio
        fields = ['shared', ]


class ArtworkForm(forms.ModelForm):
    class Meta:
        model = Artwork
        fields = ['title', 'description', ]