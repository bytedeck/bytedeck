from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from crispy_forms.layout import HTML
from django_select2.forms import Select2MultipleWidget

from siteconfig.models import SiteConfig

from .import_export import (
    CSV_FIELDS,
    get_bundled_set_keys,
    load_bundled_set,
    parse_uploaded_file,
)
from .models import Competency, ProficiencyLevel, QuestCompetency

#: Name of the multi-select field QuestCompetenciesFormMixin adds to a quest form.
COMPETENCIES_FIELD = 'competencies'

#: The quest form's field (Quest.competency_self_assessment) asking students for a self-assessment.
SELF_ASSESSMENT_FIELD = 'competency_self_assessment'


def self_assessment_field_name(competency_pk):
    """ The name of a submission form's self-assessment field for one competency, apart from the
    approval form's level fields (competency_level_field_name).

    Args:
        competency_pk (int): the competency's primary key.

    Returns:
        str: e.g. "self_assessment_12".
    """
    return f'self_assessment_{competency_pk}'


def competency_level_field_name(competency_pk):
    """ The name of a quest form's default-level field for one competency.

    Args:
        competency_pk (int): the competency's primary key.

    Returns:
        str: e.g. "competency_level_12".
    """
    return f'competency_level_{competency_pk}'


def quest_competency_initial(quest):
    """ Initial form data that starts a new quest with another quest's competencies, e.g.
    when copying it. Deactivated competencies are left out: they aren't offered for new use.

    Args:
        quest (Quest): the quest whose competency links to carry over.

    Returns:
        dict: the competencies field's initial selection plus each one's default-level field.
    """
    links = quest.quest_competencies.filter(competency__active=True)
    initial = {COMPETENCIES_FIELD: [link.competency_id for link in links]}
    for link in links:
        initial[competency_level_field_name(link.competency_id)] = link.default_level
    return initial


class CompetencyMultipleChoiceField(forms.ModelMultipleChoiceField):
    """ A multi-select of competencies labelled with their course and category, e.g. "ADST 9:
    Defining: Choose a design opportunity", so a deck holding several courses' competencies (many
    of them worded alike) can tell them apart, and searching for a course finds its competencies. """

    def label_from_instance(self, obj):
        """ Returns the competency's qualified name. """
        return obj.qualified_name


class QuestCompetenciesSelect2Widget(Select2MultipleWidget):
    """ The quest form's competency chips. Its media carries the script that shows a
    default-level picker for each selected competency, so the script only loads on pages
    where the field exists (that is, when the deck has competencies enabled).

    Each option's full "Course: Category: Competency" text is also its title, which select2 shows on
    hover: the dropdown rows and chips are cut to one line by CSS (custom_common.css), rather than the
    text being shortened, so a search still matches every word of it. """

    class Media:
        js = ('competencies/js/quest-competency-levels.js',)

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        """ Returns the option for one competency, titled with its full label. """
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        option['attrs']['title'] = label
        return option


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
        """ Populates the bundled_set choices from the datasets shipped in the app's
        data/ directory, labelled by each set's name and listed alphabetically by it (so a
        course's grades sit together), on top of the standard form args/kwargs.
        """
        super().__init__(*args, **kwargs)
        sets = sorted(((load_bundled_set(key)['name'] or key, key) for key in get_bundled_set_keys()), key=lambda s: s[0].lower())
        self.fields['bundled_set'].choices = [('', '---------')] + [(key, name) for name, key in sets]

    def clean(self):
        """ Validates that exactly one source was provided (a bundled set OR an uploaded
        file), parses it, and returns cleaned_data with the parsed, normalized set added
        under the 'competency_set' key.

        Raises:
            ValidationError: if neither/both sources are given or the file is malformed.
        """
        cleaned_data = super().clean()
        bundled_key = cleaned_data.get('bundled_set')
        file = cleaned_data.get('file')

        if bool(bundled_key) == bool(file):
            raise ValidationError("Choose a bundled competency set or upload a file (but not both).")

        # raises ValidationError with a user-facing message on malformed files
        cleaned_data['competency_set'] = load_bundled_set(bundled_key) if bundled_key else parse_uploaded_file(file)

        return cleaned_data


class QuestCompetenciesFormMixin:
    """ Adds a quest's competencies to a quest ModelForm, for decks with competencies enabled.

    The form gets a multi-select of the deck's competencies and, for each one, a default-level
    field (the level that completing the quest generally demonstrates), then the quest's "Ask for
    a self-assessment" checkbox (Quest.competency_self_assessment, which the form's Meta lists).
    The page shows the level picker only for the selected competencies; unselected ones' level
    fields are ignored. With the feature flag off, none of these fields exist, so the form is
    unchanged.

    The form must call ``add_competency_fields()`` from its ``__init__`` (after
    ``super().__init__``) and place the layout objects it returns.
    """

    competencies_enabled = False

    def add_competency_fields(self):
        """ Add the competency fields, if the deck has competencies enabled.

        Offered competencies are the active ones plus any deactivated ones already linked to
        this quest, so editing a quest never silently drops a link it already has.

        Returns:
            list: crispy layout objects rendering the fields (empty when the flag is off).
        """
        config = SiteConfig.get()
        if config is None or not config.enable_competencies:
            # a quest's self-assessment setting is meaningless without competencies, and absent
            # from the form, it keeps whatever it was
            self.fields.pop(SELF_ASSESSMENT_FIELD, None)
            return []
        self.competencies_enabled = True

        quest = self.instance
        links = {link.competency_id: link for link in quest.quest_competencies.all()} if quest.pk else {}
        queryset = Competency.objects.filter(Q(active=True) | Q(pk__in=links))

        self.fields[COMPETENCIES_FIELD] = CompetencyMultipleChoiceField(
            queryset=queryset,
            required=False,
            initial=list(links),
            widget=QuestCompetenciesSelect2Widget(attrs={'data-theme': 'bootstrap'}),
            help_text="The competencies that students show evidence of by completing this quest. "
                      "Set the default proficiency level for each below; teachers can adjust it per student when approving.",
        )

        labels = config.get_competency_scale_labels()
        level_choices = [(level, labels[level]) for level in ProficiencyLevel.values]
        self.competency_level_fields = []
        for competency in queryset:
            name = competency_level_field_name(competency.pk)
            link = links.get(competency.pk)
            self.fields[name] = forms.TypedChoiceField(
                choices=level_choices,
                coerce=int,
                empty_value=None,
                required=False,
                initial=link.default_level if link else ProficiencyLevel.PROFICIENT,
                label=competency.name,
                widget=forms.Select(attrs={'class': 'form-control input-sm'}),
            )
            self.competency_level_fields.append((competency, name))

        layout = [COMPETENCIES_FIELD, HTML("{% include 'competencies/snippets/quest_competency_levels.html' %}")]
        if SELF_ASSESSMENT_FIELD in self.fields:
            layout.append(SELF_ASSESSMENT_FIELD)
        return layout

    def competency_levels(self):
        """ The default-level pickers for the template, marking which competencies are selected
        (the page shows only those rows, and hides the table when none are).

        Returns:
            dict: 'rows', a list of (Competency, BoundField, selected) per offered competency,
            and 'any_selected'.
        """
        selected = {str(pk) for pk in (self[COMPETENCIES_FIELD].value() or [])}
        rows = [(competency, self[name], str(competency.pk) in selected) for competency, name in self.competency_level_fields]
        return {'rows': rows, 'any_selected': any(row[2] for row in rows)}

    def save(self, commit=True):
        """ Save the quest and, when committing, its competency links (see save_competencies), in
        one transaction so a failure saving the links doesn't leave the quest saved without them.

        Args:
            commit (bool): passed through to ``ModelForm.save``; with commit=False the caller
                saves the quest and then calls ``save_competencies`` itself.

        Returns:
            Quest: the saved (or unsaved, with commit=False) quest.
        """
        if not commit:
            return super().save(commit=False)
        with transaction.atomic():
            quest = super().save()
            self.save_competencies(quest)
        return quest

    def save_competencies(self, quest):
        """ Make the quest's competency links match the form: add links for newly selected
        competencies, update changed default levels, and remove deselected links. Does nothing
        when the deck has competencies disabled.

        Args:
            quest (Quest): the saved quest the links belong to.
        """
        if not self.competencies_enabled:
            return

        existing = {link.competency_id: link for link in quest.quest_competencies.all()}
        for competency in self.cleaned_data[COMPETENCIES_FIELD]:
            level = self.cleaned_data.get(competency_level_field_name(competency.pk)) or ProficiencyLevel.PROFICIENT
            link = existing.pop(competency.pk, None) or QuestCompetency(quest=quest, competency=competency)
            if link.pk is None or link.default_level != level:
                link.default_level = level
                link.full_clean()
                link.save()

        # whatever is left was deselected
        QuestCompetency.objects.filter(pk__in=[link.pk for link in existing.values()]).delete()


class CompetencyOverrideForm(forms.Form):
    """ A teacher's override of a student's level in a competency (CompetencyOverride): a level on the
    deck's Proficiency Scale, or none to clear the override, with a note for staff. """

    level = forms.TypedChoiceField(
        coerce=int, empty_value=None, required=False, label="Current level",
        help_text="This level stands as the student's current level in the competency, wherever it shows, "
                  "until you change or clear it.",
    )
    note = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}), required=False,
        help_text="Why you set it, kept with the level's history. Only staff see this note.",
    )

    def __init__(self, *args, labels, **kwargs):
        """ Offers the levels by the deck's labels, after the choice to clear the override.

        Args:
            *args: positional arguments passed through to ``forms.Form``.
            labels (dict[int, str]): the deck's label for each level (SiteConfig.get_competency_scale_labels).
            **kwargs: keyword arguments passed through to ``forms.Form``.
        """
        super().__init__(*args, **kwargs)
        self.fields['level'].choices = [('', "No override: the level worked out from the evidence")] + list(labels.items())
