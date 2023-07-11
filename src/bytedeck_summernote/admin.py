from django.contrib import admin
from django.contrib.admin.options import InlineModelAdmin
from django.db import models

from django_summernote.utils import get_config

from .widgets import ByteDeckSummernoteSafeWidget, ByteDeckSummernoteSafeInplaceWidget
from .widgets import ByteDeckSummernoteAdvancedWidget, ByteDeckSummernoteAdvancedInplaceWidget


class ByteDeckSummernoteModelAdminMixin:
    """
    Simplify upgrading to a newer `django_summernote` widgets in a future.

    """

    summernote_fields = "__all__"

    def formfield_for_dbfield(self, db_field, *args, **kwargs):
        """Override default `SummernoteModelAdminMixin` class by injecting customized version of SummernoteWidget(s)"""
        AdminSummernoteWidget = self.get_summernote_widget_class()

        if self.summernote_fields == "__all__":
            if isinstance(db_field, models.TextField):
                # use class name as CSS class
                kwargs.setdefault("widget", AdminSummernoteWidget(
                    attrs={
                        "class": str(AdminSummernoteWidget.__name__).lower(),
                    }))
        else:
            if db_field.name in self.summernote_fields:
                # use class name as CSS class
                kwargs.setdefault("widget", AdminSummernoteWidget(
                    attrs={
                        "class": str(AdminSummernoteWidget.__name__).lower(),
                    }))

        return super().formfield_for_dbfield(db_field, *args, **kwargs)

    def get_summernote_widget_class(self):
        raise NotImplementedError(
            '%s, must implement "get_summernote_widget_class" method.' % self.__class__.__name__
        )


class ByteDeckSummernoteSafeModelAdminMixin(ByteDeckSummernoteModelAdminMixin):
    def get_summernote_widget_class(self):
        return ByteDeckSummernoteSafeWidget if get_config()["iframe"] else ByteDeckSummernoteSafeInplaceWidget


class ByteDeckSummernoteAdvancedModelAdminMixin(ByteDeckSummernoteModelAdminMixin):
    def get_summernote_widget_class(self):
        return ByteDeckSummernoteAdvancedWidget if get_config()["iframe"] else ByteDeckSummernoteAdvancedInplaceWidget


class ByteDeckSummernoteSafeInlineModelAdmin(ByteDeckSummernoteSafeModelAdminMixin, InlineModelAdmin):
    pass


class ByteDeckSummernoteSafeModelAdmin(ByteDeckSummernoteSafeModelAdminMixin, admin.ModelAdmin):
    pass


class ByteDeckSummernoteAdvancedInlineModelAdmin(ByteDeckSummernoteAdvancedModelAdminMixin, InlineModelAdmin):
    pass


class ByteDeckSummernoteAdvancedModelAdmin(ByteDeckSummernoteAdvancedModelAdminMixin, admin.ModelAdmin):
    pass
