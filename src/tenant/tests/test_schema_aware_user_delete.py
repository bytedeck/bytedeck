"""Tests for schema-aware user deletion (issue #691).

Deleting a user on the *public* schema used to fail because Django's deletion
collector queried TENANT_APPS tables (e.g. quest_manager_questsubmission) that
don't exist there.  The schema-aware collectors skip absent tables on the public
schema, while remaining a no-op on tenant schemas (where every table exists and
cascades must still work).
"""
from allauth.account.models import EmailAddress

from django.contrib import admin as django_admin
from django.contrib.auth import get_user_model
from django.db import router
from django.test import RequestFactory

from django_tenants.test.cases import TenantTestCase
from django_tenants.utils import get_public_schema_name, schema_context
from model_bakery import baker

from quest_manager.models import Quest, QuestSubmission
from siteconfig.models import SiteConfig
from tenant.deletion import (
    SchemaAwareCollector,
    SchemaAwareNestedObjects,
    schema_aware_get_deleted_objects,
)

User = get_user_model()


class SchemaAwareUserDeleteTest(TenantTestCase):

    def test_public_schema_user_delete_succeeds(self):
        """A user (with an allauth EmailAddress) can be deleted on the public
        schema even though tenant-app tables are absent there (#691)."""
        with schema_context(get_public_schema_name()):
            user = User.objects.create_user("pub_del", "p@e.com", "pw")
            EmailAddress.objects.create(user=user, email="p@e.com", verified=True, primary=True)
            uid = user.pk

            collector = SchemaAwareCollector(using=router.db_for_write(User))
            collector.collect([user])   # would raise relation-does-not-exist without the fix
            collector.delete()

            self.assertFalse(User.objects.filter(pk=uid).exists())
            self.assertFalse(EmailAddress.objects.filter(user_id=uid).exists())

    def test_public_schema_nested_collect_does_not_raise(self):
        """The admin delete-confirmation collector also skips absent tables."""
        with schema_context(get_public_schema_name()):
            user = User.objects.create_user("pub_nested", "n@e.com", "pw")
            EmailAddress.objects.create(user=user, email="n@e.com", verified=True, primary=True)

            collector = SchemaAwareNestedObjects(using=router.db_for_write(User))
            collector.collect([user])  # would raise without the fix
            self.assertIn(user, [o for objs in collector.model_objs.values() for o in objs])

    def test_public_schema_get_deleted_objects(self):
        """schema_aware_get_deleted_objects builds the confirmation data without
        querying tenant tables."""
        with schema_context(get_public_schema_name()):
            superuser = User.objects.create_superuser("pub_su", "su@e.com", "pw")
            user = User.objects.create_user("pub_gdo", "g@e.com", "pw")
            EmailAddress.objects.create(user=user, email="g@e.com", verified=True, primary=True)

            request = RequestFactory().get("/")
            request.user = superuser
            to_delete, model_count, perms_needed, protected = schema_aware_get_deleted_objects(
                [user], request, django_admin.site,
            )
            self.assertIn("pub_gdo", str(to_delete))

    def test_tenant_schema_user_delete_still_cascades(self):
        """On a tenant schema every table exists, so the schema-aware collector
        cascades exactly like the default (a regression guard for the fix)."""
        user = baker.make(User)
        quest = baker.make(Quest)
        sub = baker.make(
            QuestSubmission, user=user, quest=quest,
            semester=SiteConfig.get().active_semester,
        )

        collector = SchemaAwareCollector(using=router.db_for_write(User))
        collector.collect([user])
        collector.delete()

        self.assertFalse(User.objects.filter(pk=user.pk).exists())
        self.assertFalse(QuestSubmission.objects.filter(pk=sub.pk).exists())
