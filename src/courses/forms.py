from django import forms

from .models import CourseStudent, Semester


class CourseStudentForm(forms.ModelForm):
    # filtering the available options in a foreign key choice field
    # http://stackoverflow.com/questions/15608784/django-filter-the-queryset-of-modelchoicefield
    def __init__(self, *args, **kwargs):
        super(CourseStudentForm, self).__init__(*args, **kwargs)
        self.fields['semester'].queryset = Semester.objects.get_current(as_queryset=True)
        self.fields['semester'].empty_label = None

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
