from django_summernote.views import SummernoteEditor


class ByteDeckSummernoteEditor(SummernoteEditor):
    """
    Override `SummernoteEditor` class to use customized template file (mandatory for ByteDeck project)
    """

    template_name = "bytedeck_summernote/widget_iframe_editor.html"
