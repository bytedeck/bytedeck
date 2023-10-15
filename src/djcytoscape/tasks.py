from django.contrib.auth import get_user_model

from hackerspace_online.celery import app

from notifications.signals import notify
from siteconfig.models import SiteConfig

from .models import CytoScape

User = get_user_model()


@app.task(name='djcytoscape.tasks.regenerate_all_maps')
def regenerate_all_maps(requesting_user_id):
    requesting_user = User.objects.get(id=requesting_user_id)
    for scape in CytoScape.objects.all():
        try:
            scape.regenerate()
        except scape.InitialObjectDoesNotExist:
            notify.send(
                SiteConfig.get().deck_ai,
                recipient=requesting_user,
                icon="<i class='fa fa-lg fa-fw fa-map-signs text-warning'></i>",
                verb=f"failed to regenerate '{scape.name} Map', the intial object no longer exists.  This map has been deleted."
            )

    notify.send(
        SiteConfig.get().deck_ai,
        target=None,
        recipient=requesting_user,
        affected_users=[requesting_user],
        icon="<i class='fa fa-lg fa-fw fa-map-signs text-success'></i>",
        verb="completed regeneration of all valid maps."
    )
