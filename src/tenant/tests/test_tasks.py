from django.core import mail

from django_tenants.test.cases import TenantTestCase

from tenant import tasks


class TenantTasksTests(TenantTestCase):
    """ Run tasks (from tenant module) asyncronously with apply() """

    def test_send_email_message(self):
        """Async. task "send_email_message" sends email messages as expected."""
        # outbox is empty before executing the task
        self.assertEqual(len(mail.outbox), 0)

        # executing "send_email_message" task
        task_result = tasks.send_email_message.apply(
            kwargs={
                # subject, message and a list of recipients
                "subject": "O hi, World!",
                "message": "Lorem ipsum dolor sit amet...",
                "recipient_list": ["john@doe.com", "jane@doe.com"],
            }
        )
        self.assertTrue(task_result.successful())

        # email message was sent to multiple recipients
        self.assertEqual(len(mail.outbox), 1)  # expecting one email message
        self.assertEqual(mail.outbox[0].subject, "O hi, World!")
        # john doe was first in a list of recipients (BCC)
        self.assertIn("john@doe.com", mail.outbox[0].bcc)
