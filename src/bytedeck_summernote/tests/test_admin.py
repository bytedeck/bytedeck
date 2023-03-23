from django.db import models
from django.apps import apps
from django.contrib.admin.sites import AdminSite

from django_tenants.test.cases import TenantTestCase


class TestByteDeckSummernoteModelAdmin(TenantTestCase):

    def setUp(self):
        self.username = 'lqez'
        self.password = 'ohmygoddess'
        self.site = AdminSite()

        self.app_config = apps.get_app_config('django_summernote')
        self.app_config.update_config()
        self.summernote_config = self.app_config.config

    def test_admin_model(self):
        from bytedeck_summernote.admin import ByteDeckSummernoteModelAdmin
        from bytedeck_summernote.admin import ByteDeckSummernoteInlineModelAdmin
        from bytedeck_summernote.widgets import ByteDeckSummernoteAdvancedWidget

        class SimpleModel(models.Model):
            foobar = models.TextField()

        class SimpleModelAdmin(ByteDeckSummernoteModelAdmin):
            pass

        ma = SimpleModelAdmin(SimpleModel, self.site)

        assert isinstance(
            ma.get_form(None).base_fields['foobar'].widget,
            ByteDeckSummernoteAdvancedWidget
        )

        class SimpleParentModel(models.Model):
            foobar = models.TextField()

        class SimpleModel2(models.Model):
            foobar = models.TextField()
            parent = models.ForeignKey(SimpleParentModel, on_delete=models.CASCADE)

        class SimpleModelInline(ByteDeckSummernoteInlineModelAdmin):
            model = SimpleModel2

        class SimpleParentModelAdmin(ByteDeckSummernoteModelAdmin):
            inlines = [SimpleModelInline]

        ma = SimpleParentModelAdmin(SimpleParentModel, self.site)

        assert isinstance(
            ma.get_form(None).base_fields['foobar'].widget,
            ByteDeckSummernoteAdvancedWidget
        )

    def test_admin_model_inplace(self):
        from bytedeck_summernote.admin import ByteDeckSummernoteModelAdmin
        from bytedeck_summernote.widgets import ByteDeckSummernoteSafeWidget

        class SimpleModel3(models.Model):
            foobar = models.TextField()

        self.summernote_config['iframe'] = False

        class SimpleModelAdmin(ByteDeckSummernoteModelAdmin):
            pass

        ma = SimpleModelAdmin(SimpleModel3, self.site)

        assert isinstance(
            ma.get_form(None).base_fields['foobar'].widget,
            ByteDeckSummernoteSafeWidget
        )

        self.summernote_config['iframe'] = True
