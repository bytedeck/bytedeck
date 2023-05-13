from bs4 import BeautifulSoup
from bs4.formatter import HTMLFormatter
from django.db.models.signals import pre_save
from django.dispatch import receiver

from quest_manager.models import Quest


@receiver(pre_save, sender=Quest)
def quest_pre_save_callback(sender, instance, **kwargs):
    instance.instructions = tidy_html(instance.instructions)


def tidy_html(markup, fix_runaway_newlines=False):
    """Prettify's HTML by adding an indentation of 4, except for specified inline tags.
    """

    # https://stackoverflow.com/questions/17583415/customize-beautifulsoups-prettify-by-tag

    # Double the curly brackets to avoid problems with .format()
    stripped_markup = markup.replace('{', '{{').replace('}', '}}')

    stripped_markup_soup = BeautifulSoup(stripped_markup, "html.parser")

    # We don't want line breaks/indentation for inline tags, especially span!
    inline_tags = ['span', 'a', 'b', 'i', 'u', 'em', 'strong',
                   'sup', 'sub', 'strike',
                   'code', 'kbd', 'var', 'mark', 'small', 'ins', 'del',
                   'abbr', 'samp']

    # find all the inline tags, save them into the list at i,
    # and replace them with: the string "{unformatted_tag_list[{i}]"
    unformatted_tag_list = []
    for i, tag in enumerate(stripped_markup_soup.find_all(inline_tags)):
        unformatted_tag_list.append(str(tag))
        tag.replace_with('{' + f'unformatted_tag_list[{i}]' + '}')

    # need to regenerate the soup so it forgets the location of the tags we just swapped out
    # otherwise it will still enter line breaks and indent at those locations
    markup = str(stripped_markup_soup)
    new_soup = BeautifulSoup(markup, "html.parser")

    prettified = new_soup.prettify(formatter=HTMLFormatter(indent=2))

    # replace the tags we swapped out earlier
    prettified = prettified.format(unformatted_tag_list=unformatted_tag_list)
    # revert the double braces to singles
    prettified = prettified.replace('{{', '{').replace('}}', '}')

    return prettified
