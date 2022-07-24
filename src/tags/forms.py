from dal import autocomplete


class BootstrapTaggitSelect2Widget(autocomplete.TaggitSelect2):
    """A TaggitSelect2 widget with a bootstrap theme"""

    autocomplete_view = 'tags:autocomplete'

    def __init__(self, *args, **kwargs):
        super().__init__(BootstrapTaggitSelect2Widget.autocomplete_view, *args, **kwargs)

    class Media:
        js = ('/static/js/select2-set-theme-bootstrap.js',)
        css = {
            'all': ('https://cdnjs.cloudflare.com/ajax/libs/select2-bootstrap-theme/0.1.0-beta.10/select2-bootstrap.min.css',)
        }
