from django import template
from django.contrib.sites.models import Site
from django.templatetags.static import static
from django.shortcuts import get_object_or_404
from djconfig import config, reload_maybe

from utilities.models import ImageResource, MenuItem

register = template.Library()


@register.simple_tag(takes_context=True)
def banner_url(context):
    if context.request.user.is_anonymous or not context.request.user.profile.dark_theme:
        if config.hs_banner_image:
            banner_image = get_object_or_404(ImageResource, pk=config.hs_banner_image)
            return banner_image.image.url
        else:
            return static('img/banner.svg')
    else:
        if config.hs_banner_image_dark:
            banner_image = get_object_or_404(ImageResource, pk=config.hs_banner_image_dark)
            return banner_image.image.url
        else:
            return static('img/banner_slate.svg')


@register.simple_tag
def site_logo_url():
    reload_maybe()  # used in celery tasks, so needs config loaded
    if config.hs_site_logo:
        site_logo = get_object_or_404(ImageResource, pk=config.hs_site_logo)
        return site_logo.image.url
    else:
        return static('img/default_icon.png')


@register.simple_tag
def site_logo_url_full():
    return "https://{}{}".format(Site.objects.get_current().domain, site_logo_url())


# https://docs.djangoproject.com/en/1.11/howto/custom-template-tags/#inclusion-tags

@register.inclusion_tag('utilities/list_of_links.html')
def menu_list():
    links = MenuItem.objects.filter(visible=True)
    return {'links': links}
