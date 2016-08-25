from urllib.parse import parse_qs

from django import template
from django.template.defaultfilters import stringfilter

register = template.Library()


@register.filter
@stringfilter
def youthumb(value, args):
    """returns small youtube thumb url
    if 'l' is passed as an arg then return a large thumb url
    modified from: https://djangosnippets.org/snippets/2234/
    """
    qs = value.split('?')
    video_id = parse_qs(qs[1])['v'][0]

    if args == 'l':
        return "http://img.youtube.com/vi/%s/0.jpg" % video_id
    else:
        return "http://img.youtube.com/vi/%s/2.jpg" % video_id
