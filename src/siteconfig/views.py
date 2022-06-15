from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.messages.views import SuccessMessageMixin
from django.utils.decorators import method_decorator
from django.views.generic.edit import UpdateView

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


class SiteConfigUpdateOwn(SiteConfigUpdate):

    def get_object(self):
        return SiteConfig.get()
