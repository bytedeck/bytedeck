from django_summernote.views import SummernoteEditor


class ByteDeckSummernoteEditor(SummernoteEditor):
    """
    Override `SummernoteEditor` class to use customized template file
    """
    template_name = 'bytedeck_summernote/widget_advanced_editor.html'
