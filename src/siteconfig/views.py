from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.messages.views import SuccessMessageMixin
from django.utils.decorators import method_decorator
from django.views.generic.edit import UpdateView

from .models import SiteConfig


@method_decorator(staff_member_required, name='dispatch')
class SiteConfigUpdate(SuccessMessageMixin, UpdateView):
    model = SiteConfig
    fields = '__all__'
    success_message = 'Settings updated successfully!'


class SiteConfigUpdateOwn(SiteConfigUpdate):

    def get_object(self):
        return SiteConfig.get()
