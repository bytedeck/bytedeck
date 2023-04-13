## How?

append `bytedeck_summernote` right after `django_summernote` in INSTALLED_APPS
```python
INSTALLED_APPS += [
   'django_summernote',
   'bytedeck_summernote',
]
```

update `urls.py`, replace `django_summernote.urls` with `bytedeck_summernote.urls`:

```python
urlpatterns += [
    # bytedeck summernote
    url(r'^summernote/', include('bytedeck_summernote.urls')),
]
```

Replace imports:
```python
from django_summernote.widgets import SummernoteInplaceWidget, SummernoteWidget

# and
from django_summernote.admin import SummernoteModelAdmin, SummernoteInlineModelAdmin
```

with

```python
from bytedeck_summernote.widgets import ByteDeckSummernoteSafeWidget, ByteDeckSummernoteSafeInplaceWidget

# and
from bytedeck_summernote.admin import ByteDeckSummernoteSafeModelAdmin, ByteDeckSummernoteSafeInlineModelAdmin
```

## FAQ

### Why there are a lot of templates?

To avoid clashing with django_summernote stock templates

### What was changed there?

Either `include` or `extends` tags, and two lines of code in `widget_common.html` file.

### Why did you copy-pasted render methods of widget classes?

Because original developers hardcoded template names, instead of using easy to override `template_name` attribute.

### Why all classes have prefix "ByteDeck"?

To avoid confusion with stock django_summernote, but please suggest better prefixes.

### What is the workflow for keeping our hacked version up to date?

1. once the upstream issue #465 fixed (see summernote/django-summernote#465), then replace the content of `bytecode_summernote/widget_common.html` file with:

   ```html+django
   {% extends "django_summernote/widget_common.html" %}{# inherit "django_summernote" template "as-is" #}
   ```

   yes, one line of code instead of hundred and half

2. pin newer version in `requirements.txt` and until there are no backward incompatibilities in `django-summernote` nor in Django itself, that's all you need.

from @bashu:
   > with my latest patches, there are no benefits to maintain separate fork. However if we manage to accept some of our changes (templates and more generic implementation of admin+widgets classes) into upstream version of `django_summernote`, then we can reduce "bytedeck" specific implementation to three-five lines of code.
