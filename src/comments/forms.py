from django import forms

from django_summernote.widgets import SummernoteWidget, SummernoteInplaceWidget

from .models import Comment

# class CommentForm(forms.ModelForm):
#     class Meta:
#         model = Comment
#         fields = ('text',)

class CommentForm(forms.Form):
    # comment_text = forms.CharField(label='Comment', widget=forms.Textarea(attrs={'rows':2}))
    comment_text = forms.CharField(label='Comment', widget=SummernoteWidget())
