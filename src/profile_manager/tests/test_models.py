from decimal import Decimal
from unittest.mock import Mock, patch
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import SimpleTestCase
from django.utils import timezone

from model_bakery import baker
from model_bakery.recipe import Recipe

from hackerspace_online.tests.utils import ByteDeckTenantTestCase

from badges.models import BadgeAssertion
from comments.models import Comment
from courses.models import CourseStudent, Semester
from notifications.models import Notification
from portfolios.models import Portfolio
from profile_manager.models import Profile, smart_list
from quest_manager.models import QuestSubmission
from siteconfig.models import SiteConfig

User = get_user_model()


class ProfileTestModel(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Create a teacher, a student user/profile, and active/inactive semesters."""
        cls.teacher = Recipe(User, is_staff=True).make()  # need a teacher or student creation will fail.
        cls.user = baker.make(User)
        # Profiles are created automatically with each user, so we only need to access profiles via users
        cls.profile = cls.user.profile

        cls.active_sem = SiteConfig.get().active_semester

        # Why is this required?  Why can't I just baker.make(Semester)?  For some reason when I
        # use baker.make(Semester) it tried to duplicate the pk, using pk=1 again?!
        cls.inactive_sem = baker.make(Semester, pk=(SiteConfig.get().active_semester.pk + 1))

    def create_active_course_registration(self):
        return baker.make('courses.CourseStudent', user=self.user, semester=self.active_sem, course=baker.make('courses.Course'))

    def test_mark_cached__stores_marks_above_999_9(self):
        """A profile mark above the old 999.9 ceiling saves and round-trips instead
        of raising DataError -- regression for #2035, where an uncapped early-semester
        mark projects to thousands of percent and overflowed the max_digits=4 column."""
        profile = self.user.profile
        profile.mark_cached = Decimal("1500.0")
        profile.save()  # would raise DataError on the old max_digits=4 field
        profile.refresh_from_db()
        self.assertEqual(profile.mark_cached, Decimal("1500.0"))

    def test_profile_creation__on_user_create(self):
        """Profile is automatically created when a user is created in setUp()"""
        self.assertIsInstance(self.user.profile, Profile)
        self.assertEqual(str(self.user.profile), self.user.username)

    def test_profile_deletion__cascades_to_user(self):
        """When a profile is deleted, via queryset (admin) or directly, the user should be deleted too. """
        Profile.objects.filter(pk=self.profile.pk).delete()
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

    def test_alias_clipped__truncates_long_alias(self):
        """alias_clipped() returns a placeholder when empty and truncates aliases past the max length."""
        max_len = 16
        self.assertEqual(self.profile.alias_clipped(), "-")

        self.profile.alias = "Short Alias"
        self.assertEqual(self.profile.alias_clipped(), self.profile.alias)

        self.profile.alias = "Super duper duper long alias that's super duper long"
        self.assertEqual(len(self.profile.alias_clipped()), max_len)

    def test_num_hidden_quests__zero_by_default(self):
        """A new profile has no hidden quests."""
        self.assertEqual(self.profile.num_hidden_quests(), 0)

    def test_get_hidden_quests_as_list__empty_by_default(self):
        """A new profile's hidden quest list is empty."""
        self.assertEqual(self.profile.get_hidden_quests_as_list(), [])

    def test_hidden_quests__hide_unhide_and_count(self):
        """Hiding, unhiding, and querying hidden quests behave consistently."""
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

    def test_num_hidden_quests__excludes_unavailable(self):
        """If a hidden quest has been made unavailable for some reason (published=False, etc) then it shouldn't count"""
        self.create_active_course_registration()
        quest = baker.make('quest_manager.quest', name='Hide Me')

        # hide a quest and check
        self.profile.hide_quest(quest.id)
        self.assertEqual(self.profile.num_hidden_quests(), 1)

        # make the quest invisible and it shouldn't appear in the hidden quest count
        quest.published = False
        quest.save()
        self.assertEqual(self.profile.num_hidden_quests(), 0)

    def test_current_courses__returns_active_registrations(self):
        """current_courses() returns each active-semester course registration for the profile."""
        # no current courses to start
        self.assertFalse(self.profile.current_courses().exists())
        # add one and test
        course_registration = self.create_active_course_registration()
        self.assertQuerySetEqual(self.profile.current_courses(), [course_registration])
        # add a second
        course_registration2 = self.create_active_course_registration()
        self.assertQuerySetEqual(
            self.profile.current_courses(),
            [course_registration, course_registration2]
        )

    def test_has_current_course__true_when_registered(self):
        """has_current_course is False until the student registers in the active semester."""
        self.assertFalse(self.profile.has_current_course)
        self.create_active_course_registration()
        profile = Profile.objects.get(pk=self.profile.id)  # Refresh profile to avoid cached_property
        self.assertTrue(profile.has_current_course)

    def test_has_past_courses__true_when_registered_in_inactive_semester(self):
        """has_past_courses becomes True once the student has a registration in an inactive semester."""
        self.assertFalse(self.profile.has_past_courses)
        baker.make('courses.CourseStudent', user=self.user, semester=self.inactive_sem)
        profile = Profile.objects.get(pk=self.profile.id)  # Refresh profile to avoid cached_property
        self.assertTrue(profile.has_past_courses)

    def test_blocks__none_until_registered(self):
        """blocks() is None until the student registers in a course."""
        self.assertIsNone(self.profile.blocks())
        self.create_active_course_registration()
        self.assertIsNotNone(self.profile.blocks())
        # TODO fully test this with multiple blocks

    def test_teachers__empty_until_registered(self):
        """teachers() is empty until the student has a course registration."""
        self.assertEqual(list(self.profile.teachers()), [])
        course_registration = self.create_active_course_registration()
        # Still no teachers since no teacher assign to this course's block yet
        # why is this a list of None instead of just empty? SQLite thing?
        self.assertEqual(list(self.profile.teachers()), [None])

        self.assertTrue(self.profile.has_current_course)
        course_registration.block = baker.make('courses.block', current_teacher=self.teacher)

        # TODO should have teachers now... why not working? Should not be None...
        # self.assertEqual(list(self.profile.teachers()), [None])

    def test_current_teachers__empty_until_teacher_assigned(self):
        """current_teachers() stays empty until a teacher is assigned to the student's block."""
        self.assertFalse(self.profile.current_teachers().exists())

        course_registration = self.create_active_course_registration()

        # Still no teachers since no teacher assign to this course's block yet
        self.assertFalse(self.profile.current_teachers().exists())

        course_registration.block = baker.make('courses.block', current_teacher=self.teacher)

        # print(course_registration)
        # print(self.profile.current_teachers()) # why is this empty?!?!

    def test_rank__default_for_new_user(self):
        """ By default a new user has a rank"""
        default_starting_rank = "Digital Noob"
        self.assertEqual(self.profile.rank().name, default_starting_rank)

    def test_mark__no_courses(self):
        """A student not in any current courses should return None"""
        # the test profile shouldn't be in any courses yet, but sanity check here
        self.assertFalse(self.profile.current_courses().exists())
        self.assertIsNone(self.profile.mark())

    @patch('profile_manager.models.Profile.current_courses')
    def test_mark__single_course(self, mock_current_courses):
        """mark() returns the single course's calculated mark."""
        mock_coursestudent = Mock()
        mock_coursestudent.calc_mark.return_value = 125
        mock_current_courses.return_value = [mock_coursestudent]
        self.assertEqual(self.profile.mark(), 125)

    @patch('profile_manager.models.Profile.current_courses')
    def test_mark__multiple_courses(self, mock_current_courses):
        """mark() divides the first course's mark by the number of courses."""
        mock_coursestudent1 = Mock()
        mock_coursestudent1.calc_mark.return_value = 87
        # The mark() method currently only checks the length of the list, and only uses the first course
        mock_current_courses.return_value = [mock_coursestudent1, "Another Course"]
        self.assertEqual(self.profile.mark(), 87 / 2)

    @patch('profile_manager.models.Profile.current_courses')
    def test_mark__cap_100(self, mock_current_courses):
        """Test that mark() caps at 100 if that SiteConfig option is set"""
        config = SiteConfig.get()
        config.cap_marks_at_100_percent = True
        config.save()

        mock_coursestudent1 = Mock()
        mock_coursestudent1.calc_mark.return_value = 125

        # The mark() method currently only checks the length of the list, and only uses the first course
        mock_current_courses.return_value = [mock_coursestudent1]
        self.assertEqual(self.profile.mark(), 100)

        # Add a second course, should not be capped anymore
        mock_current_courses.return_value = [mock_coursestudent1, "Another Course"]
        self.assertEqual(self.profile.mark(), 125 / 2)

        # What if both are over 100?
        mock_coursestudent1.calc_mark.return_value = 225
        self.assertEqual(self.profile.mark(), 100)

        # NEED TO RETURN SiteConfig object back to original state for other tests!
        config.cap_marks_at_100_percent = False
        config.save()


class SmartListTests(SimpleTestCase):

    def test_smart_list__empty_inputs(self):
        """smart_list() returns an empty list for empty/None-like inputs."""
        self.assertEqual(smart_list(''), [])
        self.assertEqual(smart_list([]), [])
        self.assertEqual(smart_list('[]'), [])
        self.assertEqual(smart_list(None), [])

    def test_smart_list__csv_string(self):
        """smart_list() splits a comma-separated string into a list of strings."""
        self.assertEqual(smart_list('1,2,3'), ['1', '2', '3'])

    def test_smart_list__custom_delimiter(self):
        """smart_list() splits on a custom delimiter when provided."""
        self.assertEqual(smart_list('1;2;3', delimiter=';'), ['1', '2', '3'])

    def test_smart_list__with_func(self):
        """smart_list() applies the given func to each element."""
        self.assertEqual(smart_list('1,2,3', func=lambda x: int(x)), [1, 2, 3])

    def test_smart_list__tuple_input(self):
        """smart_list() converts a tuple into a list."""
        self.assertEqual(smart_list((1, 2, 3)), [1, 2, 3])

    def test_smart_list__list_input(self):
        """smart_list() returns a list unchanged."""
        self.assertEqual(smart_list([1, 2, 3]), [1, 2, 3])

    def test_smart_list__single_int(self):
        """smart_list() wraps a single int in a list."""
        self.assertEqual(smart_list(1), [1])


class UserDeletionTest(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Create a student and related objects (badge, comment, notification, etc.) to test cascade deletion."""
        # Create a student user to be deleted
        cls.student = baker.make(User)

        # Create related objects for student user
        cls.badge_assertion = baker.make('BadgeAssertion', user=cls.student)
        # Give the GFK-bearing models explicit, real targets so baker doesn't fill
        # them with a random (possibly table-less) model under the reused schema.
        user_ct = ContentType.objects.get_for_model(User)
        cls.comment = baker.make('Comment', user=cls.student, target_content_type=None)
        cls.course_student = baker.make('CourseStudent', user=cls.student)
        cls.notification = baker.make(
            'Notification', recipient=cls.student,
            sender_content_type=user_ct, sender_object_id=cls.student.id,
        )
        cls.portfolio = baker.make('Portfolio', user=cls.student)
        cls.quest_submission = baker.make('QuestSubmission', user=cls.student)

    def test_delete_student__cascades_to_related_objects(self):
        """Deleting a student also deletes their badge, comment, registration, notification, portfolio, and submission."""
        # Ensure that the related objects exist before deletion
        self.assertTrue(self.badge_assertion.pk)
        self.assertTrue(self.comment.pk)
        self.assertTrue(self.course_student.pk)
        self.assertTrue(self.notification.pk)
        self.assertTrue(self.portfolio.pk)
        self.assertTrue(self.quest_submission.pk)

        # Perform direct user deletion for the student
        self.student.delete()

        # Check the user is deleted
        self.assertFalse(User.objects.filter(id=self.student.id).exists())

        # Check that the related objects are also deleted (cascade)
        self.assertRaises(BadgeAssertion.DoesNotExist, self.badge_assertion.refresh_from_db)
        self.assertRaises(Comment.DoesNotExist, self.comment.refresh_from_db)
        self.assertRaises(CourseStudent.DoesNotExist, self.course_student.refresh_from_db)
        self.assertRaises(Notification.DoesNotExist, self.notification.refresh_from_db)
        self.assertRaises(Portfolio.DoesNotExist, self.portfolio.refresh_from_db)
        self.assertRaises(QuestSubmission.DoesNotExist, self.quest_submission.refresh_from_db)


class ProfileNameMethodsTest(ByteDeckTenantTestCase):
    """Covers Profile's display-name variants and small string helpers."""

    def setUp(self):
        """A user with a real first/last name whose auto-created profile we exercise."""
        self.user = baker.make(User, first_name="Jane", last_name="Doe")
        self.profile = self.user.profile

    def test_str__includes_preferred_name_and_alias(self):
        """__str__ shows 'First (Preferred) Last, aka <clipped alias>' when all are set."""
        self.profile.preferred_name = "Janey"
        self.profile.alias = "JD"
        self.assertEqual(str(self.profile), "Jane (Janey) Doe, aka JD")

    def test_get_preferred_name__prefers_preferred_over_first_name(self):
        """get_preferred_name returns the preferred name when one is set."""
        self.profile.preferred_name = "Janey"
        self.assertEqual(self.profile.get_preferred_name(), "Janey")

    def test_preferred_full_name__appends_last_name(self):
        """With no preferred name, preferred_full_name is the first + last name."""
        self.assertEqual(self.profile.preferred_full_name(), "Jane Doe")

    def test_public_name__internal_only_returns_formal_name(self):
        """When preferred_internal_only is set, the public name falls back to the formal name."""
        self.profile.preferred_internal_only = True
        self.assertEqual(self.profile.public_name(), self.user.get_full_name())

    def test_internal_name__appends_clipped_alias(self):
        """internal_name appends ', aka <alias>' when an alias is set."""
        self.profile.alias = "JD"
        self.assertEqual(self.profile.internal_name(), "Jane Doe, aka JD")

    def test_formal_name__is_users_full_name(self):
        """formal_name is the user's full name."""
        self.assertEqual(self.profile.formal_name(), "Jane Doe")

    def test_get_avatar_url__returns_avatar_url_when_set(self):
        """get_avatar_url returns the avatar's own url once an avatar is set."""
        self.profile.avatar = "avatars/jane.png"
        self.assertTrue(self.profile.get_avatar_url().endswith("avatars/jane.png"))


class ProfileManagerAndQuerySetTest(ByteDeckTenantTestCase):
    """Covers the ProfileManager / ProfileQuerySet filter helpers."""

    def test_all_visible__filters_visible_to_other_students(self):
        """all_visible() returns only profiles flagged visible to other students."""
        Profile.objects.all().update(visible_to_other_students=True)
        self.assertTrue(Profile.objects.all_visible().exists())

    def test_all_inactive__includes_profiles_of_inactive_users(self):
        """all_inactive() returns the profiles of users whose accounts are inactive."""
        inactive_user = baker.make(User, is_active=False)
        self.assertIn(inactive_user.profile, Profile.objects.all_inactive())

    def test_queryset__announcement_email_filter(self):
        """The announcement_email queryset filter selects profiles opted into announcement emails."""
        Profile.objects.all().update(get_announcements_by_email=True)
        self.assertTrue(Profile.objects.get_queryset().announcement_email().exists())


class ProfileMiscMethodsTest(ByteDeckTenantTestCase):
    """Covers gone_stale, xp_to_next_rank, xp_since_last_rank, and the no-course chillax path."""

    def setUp(self):
        """A user whose auto-created profile we exercise."""
        self.user = baker.make(User)
        self.profile = self.user.profile

    def test_gone_stale__true_with_no_submissions(self):
        """A profile that has never submitted a quest is considered stale."""
        self.profile.time_of_last_submission = None
        self.assertTrue(self.profile.gone_stale())

    def test_gone_stale__true_when_last_submission_over_five_days_ago(self):
        """A profile whose last submission was more than five days ago is stale."""
        self.profile.time_of_last_submission = timezone.now() - timezone.timedelta(days=6)
        self.assertTrue(self.profile.gone_stale())

    def test_gone_stale__false_when_last_submission_is_recent(self):
        """A profile that submitted a quest just now is not stale."""
        self.profile.time_of_last_submission = timezone.now()
        self.assertFalse(self.profile.gone_stale())

    def test_xp_to_next_rank__zero_when_maxed_out(self):
        """When there is no next rank (maxed out), xp_to_next_rank is 0."""
        with patch.object(Profile, 'next_rank', return_value=None):
            self.assertEqual(self.profile.xp_to_next_rank(), 0)

    def test_xp_since_last_rank__zero_when_rank_lookup_fails(self):
        """xp_since_last_rank swallows a failed rank lookup and returns 0."""
        with patch.object(Profile, 'rank', side_effect=Exception("boom")):
            self.assertEqual(self.profile.xp_since_last_rank(), 0)

    def test_chillax__false_when_not_registered_in_a_course(self):
        """chillax() is False for a user with no current course."""
        self.assertFalse(self.profile.chillax())


class SmartListTest(SimpleTestCase):
    """Covers the module-level smart_list value parser."""

    def test_smart_list__parses_bracketed_delimited_string(self):
        """A bracketed, comma-separated string is split and mapped by func."""
        self.assertEqual(smart_list("[1, 2, 3]", func=int), [1, 2, 3])

    def test_smart_list__empty_after_stripping_returns_empty_list(self):
        """A bracket/whitespace-only string that strips to empty returns an empty list."""
        self.assertEqual(smart_list("[   ]"), [])

    def test_smart_list__wraps_a_bare_int_in_a_list(self):
        """A bare int is wrapped in a single-element list."""
        self.assertEqual(smart_list(7), [7])

    def test_smart_list__raises_valueerror_for_unparseable_type(self):
        """An unsupported value type raises ValueError."""
        with self.assertRaises(ValueError):
            smart_list(3.14)

    def test_smart_list__raises_valueerror_when_func_fails_on_an_element(self):
        """A per-element func that raises is re-raised as a ValueError."""
        with self.assertRaises(ValueError):
            smart_list("x,y", func=int)
