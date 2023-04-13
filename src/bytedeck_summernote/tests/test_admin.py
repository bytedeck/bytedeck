from django.apps import apps
from django.contrib.admin.sites import AdminSite
from django.contrib.flatpages.models import FlatPage

from django_tenants.test.cases import TenantTestCase


from django.test import TestCase

from bytedeck_summernote.admin import ByteDeckSummernoteModelAdminMixin


class ByteDeckSummernoteModelAdminMixinTestCase(TestCase):

    def test_get_summernote_widget_class(self):
        """
        Test two things:
        1. that the get_summernote_widget_class method raises a NotImplementedError when called directly,
        as it should be overridden in subclasses.
        2. that a subclass of ByteDeckSummernoteModelAdminMixin that implements the get_summernote_widget_class
        method returns the expected widget class.
        """
        mixin = ByteDeckSummernoteModelAdminMixin()

        # Test that the method raises a NotImplementedError when called directly
        with self.assertRaises(NotImplementedError):
            mixin.get_summernote_widget_class()

        # Define a test widget class
        class TestSummernoteWidget:
            pass

        # Define a subclass of the mixin that implements the get_summernote_widget_class method
        class SubByteDeckSummernoteModelAdminMixin(ByteDeckSummernoteModelAdminMixin):
            def get_summernote_widget_class(self):
                return TestSummernoteWidget

        # Test that the subclass returns the TestSummernoteWidget class
        subclass_mixin = SubByteDeckSummernoteModelAdminMixin()
        self.assertEqual(subclass_mixin.get_summernote_widget_class(), TestSummernoteWidget)


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
            ByteDeckSummernoteSafeModelAdmin,
        )
        from bytedeck_summernote.widgets import ByteDeckSummernoteSafeWidget

        class FlatPageModelAdmin(ByteDeckSummernoteSafeModelAdmin):
            pass

        ma = FlatPageModelAdmin(FlatPage, self.site)

        assert isinstance(
            ma.get_form(None).base_fields["content"].widget,
            ByteDeckSummernoteSafeWidget,
        )

    def test_admin_model_inplace(self):
        """Safe widget (non-iframe variant aka inplace) injected into customized admin class"""
        from bytedeck_summernote.admin import ByteDeckSummernoteSafeModelAdmin
        from bytedeck_summernote.widgets import ByteDeckSummernoteSafeInplaceWidget

        self.summernote_config["iframe"] = False

        class FlatPageModelAdmin(ByteDeckSummernoteSafeModelAdmin):
            pass

        ma = FlatPageModelAdmin(FlatPage, self.site)

        assert isinstance(ma.get_form(None).base_fields["content"].widget, ByteDeckSummernoteSafeInplaceWidget)

        self.summernote_config["iframe"] = True

    def test_admin_summernote_fields(self):
        from bytedeck_summernote.admin import ByteDeckSummernoteSafeModelAdmin
        from bytedeck_summernote.widgets import ByteDeckSummernoteSafeWidget

        class FlatPageModelAdmin(ByteDeckSummernoteSafeModelAdmin):
            summernote_fields = ("content",)

        ma = FlatPageModelAdmin(FlatPage, self.site)

        assert isinstance(
            ma.get_form(None).base_fields["content"].widget,
            ByteDeckSummernoteSafeWidget,
        )

        class FlatPageModelAdmin(ByteDeckSummernoteSafeModelAdmin):
            summernote_fields = []

        ma = FlatPageModelAdmin(FlatPage, self.site)

        assert not isinstance(
            ma.get_form(None).base_fields["content"].widget,
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
            ByteDeckSummernoteAdvancedModelAdmin,
        )
        from bytedeck_summernote.widgets import ByteDeckSummernoteAdvancedWidget

        class FlatPageModelAdmin(ByteDeckSummernoteAdvancedModelAdmin):
            pass

        ma = FlatPageModelAdmin(FlatPage, self.site)

        assert isinstance(
            ma.get_form(None).base_fields["content"].widget,
            ByteDeckSummernoteAdvancedWidget,
        )

    def test_admin_model_inplace(self):
        """Advanced widget (non-iframe variant aka inplace) injected into customized admin class"""
        from bytedeck_summernote.admin import ByteDeckSummernoteAdvancedModelAdmin
        from bytedeck_summernote.widgets import ByteDeckSummernoteAdvancedInplaceWidget

        self.summernote_config["iframe"] = False

        class FlatPageModelAdmin(ByteDeckSummernoteAdvancedModelAdmin):
            pass

        ma = FlatPageModelAdmin(FlatPage, self.site)

        assert isinstance(ma.get_form(None).base_fields["content"].widget, ByteDeckSummernoteAdvancedInplaceWidget)

        self.summernote_config["iframe"] = True

    def test_admin_summernote_fields(self):
        from bytedeck_summernote.admin import ByteDeckSummernoteAdvancedModelAdmin
        from bytedeck_summernote.widgets import ByteDeckSummernoteAdvancedWidget

        class FlatPageModelAdmin(ByteDeckSummernoteAdvancedModelAdmin):
            summernote_fields = ("content",)

        ma = FlatPageModelAdmin(FlatPage, self.site)

        assert isinstance(
            ma.get_form(None).base_fields["content"].widget,
            ByteDeckSummernoteAdvancedWidget,
        )

        class FlatPageModelAdmin(ByteDeckSummernoteAdvancedModelAdmin):
            summernote_fields = []

        ma = FlatPageModelAdmin(FlatPage, self.site)

        assert not isinstance(
            ma.get_form(None).base_fields["content"].widget,
            ByteDeckSummernoteAdvancedWidget,
        )
