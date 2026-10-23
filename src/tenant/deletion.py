"""Schema-aware deletion collectors.

On the public schema, ``TENANT_APPS`` tables (e.g. ``quest_manager_questsubmission``)
do not exist.  When Django's deletion collector walks a ``User``'s reverse
relations to build the delete cascade, it queries those tables and raises
``relation "..." does not exist`` -- which is why a user could not be deleted on
the public schema (issue #691; the original ``account_emailaddress`` error was
just the first missing table it hit).

The collectors below skip any related model whose DB table is not visible in the
current Postgres schema.  On a tenant schema every table is present, so this is a
no-op and cascades behave exactly as before; on the public schema the tenant-only
tables are skipped (a public user has no rows in them anyway -- those FKs point at
each *tenant's* ``auth_user``, not the public one).
"""
from django.contrib.admin.utils import NestedObjects, quote
from django.db import connection, router
from django.db.models.deletion import Collector
from django.urls import NoReverseMatch, reverse
from django.utils.functional import cached_property
from django.utils.html import format_html
from django.utils.text import capfirst


class SkipMissingSchemaTablesMixin:
    """Deletion-collector mixin: skip related models whose table isn't visible
    in the current schema (see module docstring)."""

    @cached_property
    def _visible_tables(self):
        """Return the set of table names visible on the current Postgres schema.

        ``connection.introspection.table_names()`` respects the active
        ``search_path`` (via ``pg_table_is_visible``), so on the public schema
        this set excludes the ``TENANT_APPS`` tables.  Cached because a single
        collect walks many related models and the set is stable for the life of
        the collector.
        """
        return set(connection.introspection.table_names())

    def related_objects(self, related_model, related_fields, objs):
        """Collect related objects, skipping models whose table isn't visible.

        Overrides ``Collector.related_objects``.  If ``related_model``'s table
        is absent from the current schema (e.g. a ``TENANT_APPS`` table on the
        public schema), return an empty queryset so no query is issued and
        nothing is cascaded for it; otherwise defer to the default behaviour.

        :param related_model: the model on the far side of the reverse relation.
        :param related_fields: the fields linking ``related_model`` to ``objs``.
        :param objs: the objects whose related rows are being collected.
        :returns: a queryset of related objects (empty when the table is absent).
        """
        if related_model._meta.db_table not in self._visible_tables:
            # Empty queryset -- no DB hit, nothing to cascade for this model.
            return related_model._base_manager.none()
        return super().related_objects(related_model, related_fields, objs)


class SchemaAwareCollector(SkipMissingSchemaTablesMixin, Collector):
    """Collector used for the actual delete()."""


class SchemaAwareNestedObjects(SkipMissingSchemaTablesMixin, NestedObjects):
    """Collector used to build the admin delete-confirmation page."""


def schema_aware_get_deleted_objects(objs, request, admin_site):
    """Mirror of ``django.contrib.admin.utils.get_deleted_objects`` that uses
    :class:`SchemaAwareNestedObjects`, so rendering the delete-confirmation page
    doesn't query tables absent from the current schema (issue #691)."""
    try:
        obj = objs[0]
    except IndexError:
        return [], {}, set(), []
    else:
        using = router.db_for_write(obj._meta.model)
    collector = SchemaAwareNestedObjects(using=using, origin=objs)
    collector.collect(objs)
    perms_needed = set()

    def format_callback(obj):
        model = obj.__class__
        has_admin = model in admin_site._registry
        opts = obj._meta

        no_edit_link = "%s: %s" % (capfirst(opts.verbose_name), obj)

        if has_admin:
            if not admin_site._registry[model].has_delete_permission(request, obj):
                perms_needed.add(opts.verbose_name)
            try:
                admin_url = reverse(
                    "%s:%s_%s_change" % (admin_site.name, opts.app_label, opts.model_name),
                    None,
                    (quote(obj.pk),),
                )
            except NoReverseMatch:
                return no_edit_link
            return format_html(
                '{}: <a href="{}">{}</a>', capfirst(opts.verbose_name), admin_url, obj
            )
        else:
            return no_edit_link

    to_delete = collector.nested(format_callback)
    protected = [format_callback(obj) for obj in collector.protected]
    model_count = {
        model._meta.verbose_name_plural: len(objs)
        for model, objs in collector.model_objs.items()
    }

    return to_delete, model_count, perms_needed, protected
