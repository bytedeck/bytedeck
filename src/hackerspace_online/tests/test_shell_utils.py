import io
from contextlib import redirect_stdout

from django.contrib.auth import get_user_model

from hackerspace_online.tests.utils import ByteDeckTenantTestCase

from hackerspace_online.shell_utils import generate_content, generate_quests, generate_students
from quest_manager.models import Quest, Category

# from django_tenants.test.client import TenantClient


User = get_user_model()


class ShellUtilsTest(ByteDeckTenantTestCase):
    def setUp(self):
        """No shared setup required for these shell-util tests."""
        # self.client = TenantClient(self.tenant)
        pass

    def test_generate_students__creates_requested_number(self):
        """ Generates the provided number of students (20, is_staff = False) """
        create_this_many = 20
        num_students_before = User.objects.filter(is_staff=False).count()
        generate_students(create_this_many, quiet=True)
        num_students_after = User.objects.filter(is_staff=False).count()
        self.assertEqual(num_students_after, num_students_before + create_this_many)

    def test_generate_quests__creates_requested_quests_and_campaigns(self):
        """ Generates the provided number of students (10) """
        num_quest = 5
        num_campaigns = 2

        num_quest_before = Quest.objects.count()
        num_campaigns_before = Category.objects.count()

        generate_quests(num_quest_per_campaign=num_quest, num_campaigns=num_campaigns, quiet=True)

        num_quests_after = Quest.objects.count()
        num_campaigns_after = Category.objects.count()

        # check if number of quest and campaigns is correct after generation
        self.assertEqual(num_campaigns_after, num_campaigns_before + num_campaigns)
        self.assertEqual(num_quests_after, num_quest_before + (num_quest * num_campaigns))

        # get the last (num_quest * num_campaigns) quests created and check if its related to only 2 campaigns
        quest_qs = Quest.objects.order_by('-pk')[:num_quest * num_campaigns]
        campaign_ids = set(quest_qs.values_list('campaign_id', flat=True))
        self.assertEqual(len(campaign_ids), num_campaigns)

    def test_generate_students__not_quiet_prints_progress(self):
        """With the default quiet=False, generate_students prints its progress and still creates the students."""
        before = User.objects.filter(is_staff=False).count()
        buf = io.StringIO()
        with redirect_stdout(buf):
            generate_students(2)
        output = buf.getvalue()
        self.assertIn("Generating 2 students", output)
        self.assertIn("2 students generated", output)
        self.assertEqual(User.objects.filter(is_staff=False).count(), before + 2)

    def test_generate_quests__not_quiet_prints_progress(self):
        """With the default quiet=False, generate_quests prints campaign/quest progress and its summary."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            generate_quests(num_quest_per_campaign=2, num_campaigns=1)
        output = buf.getvalue()
        self.assertIn("Generating content...", output)
        self.assertIn("2 Quests generated in 1 campaigns", output)

    def test_generate_content__not_quiet_generates_quests_and_students(self):
        """generate_content (quiet=False) runs both generators and prints the blank separator between them."""
        quests_before = Quest.objects.count()
        students_before = User.objects.filter(is_staff=False).count()
        buf = io.StringIO()
        with redirect_stdout(buf):
            generate_content(num_quest_per_campaign=1, num_campaigns=1, num_students=1)
        self.assertEqual(Quest.objects.count(), quests_before + 1)
        self.assertEqual(User.objects.filter(is_staff=False).count(), students_before + 1)
        # non-quiet run emits the blank separator between the two generators
        self.assertIn("\n", buf.getvalue())

    def test_generate_content__quiet_suppresses_the_separator(self):
        """generate_content(quiet=True) still generates content but prints nothing (no separator)."""
        quests_before = Quest.objects.count()
        buf = io.StringIO()
        with redirect_stdout(buf):
            generate_content(num_quest_per_campaign=1, num_campaigns=1, num_students=1, quiet=True)
        self.assertEqual(Quest.objects.count(), quests_before + 1)
        self.assertEqual(buf.getvalue(), "")
