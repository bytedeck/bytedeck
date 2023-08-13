from django.contrib.auth import get_user_model
from django_tenants.test.cases import TenantTestCase
from utilities.models import MenuItem

User = get_user_model()


class MenuItemModelTest(TenantTestCase):

    def setUp(self):
        pass

    def test_get_default_side_menu_items(self):
        side_menus_map = MenuItem.objects.get_or_create_default_side_menu_items().in_bulk(None, field_name='label')

        self.assertEqual(len(side_menus_map), len(MenuItem.SIDE_MENU_ITEMS))
        self.assertEqual(MenuItem.objects.count(), len(side_menus_map))

        for default_side_menu in MenuItem.SIDE_MENU_ITEMS:
            self.assertIsNotNone(side_menus_map.get(default_side_menu))
