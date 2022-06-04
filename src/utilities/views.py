from django.shortcuts import render

from django.urls import reverse
from django.views.generic import ListView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.contrib.sites.models import Site
from django.contrib.flatpages.models import FlatPage

from .models import VideoResource
from utilities.forms import VideoForm, CustomFlatpageForm
from tenant.views import non_public_only_view, NonPublicOnlyViewMixin


@non_public_only_view
def videos(request):
    videos = VideoResource.objects.all()
    form = VideoForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        form.save()
    context = {'videos': videos, 'heading': "Video Resources", 'form': form}
    return render(request, 'utilities/videos.html', context)


@method_decorator(staff_member_required, name='dispatch')
class FlatPageCreateView(NonPublicOnlyViewMixin, CreateView):
    model = FlatPage
    form_class = CustomFlatpageForm
    template_name = "flatpages/flatpage-form.html"

    def get_success_url(self):
        return reverse('utilities:flatpage-list')

    def post(self, request, *args, **kwargs):
        post = request.POST.copy()
        post["sites"] = [Site.objects.first().pk]
        request.POST = post

        return super(FlatPageCreateView, self).post(request, *args, **kwargs)


@method_decorator(staff_member_required, name='dispatch')
class FlatPageUpdateView(NonPublicOnlyViewMixin, UpdateView):
    model = FlatPage
    form_class = CustomFlatpageForm
    template_name = "flatpages/flatpage-form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['update'] = True
        context['flatpage'] = self.get_object()
        return context


@method_decorator(staff_member_required, name='dispatch')
class FlatPageDeleteView(NonPublicOnlyViewMixin, DeleteView):
    model = FlatPage
    template_name = "flatpages/flatpage-delete.html"

    def get_success_url(self):
        return reverse('utilities:flatpage-list')


class FlatPageListView(NonPublicOnlyViewMixin, ListView):
    model = FlatPage
    template_name = "flatpages/flatpage-list.html"
    context_object_name = 'flatpages'

    def get_queryset(self):
        return FlatPage.objects.all()
