from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.forms import modelform_factory
from django.test import RequestFactory

from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from prerequisites.admin import (
    PrereqInlineForm,
    auto_name_selected_prereqs,
    recalculate_available_quests_for_all_users,
)
from prerequisites.models import IsAPrereqMixin, Prereq
from quest_manager.models import Quest

User = get_user_model()


def _request_with_messages():
    request = RequestFactory().get('/')
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


class PrereqInlineFormTest(ByteDeckTenantTestCase):
    """Tests for PrereqInlineForm which limits content-type choices to registered prereq models."""

    def test_content_type_querysets_limited_to_registered(self):
        """The (or_)prereq_content_type fields only offer content types registered as prereqs."""
        # PrereqInlineForm is an inline ModelForm; Django injects the model at runtime.
        # Bind it to Prereq here so we can instantiate it in isolation.
        form_class = modelform_factory(
            Prereq, form=PrereqInlineForm,
            fields=['prereq_content_type', 'or_prereq_content_type'],
        )
        form = form_class()
        registered = set(IsAPrereqMixin.all_registered_content_types().values_list('pk', flat=True))

        self.assertEqual(set(form.fields['prereq_content_type'].queryset.values_list('pk', flat=True)), registered)
        self.assertEqual(set(form.fields['or_prereq_content_type'].queryset.values_list('pk', flat=True)), registered)


class AutoNameSelectedPrereqsActionTest(ByteDeckTenantTestCase):
    """Tests for the auto_name_selected_prereqs admin action."""

    def test_auto_name_sets_name_to_str(self):
        """The action stores str(prereq) into each selected prereq's name field."""
        parent = baker.make(Quest)
        prereq_quest = baker.make(Quest)
        prereq = Prereq.add_simple_prereq(parent, prereq_quest)
        # Clear the name so we can observe the action populating it.
        Prereq.objects.filter(pk=prereq.pk).update(name='')

        auto_name_selected_prereqs(None, _request_with_messages(), Prereq.objects.filter(pk=prereq.pk))

        prereq.refresh_from_db()
        self.assertEqual(prereq.name, str(prereq))
        self.assertTrue(prereq.name)


class RecalculateAvailableQuestsActionTest(ByteDeckTenantTestCase):
    """Tests for the recalculate_available_quests_for_all_users admin action."""

    @patch('prerequisites.admin.update_quest_conditions_all_users.apply_async')
    def test_recalculate_schedules_task_and_messages(self, mock_apply_async):
        """The action offloads recalculation to a background task and notifies the user."""
        request = _request_with_messages()

        recalculate_available_quests_for_all_users(None, request, Prereq.objects.none())

        mock_apply_async.assert_called_once()
        self.assertEqual(len(list(request._messages)), 1)
