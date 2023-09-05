import functools

from django import template
from django.db import connection

from django_tenants.utils import get_public_schema_name

from siteconfig.models import SiteConfig
from utilities.models import MenuItem

register = template.Library()


def not_allow_public_tenant(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if connection.schema_name == get_public_schema_name():
            return ''
        return f(*args, **kwargs)

    return wrapper


@not_allow_public_tenant
@register.simple_tag(takes_context=True)
def banner_url(context):
    if context.request.user.is_anonymous or not context.request.user.profile.dark_theme:
        return SiteConfig.get().get_banner_image_url()
    else:
        return SiteConfig.get().get_banner_image_dark_url()


@register.simple_tag
@not_allow_public_tenant
def site_logo_url():
    return SiteConfig.get().get_site_logo_url()


@register.simple_tag
@not_allow_public_tenant
def favicon_url():
    return SiteConfig.get().get_favicon_url()


@register.simple_tag
@not_allow_public_tenant
def tag_name():
    return SiteConfig.get().custom_name_for_tag


@register.simple_tag
@not_allow_public_tenant
def group_name():
    return SiteConfig.get().custom_name_for_group


# https://docs.djangoproject.com/en/1.11/howto/custom-template-tags/#inclusion-tags

@register.inclusion_tag('utilities/list_of_links.html')
def menu_list():
    links = MenuItem.objects.get_main_menu_items().get_visible_items()
    return {'links': links}


@register.inclusion_tag('utilities/side_menu_items.html', takes_context=True)
def side_menu_list(context):
    """
    Display the modular menu items in the sidebar (left)
    """
    side_menu_items = MenuItem.objects.get_side_menu_items().get_visible_items()
    return {'side_menu_items': side_menu_items, 'request': context.get('request')}


@register.inclusion_tag('utilities/side_menu_items_navbar.html', takes_context=True)
def side_menu_list_navbar(context):
    """
    Display the modular menu items in the navbar (top)
    """
    side_menu_items = MenuItem.objects.get_side_menu_items().get_visible_items()

    # Need add the request to the context to check if the user is authenticated
    # A check is needed because a test case is failing and it doesn't have the request in the context
    # See: src/hackerspace_online/tests/test_middleware.py::RequestDataTooBigMiddlewareTestCase
    #                ::test_request_data_too_big_exception_without_requestdatatoobig_middleware

    return {
        'side_menu_items': side_menu_items,
        'request': context.get('request'),
        'config': context.get('config'),
    }


@register.filter
def checkcross(value):
    """
    Converts a boolean value to a corresponding class value for a fontawesome check or cross (times) icon
    Usage: <i class="{{ booleanvalue | crosscheck }}"></i>
    """
    if value is True:
        return 'fa fa-check'
    elif value is False:
        return 'fa fa-times'
