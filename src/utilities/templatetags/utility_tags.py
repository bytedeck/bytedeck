import functools

from django import template
from django.contrib.sites.models import Site
from django.db import connection
from tenant_schemas.utils import get_public_schema_name

from siteconfig.models import SiteConfig

from utilities.models import MenuItem

register = template.Library()


def not_allow_public_tenant(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if connection.schema_name == get_public_schema_name():
            return None
        return f(*args, **kwargs)

    return wrapper


@register.simple_tag(takes_context=True)
@not_allow_public_tenant
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
def site_logo_url_full():
    return "https://{}{}".format(Site.objects.get_current().domain, site_logo_url())


# https://docs.djangoproject.com/en/1.11/howto/custom-template-tags/#inclusion-tags

@register.inclusion_tag('utilities/list_of_links.html')
def menu_list():
    links = MenuItem.objects.filter(visible=True)
    return {'links': links}
