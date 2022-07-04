
from django.contrib.auth.mixins import LoginRequiredMixin
# from django.urls import reverse_lazy
from django.views.generic import DetailView
# from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.views.generic.list import ListView
from badges.models import Badge
from quest_manager.models import Quest

# from utilities.forms import TagForm, 
from tenant.views import NonPublicOnlyViewMixin

# from dal import autocomplete
from taggit.models import Tag

# USE GENERIC utilities.views.ModelAutoComplete instead, might need this in the future if further customization is needed
# class TagAutocomplete(autocomplete.Select2QuerySetView):
#     """ https://django-autocomplete-light.readthedocs.io/en/master/taggit.html#view-example
#     """
#     def get_queryset(self):
#         # Don't forget to filter out results depending on the visitor !
#         if not self.request.user.is_authenticated:
#             return Tag.objects.none()

#         # order_by() added to prevent this warning:
#         # UnorderedObjectListWarning: Pagination may yield inconsistent results with an unordered object_list: <class 'taggit.models.Tag'> QuerySet.
#         qs = Tag.objects.all().order_by('name')

#         if self.q:
#             qs = qs.filter(name__istartswith=self.q)

#         return qs


class TagList(NonPublicOnlyViewMixin, LoginRequiredMixin, ListView):
    template_name = 'tags/list.html'
    model = Tag


class TagDetail(NonPublicOnlyViewMixin, LoginRequiredMixin, DetailView):
    template_name = 'tags/detail.html'
    model = Tag

    def get_context_data(self, **kwargs):
        kwargs['quests'] = Quest.objects.filter(tags__name=self.object.name)
        kwargs['badges'] = Badge.objects.filter(tags__name=self.object.name)

        return super().get_context_data(**kwargs)


# @method_decorator(staff_member_required, name='dispatch')
# class TagCreate(NonPublicOnlyViewMixin, CreateView):
#     model = Tag
#     form_class = MenuItemForm
#     success_url = reverse_lazy('utilities:menu_items')

#     def get_context_data(self, **kwargs):
#         kwargs['heading'] = 'Create New Menu Item'
#         kwargs['submit_btn_value'] = 'Create'

#         return super().get_context_data(**kwargs)


# @method_decorator(staff_member_required, name='dispatch')
# class TagUpdate(NonPublicOnlyViewMixin, UpdateView):
#     model = MenuItem
#     form_class = MenuItemForm
#     success_url = reverse_lazy('utilities:menu_items')

#     def get_context_data(self, **kwargs):
#         kwargs['heading'] = 'Update Menu Item'
#         kwargs['submit_btn_value'] = 'Update'

#         return super().get_context_data(**kwargs)


# @method_decorator(staff_member_required, name='dispatch')
# class TagDelete(NonPublicOnlyViewMixin, DeleteView):
#     model = MenuItem
#     success_url = reverse_lazy('utilities:menu_items')
