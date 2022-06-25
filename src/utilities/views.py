from django.shortcuts import render

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.flatpages.models import FlatPage
from django.contrib.sites.models import Site
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.views.generic.list import ListView

from .models import MenuItem, VideoResource
from utilities.forms import MenuItemForm, VideoForm, CustomFlatpageForm
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
class MenuItemList(NonPublicOnlyViewMixin, LoginRequiredMixin, ListView):
    model = MenuItem


@method_decorator(staff_member_required, name='dispatch')
class MenuItemCreate(NonPublicOnlyViewMixin, CreateView):
    model = MenuItem
    form_class = MenuItemForm
    success_url = reverse_lazy('utilities:menu_items')

    def get_context_data(self, **kwargs):
        kwargs['heading'] = 'Create New Menu Item'
        kwargs['submit_btn_value'] = 'Create'

        return super().get_context_data(**kwargs)


@method_decorator(staff_member_required, name='dispatch')
class MenuItemUpdate(NonPublicOnlyViewMixin, UpdateView):
    model = MenuItem
    form_class = MenuItemForm
    success_url = reverse_lazy('utilities:menu_items')

    def get_context_data(self, **kwargs):
        kwargs['heading'] = 'Update Menu Item'
        kwargs['submit_btn_value'] = 'Update'

        return super().get_context_data(**kwargs)


@method_decorator(staff_member_required, name='dispatch')
class MenuItemDelete(NonPublicOnlyViewMixin, DeleteView):
    model = MenuItem
    success_url = reverse_lazy('utilities:menu_items')


@method_decorator(staff_member_required, name='dispatch')
class FlatPageCreateView(NonPublicOnlyViewMixin, CreateView):
    model = FlatPage
    form_class = CustomFlatpageForm
    template_name = "flatpages/flatpage-form.html"

    def get_success_url(self):
        return reverse('utilities:flatpage_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Create"
        context['heading_title'] = "Create New Custom Page"
        return context 

    def get_form_kwargs(self, *args, **kwargs):
        fkwargs = super().get_form_kwargs(*args, **kwargs)
        fkwargs["initial"] = {"sites": [Site.objects.first().pk]}
        return fkwargs


@method_decorator(staff_member_required, name='dispatch')
class FlatPageUpdateView(NonPublicOnlyViewMixin, UpdateView):
    model = FlatPage
    form_class = CustomFlatpageForm
    template_name = "flatpages/flatpage-form.html"
    context_object_name = 'flatpage'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "Update"
        context['heading_title'] = "Update Custom Page"
        return context


@method_decorator(staff_member_required, name='dispatch')
class FlatPageDeleteView(NonPublicOnlyViewMixin, DeleteView):
    model = FlatPage
    template_name = "flatpages/flatpage-delete.html"
    context_object_name = 'flatpage'
    success_url = reverse_lazy('utilities:flatpage_list')


class FlatPageListView(NonPublicOnlyViewMixin, ListView):
    model = FlatPage
    template_name = "flatpages/flatpage-list.html"
    context_object_name = 'flatpages'

    def get_queryset(self):
        return FlatPage.objects.all().order_by("title")
