from django import forms

from django_summernote.widgets import SummernoteWidget, SummernoteInplaceWidget

from .models import Comment

# class CommentForm(forms.ModelForm):
#     class Meta:
#         model = Comment
#         fields = ('text',)

class CommentForm(forms.Form):

    def __init__(self,
                label='Comment',
                wysiwyg=False,
                accept_files=False):
        self.wysiwyg = wysiwyg
        self.accept_files = accept_files
        self.label = label

        super(CommentForm, self).__init__()
        # do some more stuff after the object has been created
        if self.wysiwyg:
            self.fields['comment_text'].widget = SummernoteWidget()
        else:
            self.fields['comment_text'].widget = forms.Textarea(attrs={'rows':2})


    comment_text = forms.CharField()
