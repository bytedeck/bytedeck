from django import forms
from django.forms.formsets import DELETION_FIELD_NAME

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Layout
from crispy_forms.bootstrap import Accordion, AccordionGroup
from bootstrap_datepicker_plus.widgets import DatePickerInput, TimePickerInput
from django_select2.forms import Select2Widget

from .models import Block, Course, CourseStudent, MarkRange, Rank, Semester, ExcludedDate
from siteconfig.models import SiteConfig
from utilities.fa_icon_widget import FontAwesomeIconPickerWidget, FontAwesomeModifierPickerWidget


class XPCourseChoiceMixin:
    """Asks the student which of their courses this submission's XP counts toward (issue #2440).

    They can also decline to choose: "split evenly between my courses" is the first option and
    the one selected by default, so a student who ignores the question gets the even split that
    every submission used to get.

    The field is only worth showing when there is a choice to make, so it is dropped when the
    deck has the setting off, when the student is in a single course, and when no student is in
    view at all (a staff form). Dropping it leaves the submission unassigned, which is the same
    thing as splitting it.
    """

    #: Asked the same way of everyone, so the question reads identically whether a student is
    #: handing in a quest or a teacher is granting a badge.
    label = 'Which course should this XP be awarded to?'

    #: Wording of the "do not assign this to a course" choice, which teacher-facing forms
    #: override, since they are choosing on someone else's behalf.
    split_evenly_label = 'Split evenly between my courses'

    def __init__(self, *args, student=None, **kwargs):
        """
        Args:
            student (User): whose courses to offer. None for a form no student fills in,
                or one where the student is picked on the form itself and so is not yet known.
        """
        super().__init__(*args, **kwargs)
        registrations = CourseStudent.objects.current_courses(student) if student else None
        courses = Course.objects.filter(id__in=registrations.values_list('course_id', flat=True)) if student else None

        if not student or not SiteConfig.get().students_choose_xp_course or courses.count() < 2:
            del self.fields['course']
            return

        field = self.fields['course']
        field.label = self.label
        # the label asks the whole question, so a line of help text under it would only repeat it
        field.help_text = ''
        # the same select2 dropdown the other fields on these pages use (both templates already
        # render the form's media), so the question does not stand out as a different kind of
        # box. select2 draws an optional field's empty choice as its placeholder, so the
        # "split evenly" wording has to be handed over as one or the box reads blank.
        field.widget = Select2Widget(attrs={
            'data-theme': 'bootstrap',
            'data-placeholder': self.split_evenly_label,
        })
        # "split evenly" is the empty choice, and it is what a submission with no course does
        # anyway, so it needs no separate value and is the safe thing to leave selected: a
        # student who does not think about the question gets the old behaviour. Assigning the
        # queryset last hands the choices, empty label included, to the widget set above.
        field.empty_label = self.split_evenly_label
        field.queryset = courses


class NoScriptTagDatePickerInput(DatePickerInput):
    """ Widget to override build_attrs.
    As of bootstrap_datepicker_plus 5.0.0 the widget when rendered comes with script tags if debug=True.
    This script tag breaks the javascript in `semester_form.html`.
    Furthermore, the widget.attrs responsible is 'data-dbdp-debug' which has to be removed. Not set False/True
    to stop the script tag from showing up.
    """
    def build_attrs(self, *args, **kwargs):
        attrs = super().build_attrs(*args, **kwargs)
        attrs.pop('data-dbdp-debug', None)
        return attrs


class RankForm(forms.ModelForm):
    """Rank add/edit form.

    The Font Awesome icon field uses the searchable icon picker
    (:class:`utilities.fa_icon_widget.FontAwesomeIconPickerWidget`), which writes the
    bare icon name. The modifier field sits right below it with toggle buttons for the
    common transforms (rotate, flip, spin, pulse) that a rank might want.
    """

    class Meta:
        """Binds the icon/modifier picker widgets and plain-language labels onto Rank's
        two icon fields (the Font Awesome ``fa_icon``/``fa_icon_modifiers`` and the
        ``icon`` image fallback)."""

        model = Rank
        fields = ['name', 'xp', 'fa_icon', 'fa_icon_modifiers', 'icon']
        widgets = {
            # Tell the picker which field holds the modifiers so its live preview
            # can reflect rotations/flips/etc. as they are toggled or typed.
            'fa_icon': FontAwesomeIconPickerWidget(modifiers_field_name='fa_icon_modifiers'),
            'fa_icon_modifiers': FontAwesomeModifierPickerWidget(),
        }
        labels = {
            # "Fa icon" is jargon; call it "Icon". The ImageField (a fallback used
            # where the font icon can't be, e.g. quest maps) then can't also be
            # "Icon", so it becomes "Backup image".
            'fa_icon': 'Icon',
            'fa_icon_modifiers': 'Icon modifiers',
            'icon': 'Backup image',
        }
        help_texts = {
            'fa_icon_modifiers': 'Optional. Rotate, flip, or animate the icon above.',
            'icon': 'A fallback image, used where the icon above can\'t be (e.g. in the quest maps).',
        }


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
        """Narrow the semester, course and group choices to the ones worth offering.

        Semesters are the open ones, courses and groups the active ones. Under simplified
        registration a field with only one choice is hidden and takes that choice, so a
        student joining the usual single-semester, single-course deck is not asked anything.

        Args:
            student_registration (bool): True when this is a student registering themselves,
                the only case simplified registration applies to. Staff adding a student see
                every field, whatever the setting says.
        """
        student_registration = kwargs.pop('student_registration', None)
        super().__init__(*args, **kwargs)

        # every open semester, so a deck running two cohorts on different calendars lets the
        # student say which one they are joining (issue #2157 Phase 3, #1781). With one open
        # this is the single choice it always was, and stays hidden under simple registration
        semester_qs = Semester.objects.open()
        self.fields['semester'].queryset = semester_qs
        self.fields['semester'].empty_label = None
        # preselect the deck's default rather than whichever semester sorts first: the list is
        # newest term first, so without this a deck pointed at the older of two open semesters
        # would offer the newer one. An instance being edited keeps its own semester, since
        # initial data built from the instance wins over a field's initial.
        self.fields['semester'].initial = SiteConfig.get().open_semester_id

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
    """The registration form as staff edit an existing registration, rather than create one."""

    def __init__(self, *args, **kwargs):
        """Keep the registration's own semester among the choices.

        Offering only the open semesters is right for creating a registration: a student is
        registered into a term that is running. But an archived semester keeps its
        registrations, and a form that does not offer a field's current value cannot be saved
        at all, so correcting the course or the group on a past registration failed validation
        on the semester and there was no way through it (issue #2507).

        This only adds the "leave it where it is" choice. Every open semester was already
        offered, so it does not newly allow moving a registration from one term to another.
        """
        super().__init__(*args, **kwargs)
        if self.instance.semester_id is not None:
            self.fields['semester'].queryset = (
                self.fields['semester'].queryset | Semester.objects.filter(pk=self.instance.semester_id)
            )

    class Meta:
        model = CourseStudent
        exclude = ['user', 'active', 'grade_fk']


class SemesterForm(forms.ModelForm):

    class Meta:
        model = Semester
        fields = ('name', 'first_day', 'last_day')
        widgets = {
            'first_day': DatePickerInput(),
            'last_day': DatePickerInput(),
        }

    def clean(self):
        """Reject semesters whose last day falls before their first day; the date-math
        methods (num_days, get_date, ...) assume a forward date range.

        Adds a validation error on the last_day field when it precedes first_day.

        Returns:
            dict: the form's cleaned_data.
        """
        cleaned_data = super().clean()
        first_day = cleaned_data.get('first_day')
        last_day = cleaned_data.get('last_day')
        if first_day and last_day and last_day < first_day:
            self.add_error('last_day', "The last day of the semester can't be before its first day.")
        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper(self)
        self.helper.include_media = False
        self.helper.disable_csrf = True
        self.helper.form_tag = False

        self.helper.layout = Layout(
            Div('name', css_class='col-xs-4',),
            Div('first_day', css_class='col-xs-4',),
            Div('last_day', css_class='col-xs-4',),
        )


class ExcludedDateForm(forms.ModelForm):

    class Meta:
        model = ExcludedDate
        fields = ['date', 'label']
        widgets = {
            'date': NoScriptTagDatePickerInput(),
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


class BaseExcludedDateFormSet(BaseFormSet):
    """Refuses a semester two excluded dates on the same day.

    A date is unique per semester rather than deck-wide (#2647), and `semester` is not one of
    these forms' fields: `ExcludedDateForm.save` attaches it. Django's own formset uniqueness
    check only covers a constraint whose every field is on the form, so it does not see this
    one, and two rows naming the same day would reach the database as an IntegrityError.

    Comparing the rows against each other is the whole check: the view hands the formset the
    semester's entire `excludeddate_set`, so every date it already has is a form here.
    """

    def clean(self):
        """Fault every row naming a date an earlier row in the formset already claimed."""
        super().clean()

        claimed = set()
        for form in self.forms:
            # A form with no cleaned_data failed its own validation, and a blank extra row or
            # an unparseable date leaves `date` out of it: nothing to compare either way. A row
            # marked for deletion is on its way out, so the day it holds is free to reuse.
            date = getattr(form, 'cleaned_data', {}).get('date')
            if date is None or form.cleaned_data.get(DELETION_FIELD_NAME):
                continue

            if date in claimed:
                form.add_error('date', 'This semester already excludes this date.')
            claimed.add(date)


ExcludedDateFormset = forms.modelformset_factory(
    model=ExcludedDate, form=ExcludedDateForm, formset=BaseExcludedDateFormSet, can_delete=True, extra=1,
)


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
