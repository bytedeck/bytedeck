import functools

from django import template
from django.conf import settings
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


# https://docs.djangoproject.com/en/5.2/howto/custom-template-tags/#inclusion-tags

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


@register.filter
def elided_page_range(page):
    """Return the page numbers a pagination control links, for one page of results.

    A long list would otherwise link every one of its pages: 334 links for 5000 rows at 15 a
    page, which wrap across the screen and push the first/previous/next/last links away from
    where the eye looks for them (#2448). This keeps a window of pages either side of the
    current one plus the first and last, and puts an ellipsis in each gap.

    Usage: ``{% for i in items|elided_page_range %}`` where ``items`` is a ``Page``. An entry
    equal to ``items.paginator.ELLIPSIS`` stands for the pages left out.

    Args:
        page (django.core.paginator.Page): the page being shown.

    Returns:
        iterator: page numbers (int), with ``Paginator.ELLIPSIS`` in place of each gap.
    """
    return page.paginator.get_elided_page_range(page.number, on_each_side=2, on_ends=1)


@register.simple_tag
def public_email_logo_url():
    """The absolute URL of the ByteDeck wordmark used in platform emails.

    Emails the PLATFORM sends (deck lifecycle and billing notices, the
    deck-request verification, the new-deck welcome) are signed by ByteDeck and
    carry ByteDeck branding; a deck's own mail to its users (announcements,
    notifications) carries that deck's logo through ``site_logo_url``. Reading
    the URL from settings keeps this usable on the public schema, which has no
    SiteConfig, and keeps it absolute, which mail clients require.

    Returns:
        str: settings.PUBLIC_EMAIL_LOGO_URL.
    """
    return settings.PUBLIC_EMAIL_LOGO_URL
