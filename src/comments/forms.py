from django import forms
from django.utils.html import escape

from bytedeck_summernote.widgets import ByteDeckSummernoteSafeInplaceWidget


# class CommentForm(forms.ModelForm):
#     class Meta:
#         model = Comment
#         fields = ('text',)

class CommentForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.wysiwyg = kwargs.pop('wysiwyg', False)
        self.label = kwargs.pop('label', 'Comment')
        # self.accept_files = kwargs.get('accept_files', False)

        super().__init__(*args, **kwargs)
        # do some more stuff after the object has been created
        if self.wysiwyg:
            self.fields['comment_text'].widget = ByteDeckSummernoteSafeInplaceWidget()
        else:
            self.fields['comment_text'].widget = forms.Textarea(attrs={'rows': 2})

        self.fields['comment_text'].label = self.label

    comment_text = forms.CharField()

    def clean_comment_text(self):
        text = self.cleaned_data.get('comment_text', '')
        if not self.wysiwyg:
            # The plain-text (non-wysiwyg) comment field is accessible to all users,
            # so no HTML at all is allowed in it, otherwise scripts can be injected
            # and will execute when the comment is rendered (see issue #1343).
            # The wysiwyg variant is sanitized by the safe summernote widget instead.
            text = escape(text)
        return text
