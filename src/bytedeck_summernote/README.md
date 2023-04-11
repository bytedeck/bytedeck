## What is the workflow for keeping our hacked version up to date?

1. if this one got fixed summernote/django-summernote#465, then replace the content of `bytecode_summernote/widget_common.html` file with:

   ```html+django
   {% extends "django_common/widget_common.html" %}
   ```

   yes, one line of code instead of hundred and half

2. pin newer version in `requirements.txt` and until there are no backward incompatibilities in `django-summernote` nor in Django itself, that's all you need.

from @bashu:

> with my latest patches, there are no benefits to maintain separate fork. However if we manage to accept some of our changes (templates and more generic implementation of admin+widgets classes) into upstream version of `django_summernote`, then we can reduce "bytedeck" specific implementation to three-five lines of code.
