import re

from bs4 import BeautifulSoup
from bs4 import DEFAULT_OUTPUT_ENCODING
from bs4 import Tag
from django.db.models.signals import pre_save
from django.dispatch import receiver

from quest_manager.models import Quest


class UglySoup(BeautifulSoup):
    r = re.compile(r'^(\s*)', re.MULTILINE)

    def insert_before(self, successor):
        pass

    def insert_after(self, successor):
        pass

    def prettify_indented(self, encoding=None, formatter="minimal", indent_width=4):
        return self.r.sub(r'\1' * indent_width, self.prettify(encoding, formatter))


@receiver(pre_save, sender=Quest)
def quest_pre_save_callback(sender, instance, **kwargs):
    instance.instructions = tidy_html(instance.instructions)


def tidy_html(content):
    soup = UglySoup(content, "html.parser")
    return soup.prettify_indented()

    # config = {
    #     # "break-before-br": True,
    #     # "doctype": "omit",
    #     # "output-html": True,
    #     # "wrap": 0,
    # }
    # result, errors = Tidy().tidy_fragment(content, options=config)
    # return result
