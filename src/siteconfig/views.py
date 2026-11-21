from django.contrib.messages.views import SuccessMessageMixin
from django.utils.decorators import method_decorator
from django.views.generic.edit import UpdateView

from competencies.assessments import queue_conditions_update_for_everyone
from hackerspace_online.decorators import staff_member_required

from .models import SiteConfig
from .forms import SiteConfigForm


@method_decorator(staff_member_required, name='dispatch')
class SiteConfigUpdate(SuccessMessageMixin, UpdateView):
    model = SiteConfig
    form_class = SiteConfigForm
    success_message = 'Settings updated successfully!'

    def get_form_kwargs(self, **kwargs):
        fkwargs = super().get_form_kwargs(**kwargs)
        fkwargs['is_deck_owner'] = self.request.user.pk == SiteConfig.get().deck_owner.pk

        return fkwargs

    def get_context_data(self, **kwargs):
        kwargs['submit_btn_value'] = 'Update'
        return super().get_context_data(**kwargs)

    def form_valid(self, form):
        """ Saves the settings. A change to how competency levels roll up changes every student's current
        levels, so their available quests are recalculated when a prerequisite asks for a level. """
        response = super().form_valid(form)
        if {'competency_rollup', 'competency_rollup_count'} & set(form.changed_data):
            queue_conditions_update_for_everyone()
        return response


class SiteConfigUpdateOwn(SiteConfigUpdate):

    def get_object(self):
        return SiteConfig.get()
