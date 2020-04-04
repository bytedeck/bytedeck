from .models import SiteConfig


def config(request):
    """
    Simple context processor that puts the config into every
    RequestContext.
        TEMPLATE_CONTEXT_PROCESSORS = (
            # ...
            'siteconfig.context_processors.config',
        )
    """
    return {"config": SiteConfig.get()}
