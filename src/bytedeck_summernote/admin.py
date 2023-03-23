from django.db import models
from django.contrib import admin
from django.contrib.admin.options import InlineModelAdmin

from .widgets import ByteDeckSummernoteAdvancedWidget, ByteDeckSummernoteSafeWidget


class ByteDeckSummernoteModelAdminMixin:
    summernote_fields = '__all__'

    def formfield_for_dbfield(self, db_field, *args, **kwargs):
        """Override `SummernoteModelAdminMixin` class by injecting customized version of SummernoteWidget(s)"""
        from django_summernote.utils import get_config

        summernote_widget = ByteDeckSummernoteAdvancedWidget if get_config()['iframe'] else ByteDeckSummernoteSafeWidget

        if self.summernote_fields == '__all__':
            if isinstance(db_field, models.TextField):
                kwargs['widget'] = summernote_widget
        else:
            if db_field.name in self.summernote_fields:
                kwargs['widget'] = summernote_widget

        return super().formfield_for_dbfield(db_field, *args, **kwargs)


class ByteDeckSummernoteInlineModelAdmin(ByteDeckSummernoteModelAdminMixin, InlineModelAdmin):
    pass


class ByteDeckSummernoteModelAdmin(ByteDeckSummernoteModelAdminMixin, admin.ModelAdmin):
    pass
