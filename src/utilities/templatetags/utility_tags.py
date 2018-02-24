from django import template
from django.contrib.staticfiles.templatetags.staticfiles import static
from django.shortcuts import get_object_or_404
from djconfig import config

from utilities.models import ImageResource

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
