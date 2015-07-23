from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import ListView
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from .models import Announcement
from .forms import AnnouncementForm

# Create your views here.
class List(ListView):
    model = Announcement
    template_name = 'announcements/list.html'

class Create(CreateView):
    model = Announcement
    form_class = AnnouncementForm
    template_name = 'announcements/form.html'

    def form_valid(self, form):
        data = form.save(commit=False)
        data.author = self.request.user
        data.save()
        return super(Create, self).form_valid(form)

class Update(UpdateView):
    model = Announcement
    form_class = AnnouncementForm
    template_name = 'announcements/form_update.html'

    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        return super(Update, self).dispatch(*args, **kwargs)

class Delete(DeleteView):
    model = Announcement
    template_name = 'announcements/delete.html'
    success_url = reverse_lazy('announcements:list')
