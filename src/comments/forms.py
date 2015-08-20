from django import forms

from .models import Comment

# class CommentForm(forms.ModelForm):
#     class Meta:
#         model = Comment
#         fields = ('text',)

class CommentForm(forms.Form):
    comment_text = forms.CharField(label='Comment', widget=forms.Textarea(attrs={'rows':2}))
