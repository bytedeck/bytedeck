
from datetime import date
from dal import autocomplete

from django import forms
from django.core.exceptions import ValidationError

from bootstrap_datepicker_plus.widgets import DatePickerInput, TimePickerInput
from crispy_forms.bootstrap import Accordion, AccordionGroup
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Layout
from django_summernote.widgets import SummernoteInplaceWidget
from django_select2.forms import ModelSelect2MultipleWidget
from tags.forms import BootstrapTaggitSelect2Widget

from utilities.fields import RestrictedFileFormField
from badges.models import Badge
from .models import Category, Quest, CommonData


class BadgeLabel:
    def label_from_instance(self, obj):
        return "{} ({} XP)".format(str(obj), obj.xp)


class BadgeSelect2MultipleWidget(BadgeLabel, ModelSelect2MultipleWidget):
    pass


class QuestForm(forms.ModelForm):

    new_quest_prerequisite = forms.ModelChoiceField(
        # to_field_name="name",
        required=False,
        queryset=Quest.objects.all(),
        # widget=ModelSelect2Widget(
        #     model=Quest,
        #     search_fields=['name__icontains'],
        # ),
        widget=autocomplete.ModelSelect2(url='quests:quest_autocomplete'),
    )

    new_badge_prerequisite = forms.ModelChoiceField(
        # widget=ModelSelect2Widget(
        #     model=Badge,
        #     search_fields=['name__icontains'],
        # ),
        queryset=Badge.objects.all(),
        # to_field_name="name",
        required=False,
        widget=autocomplete.ModelSelect2(url='badges:badge_autocomplete'),
    )

    campaign = forms.ModelChoiceField(
        queryset=Category.objects.all(),
        required=False,
        limit_choices_to={'active': True}
    )

    class Meta:
        model = Quest
        fields = ('name', 'visible_to_students', 'xp', 'xp_can_be_entered_by_students', 'icon', 'short_description',
                  'verification_required', 'instructions',
                  'campaign', 'common_data', 'submission_details', 'instructor_notes',
                  'repeat_per_semester', 'max_repeats', 'max_xp', 'hours_between_repeats',
                  'map_transition', 'tags',
                  'new_quest_prerequisite',
                  'new_badge_prerequisite',
                  'specific_teacher_to_notify', 'blocking',
                  'hideable', 'sort_order', 'date_available', 'time_available', 'date_expired', 'time_expired',
                  'available_outside_course', 'archived', 'editor')

        date_options = {
            'showMeridian': False,
            # 'todayBtn': True,
            'todayHighlight': True,
            # 'minuteStep': 5,
            'pickerPosition': 'bottom-left',
        }

        time_options = {
            'pickerPosition': 'bottom-left',
            'maxView': 0,
        }

        widgets = {
            'instructions': SummernoteInplaceWidget(),
            'submission_details': SummernoteInplaceWidget(),
            'instructor_notes': SummernoteInplaceWidget(),

            'date_available': DatePickerInput(format='%Y-%m-%d'),

            'time_available': TimePickerInput(),
            'date_expired': DatePickerInput(format='%Y-%m-%d'),
            'time_expired': TimePickerInput(),

            # TODO: Campaign Autocomplete
            # 'campaign': autocomplete.ModelSelect2(url='quests:category_autocomplete'),
            # 'common_data': autocomplete.ModelSelect2(url='quests:commondata_autocomplete'),
            # 'specific_teacher_to_notify': Select2Widget(),

            # dal widgets aren't compatible with django-select2 widget.  Need to convert all to dal.
            'tags': BootstrapTaggitSelect2Widget()
        }

    def __init__(self, *args, **kwargs):
        super(QuestForm, self).__init__(*args, **kwargs)

        self.fields['date_available'].initial = date.today().strftime('%Y-%m-%d'),

        self.fields['common_data'].label = 'Common Quest Info'
        self.fields['common_data'].queryset = CommonData.objects.filter(active=True)

        cancel_btn = '<a href="{{ cancel_url }}" role="button" class="btn btn-danger">Cancel</a> '
        submit_btn = '<input type="submit" value="{{ submit_btn_value }}" class="btn btn-success"/> '

        prereqs_btn = '{% if object.id %}<a role="button" class="btn btn-default" href="{% url \'quests:quest_prereqs_update\' object.id %}">' \
            'Edit Prerequisites</a>' \
            '{% else %}<button type="button" class="btn btn-default" disabled title="You need to create this new quest first, ' \
            'before you can add prerequisites.">Edit Prerequisites</button>' \
            '{% endif %}'
    
        self.helper = FormHelper()
        self.helper.layout = Layout(
            HTML(cancel_btn),
            HTML(submit_btn),
            HTML(prereqs_btn),
            Div(
                'name',
                'xp',
                'xp_can_be_entered_by_students',
                'visible_to_students',
                'verification_required',
                'icon',
                'short_description',
                'instructions',
                'submission_details',
                'instructor_notes',
                'campaign',
                'common_data',
                'max_repeats',
                'hours_between_repeats',
                'tags',
                Accordion(
                    AccordionGroup(
                        "Basic Prerequisites",
                        # TODO This code should be combined with its use in quest_detail_content.html
                        HTML(
                            "<div class='help-block'><p>If you only want to set a single quest and/or badge as a prerequisite, you can set them here."
                            "{% if object.id %} Note that this will overwrite any current prerequisites that are set. </p><p>{% endif %} "
                            "For more advanced prerequisite options you will need to "
                            "{% if request.user.profile.is_TA %} ask a teacher to set them up for you. "
                            "{% elif not object.id %} save this new quest first."
                            "{% else %}use the <a href='{% url \"quests:quest_prereqs_update\" object.id %}'>Advanced Prerequisites Form</a>."
                            "{% endif %}</p></div>"
                            "<div>Current Prerequisites:</div>"
                            "{% include 'prerequisites/current_prereq_list.html' %}",
                        ),
                        'new_quest_prerequisite',
                        'new_badge_prerequisite',
                        active=False,
                        template='crispy_forms/bootstrap3/accordion-group.html',
                    ),
                    AccordionGroup(
                        "Advanced",
                        'map_transition',
                        'max_xp',
                        'repeat_per_semester',
                        'specific_teacher_to_notify',
                        'blocking',
                        'hideable',
                        'sort_order',
                        'date_available',
                        'time_available',
                        'date_expired',
                        'time_expired',
                        'available_outside_course',
                        'archived',
                        'editor',
                        active=False,
                        template='crispy_forms/bootstrap3/accordion-group.html',
                    ),
                ),
                HTML(cancel_btn),
                HTML(submit_btn),
                style="margin-top: 10px;"
            )
        )

    def clean(self):
        cleaned_data = super().clean()

        # make sure blocking quests are not hideable
        blocking = cleaned_data.get('blocking')
        hideable = cleaned_data.get('hideable')

        if blocking and hideable:
            # both fields are valid so far and are True
            raise ValidationError(
                "Blocking quests cannot be Hideable.  In the Advanced section "
                "either turn Hidable off or turn Blocking off."
            )


class TAQuestForm(QuestForm):
    """ Modified QuestForm that removes some fields TAs should not be able to set. """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # SET visible to students here to?
        self.fields['visible_to_students'].widget = forms.HiddenInput()
        self.fields['available_outside_course'].widget = forms.HiddenInput()
        self.fields['archived'].widget = forms.HiddenInput()
        self.fields['editor'].widget = forms.HiddenInput()


class SubmissionForm(forms.Form):
    comment_text = forms.CharField(label='', required=False, widget=SummernoteInplaceWidget())

    attachments = RestrictedFileFormField(required=False,
                                          max_upload_size=16777216,
                                          widget=forms.ClearableFileInput(attrs={'multiple': True}),
                                          label="Attach files",
                                          help_text="Hold Ctrl to select multiple files, 16MB limit per file")


class SubmissionFormCustomXP(SubmissionForm):
    xp_requested = forms.IntegerField(
        label="Requested XP", 
        required=True, 
        help_text="You need to request an XP value for this submission."
    )

    def __init__(self, *args, **kwargs):
        minimum_xp = kwargs.pop('minimum_xp', 0)
        super().__init__(*args, **kwargs)
        self.fields['xp_requested'].widget.attrs['min'] = minimum_xp


class SubmissionFormStaff(SubmissionForm):
    # Queryset needs to be set on creation in __init__(), otherwise bad stuff happens upon initial migration
    awards = forms.ModelMultipleChoiceField(queryset=None, label='Grant Awards', required=False)

    def __init__(self, *args, **kwds):
        super(SubmissionFormStaff, self).__init__(*args, **kwds)

        self.fields['awards'].queryset = Badge.objects.all_manually_granted()
        self.fields['awards'].widget = BadgeSelect2MultipleWidget(
            model=Badge,
            queryset=Badge.objects.all_manually_granted(),
            search_fields=[
                'name__icontains',
            ]
        )


class SubmissionReplyForm(forms.Form):
    comment_text = forms.CharField(label='Reply', widget=forms.Textarea(attrs={'rows': 2}))


class BadgeModelChoiceField(BadgeLabel, forms.ModelChoiceField):
    pass


class SubmissionQuickReplyForm(forms.Form):
    comment_text = forms.CharField(label='', required=False, widget=forms.Textarea(attrs={'rows': 2}))
    # Queryset needs to be set on creation in __init__(), otherwise bad stuff happens upon initial migration
    award = BadgeModelChoiceField(queryset=None, label='Grant an Award', required=False)

    def __init__(self, *args, **kwds):
        super(SubmissionQuickReplyForm, self).__init__(*args, **kwds)
        self.fields['award'].queryset = Badge.objects.all_manually_granted()


class CommonDataForm(forms.ModelForm):

    class Meta:
        model = CommonData
        fields = "__all__"
        widgets = {
            "instructions": SummernoteInplaceWidget()
        }
