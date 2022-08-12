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
def tags_name():
    return SiteConfig.get().custom_name_for_tags


@register.simple_tag
@not_allow_public_tenant
def groups_name():
    return SiteConfig.get().custom_name_for_groups


# https://docs.djangoproject.com/en/1.11/howto/custom-template-tags/#inclusion-tags

@register.inclusion_tag('utilities/list_of_links.html')
def menu_list():
    links = MenuItem.objects.filter(visible=True)
    return {'links': links}


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
