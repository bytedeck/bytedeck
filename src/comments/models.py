import os

from bs4 import BeautifulSoup
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import reverse
from django.utils.html import urlize, escape

from notifications.models import deleted_object_receiver
from django.db.models.signals import pre_delete


# from quest_manager.models import Quest

# Create your models here.


class CommentQuerySet(models.query.QuerySet):
    def get_user(self, recipient):
        return self.filter(recipient=recipient)

    def get_object_target(self, object):
        object_type = ContentType.objects.get_for_model(object)
        return self.filter(target_content_type__pk=object_type.id,
                           target_object_id=object.id)

    def get_no_parents(self):
        return self.filter(parent=None)

    def get_not_flagged(self):
        return self.filter(flagged=False)


class CommentManager(models.Manager):
    def get_queryset(self):
        qs = CommentQuerySet(self.model, using=self._db)
        return qs.select_related('user')

    def all_with_target_object(self, object):
        return self.get_queryset().get_object_target(object).get_no_parents()

    # def all(self):
    #     return self.get_queryset.get_active().get_no_parents()

    def create_comment(self, user=None, text=None, path=None, target=None, parent=None, convert_newlines=True):
        if not path:
            raise ValueError("Must include a path when adding a comment")
        if not user:
            raise ValueError("Must include a user  when adding a comment")

        text = clean_html(text, convert_newlines)

        comment = self.model(
            user=user,
            path=path,
            text=text,
        )
        if target is not None:
            comment.target_content_type = ContentType.objects.get_for_model(target)
            comment.target_object_id = target.id
        # if quest is not None:
        #     comment.quest = quest

        if parent is not None:
            comment.parent = parent

        comment.save(using=self._db)

        # add anchor target to Comment path now that id assigned when saved
        comment.path += "#comment-" + str(comment.id)
        comment.save(using=self._db)

        return comment


def clean_html(text, convert_newlines=True):
    """ Several steps to clean HTML input by user:
    1. formats unformatted links
    2. sets all links to target="_blank"
    3. fixes broken lists (missing closing ul tags etc)
    4. removes script tags
    """
    # format unformatted links
    # http://stackoverflow.com/questions/32937126/beautifulsoup-replacewith-method-adding-escaped-html-want-it-unescaped/32937561?noredirect=1#comment53702552_32937561

    soup = BeautifulSoup(text, "html.parser")
    text_nodes = soup.find_all(text=True)
    # https://stackoverflow.com/questions/53588107/prevent-beautifulsoups-find-all-from-converting-escaped-html-tags/53592575?noredirect=1#comment94061687_53592575
    # text_nodes2 = [escape(x) for x in soup.strings]
    for textNode in text_nodes:
        escaped_text = escape(textNode)
        if convert_newlines:
            escaped_text = '<br>'.join(escaped_text.splitlines())

        if textNode.parent and getattr(textNode.parent, 'name') == 'a':
            continue  # skip already formatted links
        urlized_text = urlize(escaped_text, trim_url_limit=50)
        textNode.replace_with(BeautifulSoup(urlized_text, "html.parser"))

    # https://www.crummy.com/software/BeautifulSoup/bs4/doc/#unicode-dammit
    soup = BeautifulSoup(soup.renderContents(), "html.parser", from_encoding="UTF-8")

    # All links in comments: force open in new tab
    links = soup.find_all('a')
    for link in links:
        link['target'] = '_blank'

    # Add missing ul tags (raw <li> elements can break the page!)
    # https://stackoverflow.com/questions/55619920/how-to-fix-missing-ul-tags-in-html-list-snippet-with-python-and-beautiful-soup
    ulgroup = 0
    uls = []
    for li in soup.findAll('li'):
        previous_element = li.findPrevious()
        # if <li> already wrapped in <ul>, do nothing
        if previous_element and previous_element.name == 'ul':
            continue
        # if <li> is the first element of a <li> group, wrap it in a new <ul>
        if not previous_element or previous_element.name != 'li':
            ulgroup += 1
            ul = soup.new_tag("ul")
            li.wrap(ul)
            uls.append(ul)
        # append rest of <li> group to previously created <ul>
        elif ulgroup > 0:
            uls[ulgroup - 1].append(li)

    # Remove script tags
    [s.extract() for s in soup('script')]

    return str(soup)


class Comment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)
    path = models.CharField(max_length=350)
    text = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    active = models.BooleanField(default=True)
    flagged = models.BooleanField(default=False)

    target_content_type = models.ForeignKey(ContentType, related_name='comment_target',
                                            null=True, blank=True, on_delete=models.SET_NULL)
    target_object_id = models.PositiveIntegerField(null=True, blank=True)
    target_object = GenericForeignKey("target_content_type", "target_object_id")

    objects = CommentManager()

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return self.text

    def get_target_object(self):
        if self.target_object_id is not None:
            return self.target_content_type.get_object_for_this_type(id=self.target_object_id)
        else:
            return None

    def get_absolute_url(self):
        """ Find the aboslute url of the target object, then add the comment"""
        # find absolute url of the target
        self.target_object.get_absolute_url()        
        return reverse('comments:threads', kwargs={'id': self.id})

    def get_origin(self):
        return self.path

    def is_child(self):
        if self.parent is not None:
            return True
        else:
            return False

    def flag(self):
        self.flagged = True
        self.save()

    def unflag(self):
        self.flagged = False
        self.save()

    def get_children(self):
        if self.is_child():
            return None
        else:
            return Comment.objects.filter(parent=self)

    def get_affected_users(self):
        # it needs to be a parent and have children, which are the affected users
        comment_children = self.get_children()
        if comment_children is not None:
            users = []
            for comment in comment_children:
                if comment.user in users:
                    pass
                else:
                    users.append(comment.user)
            return users
        else:
            return None


# Document Handler ############################################
class Document(models.Model):
    docfile = models.FileField(upload_to='documents/%Y/%m/%d')
    # null=True is an artifect from on_delete=models.SET_NULL, can't change until all null values are removed?
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, null=True)  

    def is_valid_portfolio_type(self):
        # import here to prevent circular imports!
        from portfolios.views import is_acceptable_image_type, is_acceptable_vid_type
        filename = os.path.basename(self.docfile.name)
        return is_acceptable_image_type(filename) or is_acceptable_vid_type(filename)


pre_delete.connect(deleted_object_receiver, sender=Comment)
