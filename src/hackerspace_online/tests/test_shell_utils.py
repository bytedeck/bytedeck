from django.contrib.auth import get_user_model

from django_tenants.test.cases import TenantTestCase

from hackerspace_online.shell_utils import generate_quests, generate_students
from quest_manager.models import Quest, Category

# from django_tenants.test.client import TenantClient


User = get_user_model()


class ShellUtilsTest(TenantTestCase):
    def setUp(self):
        # self.client = TenantClient(self.tenant)
        pass

    def test_generate_students(self):
        """Generates the provided number of students (20, is_staff = False)"""
        create_this_many = 20
        num_students_before = User.objects.filter(is_staff=False).count()
        generate_students(create_this_many, quiet=True)
        num_students_after = User.objects.filter(is_staff=False).count()
        self.assertEqual(num_students_after, num_students_before + create_this_many)

    def test_generate_quests(self):
        """Generates the provided number of students (10)"""
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
        quest_qs = Quest.objects.order_by('-pk')[: num_quest * num_campaigns]
        campaign_ids = set(quest_qs.values_list('campaign_id', flat=True))
        self.assertEqual(len(campaign_ids), num_campaigns)
