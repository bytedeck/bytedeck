from django import forms
from django.core.exceptions import ValidationError

from .import_export import (
    CSV_FIELDS,
    get_bundled_set_keys,
    load_bundled_set,
    parse_uploaded_file,
)


class CompetencyImportForm(forms.Form):
    """ Step 1 of the import flow: pick a bundled curriculum set OR upload a
    JSON/CSV competency-set file. Parsing/validation happens here so the view
    only ever sees a valid, normalized competency set.
    """

    bundled_set = forms.ChoiceField(
        required=False, label="Bundled competency set",
        help_text="Curriculum sets that come with ByteDeck."
    )

    file = forms.FileField(
        required=False, label="Or upload a file",
        help_text=f"A .json competency set, or a .csv file with the header row: {', '.join(CSV_FIELDS)} "
                  "(only the name column is required)."
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['bundled_set'].choices = [('', '---------')] + [
            (key, load_bundled_set(key)['name'] or key) for key in get_bundled_set_keys()
        ]

    def clean(self):
        cleaned_data = super().clean()
        bundled_key = cleaned_data.get('bundled_set')
        file = cleaned_data.get('file')

        if bool(bundled_key) == bool(file):
            raise ValidationError("Choose a bundled competency set or upload a file (but not both).")

        # raises ValidationError with a user-facing message on malformed files
        cleaned_data['competency_set'] = load_bundled_set(bundled_key) if bundled_key else parse_uploaded_file(file)

        return cleaned_data
