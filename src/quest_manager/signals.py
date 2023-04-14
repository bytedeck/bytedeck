import re

from bs4 import BeautifulSoup
from django.db.models.signals import pre_save
from django.dispatch import receiver

from quest_manager.models import Quest


class UglySoup(BeautifulSoup):
    # continuous spaces starting from a new line, ending before (look ahead) to a non-whitespace character
    r = re.compile(r'^( +(?=\S))', re.MULTILINE)
    # match \r\n or \n newlines (preceded by any amount of horizontal whitespace), 20 or more in a row
    r2 = re.compile(r'([ \t]*(\r\n|\r|\n)){20,}')

    def insert_before(self, successor):
        pass

    def insert_after(self, successor):
        pass

    def improved_prettify(self, fix_runaway_newlines=False, encoding=None, formatter="minimal", indent_width=4):
        """ Prettify that also indents """
        # \1 is first capturing group, i.e. all continuous whitespace starting from a newline.
        # replace whitespace from standard prettify with proper indents
        bs_prettified = self.prettify(encoding, formatter)
        result = self.r.sub(r'\1' * indent_width, bs_prettified)
        # print("ugly:", result)
        if fix_runaway_newlines:
            result = self.r2.sub('\n\n', result)
        # print("delined:", result)
        return result


@receiver(pre_save, sender=Quest)
def quest_pre_save_callback(sender, instance, **kwargs):
    instance.instructions = tidy_html(instance.instructions)


def tidy_html(markup, fix_runaway_newlines=False):

    # https://stackoverflow.com/questions/17583415/customize-beautifulsoups-prettify-by-tag

    # Double the curly brackets to avoid problems with .format()
    stripped_markup = markup.replace('{', '{{').replace('}', '}}')

    stripped_markup_soup = UglySoup(stripped_markup, "html.parser")

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
    new_soup = UglySoup(markup, "html.parser")

    prettified = new_soup.improved_prettify(fix_runaway_newlines=fix_runaway_newlines)

    # replace the tags we swapped out earlier
    prettified = prettified.format(unformatted_tag_list=unformatted_tag_list)
    # revert the double braces to singles
    prettified = prettified.replace('{{', '{').replace('}}', '}')

    return prettified
