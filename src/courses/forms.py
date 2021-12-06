from django import forms

from bootstrap_datepicker_plus.widgets import DateTimePickerInput, TimePickerInput

from .models import Block, Course, CourseStudent, Semester


class CourseStudentForm(forms.ModelForm):
    # filtering the available options in a foreign key choice field
    # http://stackoverflow.com/questions/15608784/django-filter-the-queryset-of-modelchoicefield
    def __init__(self, *args, **kwargs):
        super(CourseStudentForm, self).__init__(*args, **kwargs)
        self.fields['semester'].queryset = Semester.objects.get_current(as_queryset=True)
        self.fields['semester'].empty_label = None

        courses_qs = Course.objects.filter(active=True)
        self.fields['course'].queryset = courses_qs
        
        # if there is only one option for the fields, then make them default by removing the blank option:
        if Block.objects.count() == 1:
            self.fields['block'].empty_label = None
        if courses_qs.count() == 1:
            self.fields['course'].empty_label = None

    # http://stackoverflow.com/questions/32260785/django-validating-unique-together-constraints-in-a-modelform-with-excluded-fiel/32261039#32261039
    def full_clean(self):
        super(CourseStudentForm, self).full_clean()
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
        fields = ['semester', 'block', 'course', 'grade_fk']
    #         exclude = ['user', 'active']
    #         # widgets = {'user': forms.HiddenInput()}


class SemesterForm(forms.ModelForm):

    class Meta:
        model = Semester
        fields = ('first_day', 'last_day')
        widgets = {
            'first_day': DateTimePickerInput(format='%Y-%m-%d'),
            'last_day': DateTimePickerInput(format='%Y-%m-%d'),
        }


class BlockForm(forms.ModelForm):

    class Meta:
        model = Block
        fields = '__all__'
        widgets = {
            'start_time': TimePickerInput,
            'end_time': TimePickerInput
        }
