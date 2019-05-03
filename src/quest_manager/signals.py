import re

from bs4 import BeautifulSoup
from django.db.models.signals import pre_save
from django.dispatch import receiver

from quest_manager.models import Quest


class UglySoup(BeautifulSoup):
    r = re.compile(r'^(\s*)', re.MULTILINE)

    def insert_before(self, successor):
        pass

    def insert_after(self, successor):
        pass

    def improved_prettify(self, encoding=None, formatter="minimal", indent_width=4):
        return self.r.sub(r'\1' * indent_width, self.prettify(encoding, formatter))


@receiver(pre_save, sender=Quest)
def quest_pre_save_callback(sender, instance, **kwargs):
    instance.instructions = tidy_html(instance.instructions)


def tidy_html(markup):

    # https://stackoverflow.com/questions/17583415/customize-beautifulsoups-prettify-by-tag

    # Double curly brackets to avoid problems with .format()
    stripped_markup = markup.replace('{', '{{').replace('}', '}}')

    stripped_markup_soup = UglySoup(stripped_markup, "html.parser")

    # We don't want line breaks/indentation for inline tags, especially span!
    inline_tags = ['span', 'a', 'b', 'i', 'u', 'em', 'strong',
                   'sup', 'sub', 'strike',
                   'code', 'var', 'mark', 'small', 'ins', 'del']

    # find all the inline tags, save them into the list at i,
    # and replace them with: the string "{unformatted_tag_list[{i}]"
    unformatted_tag_list = []
    for i, tag in enumerate(stripped_markup_soup.find_all(inline_tags)):
        unformatted_tag_list.append(str(tag))
        tag.replace_with('{' + 'unformatted_tag_list[{0}]'.format(i) + '}')

    # need to regenerate the soup so it forgets the location of the tags we just swapped out
    # otherwise it will still enter line breaks and indent at those locations
    markup = str(stripped_markup_soup)
    new_soup = UglySoup(markup, "html.parser")

    prettified = new_soup.improved_prettify()

    # replace the tags we swapped out earlier
    prettified = prettified.format(unformatted_tag_list=unformatted_tag_list)
    return prettified

