from io import StringIO
from unittest.mock import patch

from django.core.management import call_command

from prerequisites.tasks import update_quest_conditions_all_users
from hackerspace_online.tests.utils import ByteDeckTenantTestCase


class UpdateConditionsCommandTest(ByteDeckTenantTestCase):
    """The `update_conditions` management command, which queues a full conditions-met recompute for all users."""

    def test_update_conditions__queues_task_and_writes_status(self):
        """Running the command writes a status line and schedules the recompute task on the default queue."""
        out = StringIO()
        with patch.object(update_quest_conditions_all_users, 'apply_async') as mock_apply_async:
            call_command('update_conditions', stdout=out)

        self.assertIn('Creating conditions met for all users', out.getvalue())
        mock_apply_async.assert_called_once_with(args=[1], queue='default')
