from django import template
from django.contrib.sites.models import Site

from siteconfig.models import SiteConfig

from utilities.models import MenuItem

register = template.Library()


@register.simple_tag(takes_context=True)
def banner_url(context):
    if context.request.user.is_anonymous or not context.request.user.profile.dark_theme:
        return SiteConfig.get().get_banner_image_url()
    else:
        return SiteConfig.get().get_banner_image_dark_url()


@register.simple_tag
def site_logo_url():
    return SiteConfig.get().get_site_logo_url()


@register.simple_tag
def favicon_url():
    return SiteConfig.get().get_favicon_url()


@register.simple_tag
def site_logo_url_full():
    return "https://{}{}".format(Site.objects.get_current().domain, site_logo_url())


# https://docs.djangoproject.com/en/1.11/howto/custom-template-tags/#inclusion-tags

@register.inclusion_tag('utilities/list_of_links.html')
def menu_list():
    links = MenuItem.objects.filter(visible=True)
    return {'links': links}
