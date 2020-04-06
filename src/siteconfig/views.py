from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.views.generic.edit import UpdateView
from .models import SiteConfig


@method_decorator(staff_member_required, name='dispatch')
class SiteConfigUpdate(UpdateView):
    model = SiteConfig
    fields = '__all__'
