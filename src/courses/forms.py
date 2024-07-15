from django import forms

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Layout
from crispy_forms.bootstrap import Accordion, AccordionGroup
from bootstrap_datepicker_plus.widgets import DateTimePickerInput, TimePickerInput

from .models import Block, Course, CourseStudent, MarkRange, Semester, ExcludedDate
from siteconfig.models import SiteConfig


class MarkRangeForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['courses'].help_text = MarkRange._meta.get_field('courses').help_text + " Hold down “Control”, or “Command” on a Mac, to \
            select more than one."
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Div(
                'name',
                'minimum_mark',
                'active',
                Accordion(
                    AccordionGroup(
                        "Advanced",
                        'color_light',
                        'color_dark',
                        'days',
                        'courses',
                        active=False,
                        template="crispy_forms/bootstrap3/accordion-group.html"
                    ),
                )
            ),
            HTML('<input type="submit" value="{{ submit_btn_value }}" class="btn btn-success"/>'),
            HTML('<a href="{% url "courses:markranges" %}" role="button" class="btn btn-danger">Cancel</a>')
        )

    class Meta:
        model = MarkRange
        fields = ['name', 'minimum_mark', 'active', 'color_light', 'color_dark', 'days', 'courses']


class CourseStudentForm(forms.ModelForm):
    # filtering the available options in a foreign key choice field
    # http://stackoverflow.com/questions/15608784/django-filter-the-queryset-of-modelchoicefield
    def __init__(self, *args, **kwargs):
        student_registration = kwargs.pop('student_registration', None)
        super().__init__(*args, **kwargs)

        semester_qs = Semester.objects.get_current(as_queryset=True)
        self.fields['semester'].queryset = semester_qs
        self.fields['semester'].empty_label = None

        courses_qs = Course.objects.filter(active=True)
        self.fields['course'].queryset = courses_qs

        block_qs = Block.objects.filter(active=True)
        self.fields['block'].queryset = block_qs
        self.fields['block'].label = SiteConfig.get().custom_name_for_group

        # if there is only one option for the fields, then make them default by removing the blank option
        # then if simple_registration is true, hide the field
        # simple_registration is true when the setting is enabled in config and the view being accessed is the student course self-registration view
        simple_registration = SiteConfig.get().simplified_course_registration and student_registration

        # semester field already sets a default, so only check for simple_registration
        if semester_qs.count() == 1 and simple_registration:
            self.fields['semester'].widget = forms.HiddenInput()

        if courses_qs.count() == 1:
            self.fields['course'].empty_label = None
            if simple_registration:
                self.fields['course'].widget = forms.HiddenInput()

        if block_qs.count() == 1:
            self.fields['block'].empty_label = None
            if simple_registration:
                self.fields['block'].widget = forms.HiddenInput()

    # http://stackoverflow.com/questions/32260785/django-validating-unique-together-constraints-in-a-modelform-with-excluded-fiel/32261039#32261039
    def full_clean(self):
        super().full_clean()
        try:
            self.instance.validate_unique()
        except forms.ValidationError as e:
            self._update_errors(e)
        #
        #         # Passing parameters to forms (w/CBV in comments).
        #         # http://stackoverflow.com/questions/7299973/django-how-to-access-current-request-user-in-modelform
        #

    class Meta:
        model = CourseStudent
        fields = ['semester', 'block', 'course']
    #         exclude = ['user', 'active']
    #         # widgets = {'user': forms.HiddenInput()}


class CourseStudentStaffForm(CourseStudentForm):

    class Meta:
        model = CourseStudent
        exclude = ['user', 'active', 'grade_fk']


class SemesterForm(forms.ModelForm):

    class Meta:
        model = Semester
        fields = ('first_day', 'last_day')
        widgets = {
            'first_day': DateTimePickerInput(format='%Y-%m-%d'),
            'last_day': DateTimePickerInput(format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper(self)
        self.helper.include_media = False
        self.helper.disable_csrf = True
        self.helper.form_tag = False

        self.helper.layout = Layout(
            Div('first_day', css_class='col-xs-6 col-sm-4',),
            Div('last_day', css_class='col-xs-6 col-sm-4',),
        )


class ExcludedDateForm(forms.ModelForm):

    class Meta:
        model = ExcludedDate
        fields = ['date', 'label']
        widgets = {
            'date': DateTimePickerInput(format='%Y-%m-%d'),
        }
        help_texts = {
            'label': None
        }

    def __init__(self, *args, **kwargs):
        self.semester_instance = kwargs.pop('semester')
        super().__init__(*args, **kwargs)

        self.fields['label'].label = ''
        self.fields['label'].required = False

        self.fields['date'].label = ''
        self.fields['date'].required = True

    def save(self, **kwargs):
        excluded_date = self.instance
        excluded_date.semester = self.semester_instance

        return excluded_date.save()  # formset saves the rest in its own function


class ExcludedDateFormsetHelper(FormHelper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.include_media = False
        self.disable_csrf = True
        self.form_tag = False

        self.layout = Layout(
            # formset injected vars
            'id',
            'DELETE',
            # form vars
            Div('date', css_class='col-xs-4 col-sm-3',),
            Div('label', css_class='col-xs-6 col-sm-4',),
        )


class BaseFormSet(forms.BaseModelFormSet):
    def add_fields(self, form, index):
        super().add_fields(form, index)
        form.fields['DELETE'].widget = forms.HiddenInput()


ExcludedDateFormset = forms.modelformset_factory(model=ExcludedDate, form=ExcludedDateForm, formset=BaseFormSet, can_delete=True, extra=1)


class BlockForm(forms.ModelForm):

    class Meta:
        model = Block
        fields = '__all__'
        widgets = {
            'start_time': TimePickerInput,
            'end_time': TimePickerInput
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['current_teacher'].initial = SiteConfig.get().deck_owner.pk
