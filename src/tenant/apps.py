from django.apps import AppConfig


def _shortcut(request, content_type_id, object_id):
    """
    TODO: Remove this once `django-tenants` fixes this issue
    Monkey patch django.contrib.contenttypes.views.shortcut so it would properly handle tenants
    This just removes the part where it checks if `django.contrib.sites` is installed.

    Redirect to an object's page based on a content-type ID and an object ID.
    """
    from django.contrib.contenttypes.models import ContentType
    from django.core.exceptions import ObjectDoesNotExist
    from django.http import Http404, HttpResponseRedirect
    from django.utils.translation import gettext as _

    # Look up the object, making sure it's got a get_absolute_url() function.
    try:
        content_type = ContentType.objects.get(pk=content_type_id)
        if not content_type.model_class():
            raise Http404(
                _("Content type %(ct_id)s object has no associated model") %
                {'ct_id': content_type_id}
            )
        obj = content_type.get_object_for_this_type(pk=object_id)
    except (ObjectDoesNotExist, ValueError):
        raise Http404(
            _("Content type %(ct_id)s object %(obj_id)s doesn't exist") %
            {'ct_id': content_type_id, 'obj_id': object_id}
        )

    try:
        get_absolute_url = obj.get_absolute_url
    except AttributeError:
        raise Http404(
            _("%(ct_name)s objects don't have a get_absolute_url() method") %
            {'ct_name': content_type.name}
        )
    absurl = get_absolute_url()

    # If the object actually defines a domain, we're done.
    if absurl.startswith(('http://', 'https://', '//')):
        return HttpResponseRedirect(absurl)

    return HttpResponseRedirect(absurl)


class TenantConfig(AppConfig):
    name = 'tenant'

    def ready(self):
        from django.contrib.contenttypes import views as contenttypes_views
        from django.db.models.signals import post_save

        from django_tenants.models import TenantMixin
        from django_tenants.signals import post_schema_sync

        from tenant.models import Tenant
        from tenant.signals import initialize_tenant_with_data, tenant_save_callback

        post_schema_sync.connect(initialize_tenant_with_data, sender=TenantMixin)
        post_save.connect(tenant_save_callback, sender=Tenant)

        # Monkey patch here
        contenttypes_views.shortcut = _shortcut
