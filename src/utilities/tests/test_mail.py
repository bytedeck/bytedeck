from django.test import SimpleTestCase, override_settings
from django.core import mail

from utilities.mail import send_mass_mail


class MailTests:
    """
    Various tests for `utilities.mail` module.
    """
    def test_send_mass_mail(self):
        """Test send_mass_mail with text and html messages"""
        send_mass_mail([
            (
                "Subject",
                "Content",
                "HTML Content",
                "sender@example.com",
                ["nobody@example.com"],
            )
        ])
        message = self.get_the_message()

        self.assertEqual(message.get("subject"), "Subject")
        self.assertEqual(message.get_all("to"), ["nobody@example.com"])
        self.assertTrue(message.is_multipart())
        self.assertEqual(len(message.get_payload()), 2)
        self.assertEqual(message.get_payload(0).get_payload(), "Content")
        self.assertEqual(message.get_payload(0).get_content_type(), "text/plain")
        self.assertEqual(message.get_payload(1).get_payload(), "HTML Content")
        self.assertEqual(message.get_payload(1).get_content_type(), "text/html")


class BaseEmailBackendTests:
    """
    Copy-pasted from `django.tests.mail` without changes.
    """
    email_backend = None

    def setUp(self):
        self.settings_override = override_settings(EMAIL_BACKEND=self.email_backend)
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()

    def assertStartsWith(self, first, second):
        if not first.startswith(second):
            self.longMessage = True
            self.assertEqual(
                first[: len(second)],
                second,
                "First string doesn't start with the second.",
            )

    def get_mailbox_content(self):
        raise NotImplementedError(
            "subclasses of BaseEmailBackendTests must provide a get_mailbox_content() "
            "method"
        )

    def flush_mailbox(self):
        raise NotImplementedError(
            "subclasses of BaseEmailBackendTests may require a flush_mailbox() method"
        )

    def get_the_message(self):
        mailbox = self.get_mailbox_content()
        self.assertEqual(
            len(mailbox),
            1,
            "Expected exactly one message, got %d.\n%r"
            % (len(mailbox), [m.as_string() for m in mailbox]),
        )
        return mailbox[0]


class LocmemBackendTests(BaseEmailBackendTests, MailTests, SimpleTestCase):
    """
    Copy-pasted from `django.tests.mail` without changes.
    """
    email_backend = "django.core.mail.backends.locmem.EmailBackend"

    def get_mailbox_content(self):
        return [m.message() for m in mail.outbox]

    def flush_mailbox(self):
        mail.outbox = []

    def tearDown(self):
        super().tearDown()
        mail.outbox = []
