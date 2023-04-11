from django.apps import apps
from django.contrib.admin.sites import AdminSite
from django.db import models

from django_tenants.test.cases import TenantTestCase


class TestByteDeckSummernoteSafeModelAdmin(TenantTestCase):
    """ByteDeck's Summernote implementation, so called 'Safe' variant"""

    def setUp(self):
        self.username = "lqez"
        self.password = "ohmygoddess"
        self.site = AdminSite()

        self.app_config = apps.get_app_config("django_summernote")
        self.app_config.update_config()
        self.summernote_config = self.app_config.config

    def test_admin_model(self):
        """Safe widget (iframe variant) injected into customized admin class"""
        from bytedeck_summernote.admin import (
            ByteDeckSummernoteSafeInlineModelAdmin,
            ByteDeckSummernoteSafeModelAdmin,
        )
        from bytedeck_summernote.widgets import ByteDeckSummernoteSafeWidget

        class SimpleModel(models.Model):
            foobar = models.TextField()

        class SimpleModelAdmin(ByteDeckSummernoteSafeModelAdmin):
            pass

        ma = SimpleModelAdmin(SimpleModel, self.site)

        assert isinstance(
            ma.get_form(None).base_fields["foobar"].widget,
            ByteDeckSummernoteSafeWidget,
        )

        class SimpleParentModel(models.Model):
            foobar = models.TextField()

        class SimpleModel2(models.Model):
            foobar = models.TextField()
            parent = models.ForeignKey(SimpleParentModel, on_delete=models.CASCADE)

        class SimpleModelInline(ByteDeckSummernoteSafeInlineModelAdmin):
            model = SimpleModel2

        class SimpleParentModelAdmin(ByteDeckSummernoteSafeModelAdmin):
            inlines = [SimpleModelInline]

        ma = SimpleParentModelAdmin(SimpleParentModel, self.site)

        assert isinstance(
            ma.get_form(None).base_fields["foobar"].widget,
            ByteDeckSummernoteSafeWidget,
        )

    def test_admin_model_inplace(self):
        """Safe widget (non-iframe variant aka inplace) injected into customized admin class"""
        from bytedeck_summernote.admin import ByteDeckSummernoteSafeModelAdmin
        from bytedeck_summernote.widgets import ByteDeckSummernoteSafeInplaceWidget

        class SimpleModel3(models.Model):
            foobar = models.TextField()

        self.summernote_config["iframe"] = False

        class SimpleModelAdmin(ByteDeckSummernoteSafeModelAdmin):
            pass

        ma = SimpleModelAdmin(SimpleModel3, self.site)

        assert isinstance(ma.get_form(None).base_fields["foobar"].widget, ByteDeckSummernoteSafeInplaceWidget)

        self.summernote_config["iframe"] = True

    def test_admin_summernote_fields(self):
        from bytedeck_summernote.admin import ByteDeckSummernoteSafeModelAdmin
        from bytedeck_summernote.widgets import ByteDeckSummernoteSafeWidget

        class SimpleModel4(models.Model):
            foo = models.TextField()
            bar = models.TextField()

        class SimpleModelAdmin(ByteDeckSummernoteSafeModelAdmin):
            summernote_fields = ("foo",)

        ma = SimpleModelAdmin(SimpleModel4, self.site)

        assert isinstance(
            ma.get_form(None).base_fields["foo"].widget,
            ByteDeckSummernoteSafeWidget,
        )
        assert not isinstance(
            ma.get_form(None).base_fields["bar"].widget,
            ByteDeckSummernoteSafeWidget,
        )


class TestByteDeckSummernoteAdvancedModelAdmin(TenantTestCase):
    """ByteDeck's Summernote implementation, so called 'Advanced' variant"""

    def setUp(self):
        self.username = "lqez"
        self.password = "ohmygoddess"
        self.site = AdminSite()

        self.app_config = apps.get_app_config("django_summernote")
        self.app_config.update_config()
        self.summernote_config = self.app_config.config

    def test_admin_model(self):
        """Advanced widget (iframe variant) injected into customized admin class"""
        from bytedeck_summernote.admin import (
            ByteDeckSummernoteAdvancedInlineModelAdmin,
            ByteDeckSummernoteAdvancedModelAdmin,
        )
        from bytedeck_summernote.widgets import ByteDeckSummernoteAdvancedWidget

        class SimpleModel(models.Model):
            foobar = models.TextField()

        class SimpleModelAdmin(ByteDeckSummernoteAdvancedModelAdmin):
            pass

        ma = SimpleModelAdmin(SimpleModel, self.site)

        assert isinstance(
            ma.get_form(None).base_fields["foobar"].widget,
            ByteDeckSummernoteAdvancedWidget,
        )

        class SimpleParentModel(models.Model):
            foobar = models.TextField()

        class SimpleModel2(models.Model):
            foobar = models.TextField()
            parent = models.ForeignKey(SimpleParentModel, on_delete=models.CASCADE)

        class SimpleModelInline(ByteDeckSummernoteAdvancedInlineModelAdmin):
            model = SimpleModel2

        class SimpleParentModelAdmin(ByteDeckSummernoteAdvancedModelAdmin):
            inlines = [SimpleModelInline]

        ma = SimpleParentModelAdmin(SimpleParentModel, self.site)

        assert isinstance(
            ma.get_form(None).base_fields["foobar"].widget,
            ByteDeckSummernoteAdvancedWidget,
        )

    def test_admin_model_inplace(self):
        """Advanced widget (non-iframe variant aka inplace) injected into customized admin class"""
        from bytedeck_summernote.admin import ByteDeckSummernoteAdvancedModelAdmin
        from bytedeck_summernote.widgets import ByteDeckSummernoteAdvancedInplaceWidget

        class SimpleModel3(models.Model):
            foobar = models.TextField()

        self.summernote_config["iframe"] = False

        class SimpleModelAdmin(ByteDeckSummernoteAdvancedModelAdmin):
            pass

        ma = SimpleModelAdmin(SimpleModel3, self.site)

        assert isinstance(ma.get_form(None).base_fields["foobar"].widget, ByteDeckSummernoteAdvancedInplaceWidget)

        self.summernote_config["iframe"] = True

    def test_admin_summernote_fields(self):
        from bytedeck_summernote.admin import ByteDeckSummernoteAdvancedModelAdmin
        from bytedeck_summernote.widgets import ByteDeckSummernoteAdvancedWidget

        class SimpleModel4(models.Model):
            foo = models.TextField()
            bar = models.TextField()

        class SimpleModelAdmin(ByteDeckSummernoteAdvancedModelAdmin):
            summernote_fields = ("foo",)

        ma = SimpleModelAdmin(SimpleModel4, self.site)

        assert isinstance(
            ma.get_form(None).base_fields["foo"].widget,
            ByteDeckSummernoteAdvancedWidget,
        )
        assert not isinstance(
            ma.get_form(None).base_fields["bar"].widget,
            ByteDeckSummernoteAdvancedWidget,
        )
