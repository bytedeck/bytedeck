from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.contrib.contenttypes.forms import generic_inlineformset_factory
from django.utils.decorators import method_decorator
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages

from tenant.views import NonPublicOnlyViewMixin
from prerequisites.forms import PrereqFormInline, PrereqFormsetHelper
from prerequisites.models import Prereq
from django.views.generic.detail import SingleObjectMixin
from django.views.generic.edit import FormView


@method_decorator(staff_member_required, name='dispatch')
class ObjectPrereqsFormView(NonPublicOnlyViewMixin, SingleObjectMixin, FormView):
    model = None  # Needs to be set by the inheriting form class
    template_name = 'prerequisites/advanced_prereqs_form.html'
    ObjectPrereqFormset = generic_inlineformset_factory(
        model=Prereq, 
        form=PrereqFormInline, 
        ct_field='parent_content_type',
        fk_field='parent_object_id',
        extra=1,
    )  

    def get(self, request, *args, **kwargs):
        self.object = self.get_object(queryset=self.model.objects.all())
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object(queryset=self.model.objects.all())

        if "cancel" in request.POST:
            return redirect(self.object.get_absolute_url())

        return super().post(request, *args, **kwargs)

    def get_form(self, form_class=None):
        self.ObjectPrereqFormset.helper = PrereqFormsetHelper()
        return self.ObjectPrereqFormset(**self.get_form_kwargs(), instance=self.object)

    def form_valid(self, form):
        form.save()

        messages.success(
            self.request,
            f"Prerequisites have been updated for {self.object}."
        )
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return self.object.get_absolute_url()
