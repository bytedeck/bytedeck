from django_tenants.test.cases import TenantTestCase
from django.contrib.auth import get_user_model

from model_bakery import baker

from tags.models import total_xp_by_tags
from siteconfig.models import SiteConfig
from quest_manager.models import Quest, QuestSubmission
from badges.models import Badge, BadgeAssertion

User = get_user_model()


class Tag_total_xp_by_tags_Tests(TenantTestCase):
    """ 
        Specialized TestClass for testing total_xp_by_tags function
    """ 

    def setUp(self):
        self.user = baker.make(User)

    def create_quest_and_submissions(self, xp, quest_submission_quantity=1):
        """ 
            Creates and returns quest with linked quest submission objects
            Args
                xp - amount of xp quest obj will have
                quest_submission_quantity - how many submissions are crated
        """ 
        quest = baker.make(Quest, xp=xp)
        quest_submissions = baker.make(
            QuestSubmission, 
            quest=quest, 
            user=self.user, 
            is_completed=True, 
            is_approved=True, 
            semester=SiteConfig().get().active_semester,

            _quantity=quest_submission_quantity,
        )

        return quest, quest_submissions

    def create_badge_and_assertions(self, xp, badge_assertion_quantity=1):
        """ 
            Creates and returns badge with linked badge assertion objects
            Args
                xp - amount of xp badge obj will have
                badge_assertion_quantity - how many assertions are crated
        """ 
        badge = baker.make(Badge, xp=xp)
        badge_assertion = baker.make(BadgeAssertion, badge=badge, user=self.user, _quantity=badge_assertion_quantity,)

        return badge, badge_assertion

    # QUEST ONLY TESTS

    def test_one_tag_quests_only(self):
        """ 
            See if correct xp is returned using only 1 tag added to Quest objects
        """ 
        xp_list = [55, 84, 74, 85, 61, 61, 22, 39, 12, 46]

        for xp in xp_list:
            quest, _ = self.create_quest_and_submissions(xp)
            quest.tags.add("TAG")

        self.assertEqual(total_xp_by_tags(self.user, ["TAG"]), sum(xp_list))

    def test_multiple_separate_tags_quests_only(self):
        """ 
            See if correct xp is returned using only multiple tags added to Quest objects
            only 1 unique tag per quest
        """ 
        xp_list = [55, 84, 74, 85, 61]
        tag_list = ['tag-0', 'tag-1', 'tag-2', 'tag-3', 'tag-4']

        for i in range(len(xp_list)):
            quest, _ = self.create_quest_and_submissions(xp_list[i])
            quest.tags.add(tag_list[i])

        self.assertEqual(total_xp_by_tags(self.user, tag_list), sum(xp_list))

    def test_multiple_crossing_tags_quests_only(self):
        """ 
            See if correct xp is returned using only multiple tags added to Quest objects
            each quest object should have multiple tags
        """ 
        xp_list = [55, 84, 74, 85, 61]
        tag_tuples = [('tag0-0', 'tag1-0'), ('tag0-1', 'tag1-1'), ('tag0-2', 'tag1-2'), ('tag0-3', 'tag1-3'), ('tag0-4', 'tag1-4')]
    
        for i in range(len(xp_list)):
            quest, _ = self.create_quest_and_submissions(xp_list[i])
            quest.tags.add(tag_tuples[i][0])
            quest.tags.add(tag_tuples[i][1])

        unpacked_tag_tuples = [tag_tuple[index] for tag_tuple in tag_tuples for index in range(len(tag_tuple))]
        self.assertEqual(total_xp_by_tags(self.user, unpacked_tag_tuples), sum(xp_list))

    def test_one_tag_multiple_quests_only(self):
        """ 
            See if correct xp is returned using only one tag + quests with multiple questsubmissions
        """
        xp_list = [55, 84, 74, 85, 61, 61, 22, 39, 12, 46]
        quantity_list = [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]

        for i in range(len(xp_list)):
            quest, _ = self.create_quest_and_submissions(xp_list[i], quantity_list[i])
            quest.tags.add("TAG")

        calculated_xp = total_xp_by_tags(self.user, ["TAG"])
        expected_xp = sum(xp_list[i] * quantity_list[i] for i in range(len(xp_list)))
        self.assertEqual(calculated_xp, expected_xp)

    def test_one_tag_quests_only__different_semesters(self):
        """ 
            See if correct xp is returned using only one tag + quests with multiple questsubmissions in different semesters
        """ 
        semester_set = [SiteConfig().get().active_semester] + baker.make("courses.semester", _quantity=2)
        for semester in semester_set:
            quest, submissions = self.create_quest_and_submissions(100)
            quest.tags.add("TAG")

            submissions[0].semester = semester
            submissions[0].save()

        self.assertEqual(total_xp_by_tags(self.user, ["TAG"]), 100)

    # BADGE ONLY TESTS

    def test_one_tag_badges_only(self):
        """ 
            See if correct xp is returned using only 1 tag added to Badge objects
        """ 
        xp_list = [55, 84, 74, 85, 61, 61, 22, 39, 12, 46]
        
        for xp in xp_list:
            badge, _ = self.create_badge_and_assertions(xp)
            badge.tags.add("TAG")

        self.assertEqual(total_xp_by_tags(self.user, ["TAG"]), sum(xp_list))

    def test_multiple_separate_tags_badges_only(self):
        """ 
            See if correct xp is returned using only multiple tags added to Badge objects
            only 1 unique tag per badge
        """ 
        xp_list = [55, 84, 74, 85, 61]
        tag_list = ['tag-0', 'tag-1', 'tag-2', 'tag-3', 'tag-4']

        for i in range(len(xp_list)):
            badge, _ = self.create_badge_and_assertions(xp_list[i])
            badge.tags.add(tag_list[i])

        self.assertEqual(total_xp_by_tags(self.user, tag_list), sum(xp_list))

    def test_multiple_crossing_tags_badges_only(self):
        """ 
            See if correct xp is returned using only multiple tags added to Badge objects
            each Badge object should have multiple tags
        """ 
        xp_list = [55, 84, 74, 85, 61]
        tag_tuples = [('tag0-0', 'tag1-0'), ('tag0-1', 'tag1-1'), ('tag0-2', 'tag1-2'), ('tag0-3', 'tag1-3'), ('tag0-4', 'tag1-4')]
    
        for i in range(len(xp_list)):
            badge, _ = self.create_badge_and_assertions(xp_list[i])
            badge.tags.add(tag_tuples[i][0])
            badge.tags.add(tag_tuples[i][1])

        unpacked_tag_tuples = [tag_tuple[index] for tag_tuple in tag_tuples for index in range(len(tag_tuple))]
        self.assertEqual(total_xp_by_tags(self.user, unpacked_tag_tuples), sum(xp_list))

    def test_one_tag_multiple_badges_only(self):
        """ 
            See if correct xp is returned using only one tag + badges with multiple BadgeAssertions
        """
        xp_list = [55, 84, 74, 85, 61, 61, 22, 39, 12, 46]
        quantity_list = [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]

        for i in range(len(xp_list)):
            badge, _ = self.create_badge_and_assertions(xp_list[i], quantity_list[i])
            badge.tags.add("TAG")

        calculated_xp = total_xp_by_tags(self.user, ["TAG"])
        expected_xp = sum(xp_list[i] * quantity_list[i] for i in range(len(xp_list)))
        self.assertEqual(calculated_xp, expected_xp)

    def test_one_tag_badge_only__different_semesters(self):
        """ 
            See if correct xp is returned using only one tag + badges with multiple BadgeAssertions in different semesters
        """ 
        semester_set = [SiteConfig().get().active_semester] + baker.make("courses.semester", _quantity=2)
        for semester in semester_set:
            badge, assertions = self.create_badge_and_assertions(100)
            badge.tags.add("TAG")

            assertions[0].semester = semester
            assertions[0].save()

        self.assertEqual(total_xp_by_tags(self.user, ["TAG"]), 100)

    # QUEST + BADGE TESTS

    def test_one_tag_quests_badges(self):
        """ 
            See if correct xp is returned using only 1 tag added to Quest and Badge objects
        """ 
        xp_list = [
            55, 84, 74, 85, 61, 61, 22, 39, 12, 46, 
            36, 22, 93, 16, 2, 36, 28, 95, 10, 79, 
        ]
        
        for i in range(0, len(xp_list), 2):
            quest, _ = self.create_quest_and_submissions(xp_list[i])
            quest.tags.add("TAG")

            badge, _ = self.create_badge_and_assertions(xp_list[i + 1])
            badge.tags.add("TAG")

        self.assertEqual(total_xp_by_tags(self.user, ["TAG"]), sum(xp_list))

    def test_multiple_separate_tags_quests_badges(self):
        """ 
            See if correct xp is returned using only 1 tag added to Quest and Badge objects
            only 1 unique tag per quest and badge
        """ 
        xp_list = [55, 84, 74, 85, 61, 61, 22, 39, 12, 46]
        tag_list = ['tag-0', 'tag-1', 'tag-2', 'tag-3', 'tag-4', 'tag-5', 'tag-6', 'tag-7', 'tag-8', 'tag-9']

        for i in range(0, len(xp_list), 2):
            quest, _ = self.create_quest_and_submissions(xp_list[i])
            quest.tags.add(tag_list[i])
        
            badge, _ = self.create_badge_and_assertions(xp_list[i + 1])
            badge.tags.add(tag_list[i + 1])

        self.assertEqual(total_xp_by_tags(self.user, tag_list), sum(xp_list))

    def test_multiple_crossing_tags_quest_badges(self):
        """ 
            See if correct xp is returned using two tags per Quest and Badge object
            each Quest and Badge object should have multiple tags
        """ 
        xp_list = [55, 84, 74, 85, 61, 61, 22, 39, 12, 46]
        tag_tuples = [
            ('tag0-0', 'tag1-0'), ('tag0-1', 'tag1-1'), ('tag0-2', 'tag1-2'), ('tag0-3', 'tag1-3'), ('tag0-4', 'tag1-4'), 
            ('tag0-5', 'tag1-5'), ('tag0-6', 'tag1-6'), ('tag0-7', 'tag1-7'), ('tag0-8', 'tag1-8'), ('tag0-9', 'tag1-9')
        ]

        for i in range(0, len(xp_list), 2):
            quest, _ = self.create_quest_and_submissions(xp_list[i])
            quest.tags.add(tag_tuples[i][0])
            quest.tags.add(tag_tuples[i][1])
            
            badge, _ = self.create_badge_and_assertions(xp_list[i + 1])
            badge.tags.add(tag_tuples[i + 1][0])
            badge.tags.add(tag_tuples[i + 1][1])

        unpacked_tag_tuples = [tag_tuple[index] for tag_tuple in tag_tuples for index in range(len(tag_tuple))]
        self.assertEqual(total_xp_by_tags(self.user, unpacked_tag_tuples), sum(xp_list))
    
    def test_one_tag_multiple_quests_badges(self):
        """ 
             See if correct xp is returned using only one tag + quests and badges with multiple QuestSubmissions and BadgeAssertions
        """ 
        xp_list = [55, 84, 74, 85, 61, 61, 22, 39, 12, 46]
        quantity_list = [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]

        for i in range(0, len(xp_list), 2):
            quest, _ = self.create_quest_and_submissions(xp_list[i], quantity_list[i])
            quest.tags.add("TAG")

            badge, _ = self.create_badge_and_assertions(xp_list[i + 1], quantity_list[i + 1])
            badge.tags.add("TAG")

        calculated_xp = total_xp_by_tags(self.user, ["TAG"])
        expected_xp = sum(xp_list[i] * quantity_list[i] for i in range(len(xp_list)))
        self.assertEqual(calculated_xp, expected_xp)
