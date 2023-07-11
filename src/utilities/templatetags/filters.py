from django import template
from django.template.defaultfilters import stringfilter

register = template.Library()


@register.filter
@stringfilter
def add_possessive(string):
    """
    Possessivizes names to include either a 's or an ' depending on if the name ends in a "s".
    """
    if string[-2:] == "'s" or string[-2:] == "’s":
        return string
    elif string[-1:] == "s":
        return f"{string}'"
    else:
        return f"{string}'s"
