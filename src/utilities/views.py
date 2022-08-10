from django.shortcuts import render

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.flatpages.models import FlatPage
from django.contrib.sites.models import Site
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.views.generic.list import ListView

from hackerspace_online.decorators import staff_member_required

from .models import MenuItem, VideoResource
from utilities.forms import MenuItemForm, VideoForm, CustomFlatpageForm
from tenant.views import non_public_only_view, NonPublicOnlyViewMixin

from dal import autocomplete


class ModelAutocomplete(NonPublicOnlyViewMixin, autocomplete.Select2QuerySetView):
    """ 
    DRY autocomplete view for select2 widgets.  Example usage in urls.py with model = Quest
    `path('quest/autocomplete/', utilities.views.ModelAutocomplete.as_view(model=Quest), name='quest_autocomplete')`

    https://django-autocomplete-light.readthedocs.io/en/master/tutorial.html#create-an-autocomplete-view
    """

    def get_queryset(self):
        # Don't forget to filter out results depending on the visitor !
        if not self.request.user.is_authenticated:
            return self.model.objects.none()

        # if model doesn't have a 'name' then try 'title'
        search_field = 'name' if hasattr(self.model, 'name') else 'title'

        # order_by() added to prevent this warning:
        # UnorderedObjectListWarning: Pagination may yield inconsistent results with an unordered object_list: <class '<some model here>'> QuerySet.
        qs = self.model.objects.all().order_by(search_field)

        if self.q:  # If a GET search query was provided (autocomplete/?q=thing), then filter on it
            filter_kwargs = {f'{search_field}__icontains': self.q}
            qs = qs.filter(**filter_kwargs)

        return qs


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
