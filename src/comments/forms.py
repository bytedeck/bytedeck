from django import forms

from django_summernote.widgets import SummernoteWidget, SummernoteInplaceWidget

from .models import Comment

# class CommentForm(forms.ModelForm):
#     class Meta:
#         model = Comment
#         fields = ('text',)

class CommentForm(forms.Form):

    def __init__(self, *args, **kwargs):
        self.wysiwyg = kwargs.pop('wysiwyg', False)
        self.label = kwargs.pop('label', 'Comment')
        # self.accept_files = kwargs.get('accept_files', False)

        super(CommentForm, self).__init__(*args, **kwargs)
        # do some more stuff after the object has been created
        if self.wysiwyg:
            self.fields['comment_text'].widget = SummernoteWidget()
        else:
            self.fields['comment_text'].widget = forms.Textarea(attrs={'rows':2})

        self.fields['comment_text'].label = self.label

    comment_text = forms.CharField()
