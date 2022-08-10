from django_tenants.test.cases import TenantTestCase
from django.contrib.auth import get_user_model
from django.db.utils import ProgrammingError

from model_bakery import baker

from taggit.models import Tag
from tags.models import total_xp_by_tags, get_tags_from_user, get_user_tags_and_xp
from siteconfig.models import SiteConfig
from quest_manager.models import Quest, QuestSubmission
from badges.models import Badge, BadgeAssertion

User = get_user_model()


class TagHelper:

    def create_quest_and_submissions(self, xp, quest_submission_quantity=1):
        """
        Creates and returns quest with linked quest submission objects for self.user

        Args:
            xp (int): amount of xp quest object will have
            quest_submission_quantity (int, optional): how many submissions are created. Defaults to 1.

        Returns:
            tuple[Quest, list[QuestSubmission]]: tuple of Quest object + list of QuestSubmission objects
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
        Creates and returns badge with linked badge assertion objects that are also linked to self.user

        Args:
            xp (int): amount of xp badge obj will have
            badge_assertion_quantity (int, optional): how many assertions are created. Defaults to 1.. Defaults to 1.

        Returns:
            tuple[Badge, list[BadgeAssertion]]: tuple of Badge object + list of BadgeAssertion objects
        """
        badge = baker.make(Badge, xp=xp)
        badge_assertion = baker.make(BadgeAssertion, badge=badge, user=self.user, _quantity=badge_assertion_quantity,)

        return badge, badge_assertion


class Tag_get_user_tags_and_xp_Tests(TagHelper, TenantTestCase):
    """ 
        Specialized TestClass for testing get_user_tags_and_xp function
    """ 

    def setUp(self):
        self.user = baker.make(User)

    def test_unique_tag_quest_badges(self):
        """ 
            Unique tags per quest and badge, xp representing tag's index
        """
        # generate quests + submissions and assign a unique tag
        quest_tag_list = ['tag-0', 'tag-1', 'tag-2', 'tag-3', 'tag-4']
        for count, tag_name in enumerate(quest_tag_list):
            quest, _ = self.create_quest_and_submissions(count)
            quest.tags.add(tag_name)

        # Generates badge + assertions and assigns a unique tag
        badge_tag_list = ['tag-5', 'tag-6', 'tag-7', 'tag-8', 'tag-9']
        for count, tag_name in enumerate(badge_tag_list, start=len(quest_tag_list)):
            badge, _ = self.create_badge_and_assertions(count)
            badge.tags.add(tag_name)

        # see if tag names are in the same order
        expected_order = (quest_tag_list + badge_tag_list)[::-1]
        calculated_order = [tag_tuple[0].name for tag_tuple in get_user_tags_and_xp(self.user)]  # get tag names from func

        self.assertEqual(expected_order, calculated_order)

    def test_same_tag_per_quest_badges(self):
        """ 
            Same tag for quest and badges, xp representing tag's index
        """
        tag_list = ['tag-0', 'tag-1', 'tag-2', 'tag-3', 'tag-4']
        
        # Generates quest and badge + assigns both the same tag
        for count, tag_name in enumerate(tag_list):
            quest, _ = self.create_quest_and_submissions(count)
            quest.tags.add(tag_name)
        
            badge, _ = self.create_badge_and_assertions(count)
            badge.tags.add(tag_name)

        # see if tag names are in the same order
        expected_order = tag_list[::-1]
        calculated_order = [tag_tuple[0].name for tag_tuple in get_user_tags_and_xp(self.user)]  # get tag names from func
        
        self.assertEqual(expected_order, calculated_order)

    def test_multiple_tags_per_quest_badges(self):
        """ 
            Two tags per generated quest and badges, xp representing tag_tuples's index
        """
        # generate quests + submissions and assign quest 2 tags
        quest_tag_tuples = [('tag-0-0', 'tag-0-1'), ('tag-1-0', 'tag-1-1'), ('tag-2-0', 'tag-2-1'), ('tag-3-0', 'tag-3-1'), ('tag-4-0', 'tag-4-1')]
        for count, tag_tuple in enumerate(quest_tag_tuples):
            quest, _ = self.create_quest_and_submissions(count)
            quest.tags.add(tag_tuple[0])
            quest.tags.add(tag_tuple[1])

        # generate badge + assertions and assign badge 2 tags
        badge_tag_tuples = [('tag-5-0', 'tag-5-1'), ('tag-6-0', 'tag-6-1'), ('tag-7-0', 'tag-7-1'), ('tag-8-0', 'tag-8-1'), ('tag-9-0', 'tag-9-1')]
        for count, tag_tuple in enumerate(badge_tag_tuples, start=len(quest_tag_tuples)):
            badge, _ = self.create_badge_and_assertions(count)
            badge.tags.add(tag_tuple[0])
            badge.tags.add(tag_tuple[1])

        # sort by xp instead since 2 tags share the same total xp then their position is entirely up to sorted()
        expected_order = [xp for xp in range(len(quest_tag_tuples + badge_tag_tuples)) for i in range(2)][::-1]
        calculated_order = [tag_tuple[1] for tag_tuple in get_user_tags_and_xp(self.user)]  # get xp from func

        self.assertEqual(expected_order, calculated_order)


class Tag_get_tags_from_user_Tests(TagHelper, TenantTestCase):
    """ 
        Specialized TestClass for testing get_tags_from_user function
    """ 

    def setUp(self):
        self.user = baker.make(User)

    def test_unique_tag_per_quest_badges(self):
        """ 
            Unique tags per quest and badge
        """ 
        # Generates quest + submission and assigns a unique tag
        quest_tag_list = ['tag-0', 'tag-1', 'tag-2', 'tag-3', 'tag-4']
        for tag_name in quest_tag_list:
            quest, _ = self.create_quest_and_submissions(0)
            quest.tags.add(tag_name)
        
        # Generates badge + assertions and assigns a unique tag
        badge_tag_list = ['tag-5', 'tag-6', 'tag-7', 'tag-8', 'tag-9']
        for tag_name in badge_tag_list:
            badge, _ = self.create_badge_and_assertions(0)
            badge.tags.add(tag_name)

        tag_list = quest_tag_list + badge_tag_list
        tag_names = list(get_tags_from_user(self.user).order_by('name').values_list('name', flat=True))
        self.assertEqual(tag_names, tag_list)
    
    def test_same_tag_per_quest_badges(self):
        """ 
            Same tag for quest and badges
        """ 
        tag_list = ['tag-0', 'tag-1', 'tag-2', 'tag-3', 'tag-4']
        
        # Generates quest and badge + assigns both the same tag
        for tag_name in tag_list:
            quest, _ = self.create_quest_and_submissions(0)
            quest.tags.add(tag_name)
        
            badge, _ = self.create_badge_and_assertions(0)
            badge.tags.add(tag_name)

        tag_names = list(get_tags_from_user(self.user).order_by('name').values_list('name', flat=True))
        self.assertEqual(tag_names, tag_list)

    def test_multiple_tags_per_quest_badges(self):
        """ 
            Two tags per generated quest and badges
        """
        # generate quests + submissions and assign quest 2 tags
        quest_tag_tuples = [('tag-0-0', 'tag-0-1'), ('tag-1-0', 'tag-1-1'), ('tag-2-0', 'tag-2-1'), ('tag-3-0', 'tag-3-1'), ('tag-4-0', 'tag-4-1')]
        for tag_tuple in quest_tag_tuples:
            quest, _ = self.create_quest_and_submissions(0)
            quest.tags.add(tag_tuple[0])
            quest.tags.add(tag_tuple[1])

        # generate badge + assertions and assign badge 2 tags
        badge_tag_tuples = [('tag-5-0', 'tag-5-1'), ('tag-6-0', 'tag-6-1'), ('tag-7-0', 'tag-7-1'), ('tag-8-0', 'tag-8-1'), ('tag-9-0', 'tag-9-1')]
        for tag_tuple in badge_tag_tuples:
            badge, _ = self.create_badge_and_assertions(0)
            badge.tags.add(tag_tuple[0])
            badge.tags.add(tag_tuple[1])

        tag_tuples = quest_tag_tuples + badge_tag_tuples
        unpacked_tag_tuples = [tag_tuple[index] for tag_tuple in tag_tuples for index in range(len(tag_tuple))]
        tag_names = list(get_tags_from_user(self.user).order_by('name').values_list('name', flat=True))

        self.assertEqual(tag_names, unpacked_tag_tuples)


class Tag_total_xp_by_tags_Tests(TagHelper, TenantTestCase):
    """ 
        Specialized TestClass for testing total_xp_by_tags function
    """ 

    def setUp(self):
        self.user = baker.make(User)

    # MISC. TEST

    def test_list_input(self):
        """ 
            check if total_xp_by_tags can accept test without exception
        """ 
        try: 
            name = baker.make(Tag).name

            total_xp_by_tags(self.user, [])
            total_xp_by_tags(self.user, [name])
        except ProgrammingError:
            self.fail("total_xp_by_tags raised ProgrammingError when using list as input")
        
    def test_queryset_input(self):
        """ 
            check if total_xp_by_tags can accept a queryset without exception
        """ 
        try: 
            baker.make(Tag)

            total_xp_by_tags(self.user, Tag.objects.none())
            total_xp_by_tags(self.user, Tag.objects.all())
        except ProgrammingError:
            self.fail("total_xp_by_tags raised ProgrammingError when using queryset as input")
        
    # QUEST ONLY TESTS

    def test_one_tag_quests_only(self):
        """ 
            See if correct xp is returned using only 1 tag added to Quest objects
        """ 
        xp_list = [55, 84, 74, 85, 61, 61, 22, 39, 12, 46]

        # generate quests with same tag
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

        # generate quests with unique tag
        for xp, tag_name in zip(xp_list, tag_list):
            quest, _ = self.create_quest_and_submissions(xp)
            quest.tags.add(tag_name)

        self.assertEqual(total_xp_by_tags(self.user, tag_list), sum(xp_list))

    def test_multiple_crossing_tags_quests_only(self):
        """ 
            See if correct xp is returned using only multiple tags added to Quest objects
            each quest object should have multiple tags
        """ 
        xp_list = [55, 84, 74, 85, 61]
        tag_tuples = [('tag0-0', 'tag1-0'), ('tag0-1', 'tag1-1'), ('tag0-2', 'tag1-2'), ('tag0-3', 'tag1-3'), ('tag0-4', 'tag1-4')]

        # generate quests with 2 tags
        for xp, tag_tuple in zip(xp_list, tag_tuples):
            quest, _ = self.create_quest_and_submissions(xp)
            quest.tags.add(tag_tuple[0])
            quest.tags.add(tag_tuple[1])

        unpacked_tag_tuples = [tag_tuple[index] for tag_tuple in tag_tuples for index in range(len(tag_tuple))]
        self.assertEqual(total_xp_by_tags(self.user, unpacked_tag_tuples), sum(xp_list))

    def test_one_tag_multiple_quests_only(self):
        """ 
            See if correct xp is returned using only one tag + quests with multiple questsubmissions
        """
        xp_list = [55, 84, 74, 85, 61, 61, 22, 39, 12, 46]
        quantity_list = [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]

        # generate quests with x amount of submissions and 1 tag
        for xp, quantity in zip(xp_list, quantity_list):
            quest, _ = self.create_quest_and_submissions(xp, quantity)
            quest.tags.add("TAG")

        calculated_xp = total_xp_by_tags(self.user, ["TAG"])
        expected_xp = sum(xp_list[i] * quantity_list[i] for i in range(len(xp_list)))
        self.assertEqual(calculated_xp, expected_xp)

    def test_one_tag_quests_only__different_semesters(self):
        """ 
            See if correct xp is returned using only one tag + quests with multiple questsubmissions in different semesters
        """ 
        # generate quest in active sem
        quest, submissions = self.create_quest_and_submissions(100)
        quest.tags.add("TAG")

        submissions[0].semester = SiteConfig().get().active_semester
        submissions[0].save()

        # generate quests outside of active sem
        semester_set = baker.make("courses.semester", _quantity=2)
        for semester in semester_set:
            quest, submissions = self.create_quest_and_submissions(399)
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
        
        # generate badges with same tag
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

        # generate badges with unique tag
        for xp, tag_name in zip(xp_list, tag_list):
            badge, _ = self.create_badge_and_assertions(xp)
            badge.tags.add(tag_name)

        self.assertEqual(total_xp_by_tags(self.user, tag_list), sum(xp_list))

    def test_multiple_crossing_tags_badges_only(self):
        """ 
            See if correct xp is returned using only multiple tags added to Badge objects
            each Badge object should have multiple tags
        """ 
        xp_list = [55, 84, 74, 85, 61]
        tag_tuples = [('tag0-0', 'tag1-0'), ('tag0-1', 'tag1-1'), ('tag0-2', 'tag1-2'), ('tag0-3', 'tag1-3'), ('tag0-4', 'tag1-4')]

        # generate badges with 2 tags
        for xp, tag_name in zip(xp_list, tag_tuples):
            badge, _ = self.create_badge_and_assertions(xp)
            badge.tags.add(tag_name[0])
            badge.tags.add(tag_name[1])

        unpacked_tag_tuples = [tag_tuple[index] for tag_tuple in tag_tuples for index in range(len(tag_tuple))]
        self.assertEqual(total_xp_by_tags(self.user, unpacked_tag_tuples), sum(xp_list))

    def test_one_tag_multiple_badges_only(self):
        """ 
            See if correct xp is returned using only one tag + badges with multiple BadgeAssertions
        """
        xp_list = [55, 84, 74, 85, 61, 61, 22, 39, 12, 46]
        quantity_list = [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]

        # generate badges with x amount of assertions and 1 tag
        for xp, quantity in zip(xp_list, quantity_list):
            badge, _ = self.create_badge_and_assertions(xp, quantity)
            badge.tags.add("TAG")

        calculated_xp = total_xp_by_tags(self.user, ["TAG"])
        expected_xp = sum(xp_list[i] * quantity_list[i] for i in range(len(xp_list)))
        self.assertEqual(calculated_xp, expected_xp)

    def test_one_tag_badge_only__different_semesters(self):
        """ 
            See if correct xp is returned using only one tag + badges with multiple BadgeAssertions in different semesters
        """ 
        # generate quest in active sem
        badge, assertions = self.create_quest_and_submissions(100)
        badge.tags.add("TAG")

        assertions[0].semester = SiteConfig().get().active_semester
        assertions[0].save()

        # generate quests outside of active sem
        semester_set = baker.make("courses.semester", _quantity=2)
        for semester in semester_set:
            badge, assertions = self.create_quest_and_submissions(399)
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
        
        # Generates quest and badge + assigns both a tag
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

        # Generates quest and badge + assigns both a unique tag
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

        # Generates quest and badge + assigns both a unique tag
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

        # generate quests and badges with x amount of submissions/assertions and 1 tag
        for i in range(0, len(xp_list), 2):
            quest, _ = self.create_quest_and_submissions(xp_list[i], quantity_list[i])
            quest.tags.add("TAG")

            badge, _ = self.create_badge_and_assertions(xp_list[i + 1], quantity_list[i + 1])
            badge.tags.add("TAG")

        calculated_xp = total_xp_by_tags(self.user, ["TAG"])
        expected_xp = sum(xp_list[i] * quantity_list[i] for i in range(len(xp_list)))
        self.assertEqual(calculated_xp, expected_xp)
