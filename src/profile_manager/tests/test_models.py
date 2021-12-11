from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from model_bakery import baker
from model_bakery.recipe import Recipe
from tenant_schemas.test.cases import TenantTestCase

from siteconfig.models import SiteConfig

from courses.models import Semester
from profile_manager.models import Profile, smart_list

User = get_user_model()


class ProfileTestModel(TenantTestCase):

    def setUp(self):
        self.teacher = Recipe(User, is_staff=True).make()  # need a teacher or student creation will fail.
        self.user = baker.make(User)
        # Profiles are created automatically with each user, so we only need to access profiles via users
        self.profile = self.user.profile

        self.active_sem = SiteConfig.get().active_semester

        # Why is this required?  Why can't I just baker.make(Semester)?  For some reason when I
        # use baker.make(Semester) it tried to duplicate the pk, using pk=1 again?!
        self.inactive_sem = baker.make(Semester, pk=(SiteConfig.get().active_semester.pk + 1))

    def create_active_course_registration(self):
        return baker.make('courses.CourseStudent', user=self.user, semester=self.active_sem)

    def test_profile_creation(self):
        """Profile is automatically created when a user is created in setUp()"""
        self.assertIsInstance(self.user.profile, Profile)
        self.assertEqual(str(self.user.profile), self.user.username)

    def test_profile_deletion(self):
        """When a profile is deleted, via queryset (admin) or directly, the user should be deleted too. """
        Profile.objects.filter(pk=self.profile.pk).delete()
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

    def test_profile_alias_clipped(self):
        max_len = 16
        self.assertEqual(self.profile.alias_clipped(), "-")

        self.profile.alias = "Short Alias"
        self.assertEqual(self.profile.alias_clipped(), self.profile.alias)

        self.profile.alias = "Super duper duper long alias that's super duper long"
        self.assertEqual(len(self.profile.alias_clipped()), max_len)

    def test_profile_num_hidden_quests(self):
        self.assertEqual(self.profile.num_hidden_quests(), 0)

    def test_profile_get_hidden_quests_as_list(self):
        self.assertEqual(self.profile.get_hidden_quests_as_list(), [])

    def test_profile_hidden_quests(self):
        self.create_active_course_registration()
        num_to_hide = 3
        quests_to_hide = baker.make('quest_manager.quest', _quantity=num_to_hide)
        hidden_quest_list = [str(q.pk) for q in quests_to_hide]

        self.profile.save_hidden_quests_from_list(hidden_quest_list)

        self.assertEqual(self.profile.num_hidden_quests(), num_to_hide)

        quest_hidden = quests_to_hide[0]
        self.assertTrue(self.profile.is_quest_hidden(quest_hidden))

        quest_not_hidden = baker.make('quest_manager.quest')
        self.assertFalse(self.profile.is_quest_hidden(quest_not_hidden))
        self.assertEqual(self.profile.get_hidden_quests_as_list(), hidden_quest_list)

        self.profile.hide_quest(quest_not_hidden.id)
        self.assertTrue(self.profile.is_quest_hidden(quest_not_hidden))

        self.profile.unhide_quest(quest_hidden.id)
        self.assertFalse(self.profile.is_quest_hidden(quest_hidden))

    def test_num_hidden_quests_doesnt_include_unavailable(self):
        """If a hidden quest has been made unavailable for some reason (visible=False, etc) then it shouldn't count"""
        self.create_active_course_registration()
        quest = baker.make('quest_manager.quest', name='Hide Me')

        # hide a quest and check
        self.profile.hide_quest(quest.id)
        self.assertEqual(self.profile.num_hidden_quests(), 1)

        # make the quest invisible and it shouldn't appear in the hidden quest count
        quest.visible_to_students = False
        quest.save()
        self.assertEqual(self.profile.num_hidden_quests(), 0)

    def test_profile_current_courses(self):
        # no current courses to start
        self.assertFalse(self.profile.current_courses().exists())
        # add one and test
        course_registration = self.create_active_course_registration()
        self.assertQuerysetEqual(self.profile.current_courses(), [repr(course_registration)])
        # add a second
        course_registration2 = self.create_active_course_registration()
        self.assertQuerysetEqual(
            self.profile.current_courses(),
            [repr(course_registration), repr(course_registration2)]
        )

    def test_profile_has_current_course(self):
        self.assertFalse(self.profile.has_current_course)
        self.create_active_course_registration()
        profile = Profile.objects.get(pk=self.profile.id)  # Refresh profile to avoid cached_property
        self.assertTrue(profile.has_current_course)

    def test_profile_has_past_courses(self):
        self.assertFalse(self.profile.has_past_courses)
        baker.make('courses.CourseStudent', user=self.user, semester=self.inactive_sem)
        profile = Profile.objects.get(pk=self.profile.id)  # Refresh profile to avoid cached_property
        self.assertTrue(profile.has_past_courses)

    def test_profile_blocks(self):
        self.assertIsNone(self.profile.blocks())
        self.create_active_course_registration()
        self.assertIsNotNone(self.profile.blocks())
        # TODO fully test this with multiple blocks

    def test_profile_teachers(self):
        self.assertEqual(list(self.profile.teachers()), [])
        course_registration = self.create_active_course_registration()
        # Still no teachers since no teacher assign to this course's block yet
        # why is this a list of None instead of just empty? SQLite thing?
        self.assertEqual(list(self.profile.teachers()), [None])

        self.assertTrue(self.profile.has_current_course)
        course_registration.block = baker.make('courses.block', current_teacher=self.teacher)

        # TODO should have teachers now... why not working? Should not be None...
        # self.assertEqual(list(self.profile.teachers()), [None])

    def test_profile_current_teachers(self):
        self.assertFalse(self.profile.current_teachers().exists())

        course_registration = self.create_active_course_registration()

        # Still no teachers since no teacher assign to this course's block yet
        self.assertFalse(self.profile.current_teachers().exists())

        course_registration.block = baker.make('courses.block', current_teacher=self.teacher)

        # print(course_registration)
        # print(self.profile.current_teachers()) # why is this empty?!?!

    def test_rank(self):
        """ By default a new user has a rank"""
        default_starting_rank = "Digital Noob"
        self.assertEqual(self.profile.rank().name, default_starting_rank)


class SmartListTests(SimpleTestCase):

    def test_smart_list_empty(self):
        self.assertEqual(smart_list(''), [])
        self.assertEqual(smart_list([]), [])
        self.assertEqual(smart_list('[]'), [])
        self.assertEqual(smart_list(None), [])

    def test_smart_list_csv(self):
        self.assertEqual(smart_list('1,2,3'), ['1', '2', '3'])

    def test_smart_list_csv_delimeter(self):
        self.assertEqual(smart_list('1;2;3', delimiter=';'), ['1', '2', '3'])

    def test_smart_list_csv_to_int(self):
        self.assertEqual(smart_list('1,2,3', func=lambda x: int(x)), [1, 2, 3])

    def test_smart_list_tuple(self):
        self.assertEqual(smart_list((1, 2, 3)), [1, 2, 3])

    def test_smart_list_list(self):
        self.assertEqual(smart_list([1, 2, 3]), [1, 2, 3])

    def test_smart_list_int(self):
        self.assertEqual(smart_list(1), [1])
