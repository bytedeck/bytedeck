from collections import OrderedDict

from django.http import Http404, JsonResponse
from django.conf import settings
from django.shortcuts import render

from django.core import signing
from django.core.signing import BadSignature
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.contrib.flatpages.models import FlatPage
from django.contrib.sites.models import Site
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.views.generic.list import ListView
from django.template.defaultfilters import capfirst

from hackerspace_online.decorators import staff_member_required

from .models import MenuItem, VideoResource
from utilities.forms import MenuItemForm, VideoForm, CustomFlatpageForm
from tenant.views import non_public_only_view, NonPublicOnlyViewMixin

from django_select2.views import AutoResponseView
from queryset_sequence import QuerySetSequence


class QuerySetSequenceAutoResponseView(AutoResponseView):
    """
    View that handles requests from ContentObjectSelect2Widget widgets.

    The view only supports HTTP's GET method.

    """
    context_object_name = 'objects'

    def get(self, request, *args, **kwargs):
        """
        This is needed because `django_select2.views.AutoResponseView`
        returns primary keys of selected options, and the ContentObjectChoiceField
        expects ctypeid-objectid for result.

        Return a :class:`.django.http.JsonResponse`.

        Example::
            {
                'results': [
                    {
                        'text': "foo",
                        'id': "1-23"
                    }
                ],
                'more': true
            }
        """
        self.widget = self.get_widget_or_404()
        self.term = kwargs.get('term', request.GET.get('term', ''))
        self.object_list = self.get_queryset()
        context = self.get_context_data()

        groups = OrderedDict()

        for result in context['object_list']:
            groups.setdefault(type(result), [])
            groups[type(result)].append(result)

        return JsonResponse({
            'results': [
                {
                    'id': None,
                    'text': capfirst(self.get_model_name(model)),
                    'children': [{
                        'id': self.get_result_value(result),
                        'text': self.widget.label_from_instance(result),
                    } for result in results]
                } for model, results in groups.items()
            ],
            'more': context['page_obj'].has_next()
        })

    def get_result_value(self, result):
        """Return ctypeid-objectid for result."""
        return '{}-{}'.format(
            ContentType.objects.get_for_model(result).pk,
            result.pk,
        )

    def get_model_name(self, model):
        """Return the name of the model, fetch parent if model is a proxy."""
        if model._meta.proxy:
            try:
                model = list(model._meta.parents.keys())[0]
            except IndexError:
                pass
        return model._meta.verbose_name

    def get_widget_or_404(self):
        """
        Get and return widget from cache.

        Raises:
            Http404: If the widget can not be found or no id is provided.

        Returns:
            ContentObjectSelect2Widget: Widget from cache.

        """
        from django_select2.cache import cache

        field_id = self.kwargs.get('field_id', self.request.GET.get('field_id', None))
        if not field_id:
            raise Http404('No "field_id" provided.')
        try:
            key = signing.loads(field_id)
        except BadSignature:
            raise Http404('Invalid "field_id".')
        else:
            cache_key = f'{settings.SELECT2_CACHE_PREFIX}{key}'
            widget_dict = cache.get(cache_key)
            if widget_dict is None:
                raise Http404('field_id not found')
            if widget_dict.pop('url') != self.request.path:
                raise Http404('field_id was issued for the view.')
        queryset = QuerySetSequence(*[qs.all() for qs, qs.query in widget_dict.pop('queryset')])
        self.queryset = queryset
        widget_dict['queryset'] = self.queryset
        widget_cls = widget_dict.pop('cls')
        return widget_cls(**widget_dict)


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
