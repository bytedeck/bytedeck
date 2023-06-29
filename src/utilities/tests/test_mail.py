from django.test import SimpleTestCase
from django.core import mail

from utilities.mail import send_mass_mail


class MailTests(SimpleTestCase):
    """
    Various tests for `utilities.mail` module.
    """
    def get_mailbox_content(self):
        return [m.message() for m in mail.outbox]

    def get_the_message(self):
        mailbox = self.get_mailbox_content()
        self.assertEqual(
            len(mailbox),
            1,
            "Expected exactly one message, got %d.\n%r"
            % (len(mailbox), [m.as_string() for m in mailbox]),
        )
        return mailbox[0]

    def test_send_mass_mail(self):
        """Test send_mass_mail with text and html messages"""
        send_mass_mail([
            (
                "Subject",
                "Content",
                "HTML Content",
                "sender@example.com",
                ["nobody@example.com", "somebody@example.com"],
            )
        ])

        # email message was sent to multiple recipients
        self.assertEqual(len(mail.outbox), 1)

        message = self.get_the_message()

        self.assertEqual(message.get("subject"), "Subject")
        self.assertEqual(message.get_all("to"), ['nobody@example.com, somebody@example.com'])
        self.assertTrue(message.is_multipart())
        self.assertEqual(len(message.get_payload()), 2)
        self.assertEqual(message.get_payload(0).get_payload(), "Content")
        self.assertEqual(message.get_payload(0).get_content_type(), "text/plain")
        self.assertEqual(message.get_payload(1).get_payload(), "HTML Content")
        self.assertEqual(message.get_payload(1).get_content_type(), "text/html")
