"""Tests for a group's report card data: the file builders in courses.report_cards and the
staff views that offer them."""
import csv
import datetime
import io
import json
import zipfile

from django.contrib.auth import get_user_model
from django.shortcuts import reverse
from django.utils import timezone

from model_bakery import baker

from badges.models import Badge, BadgeAssertion, BadgeType
from comments.models import Comment, Document
from courses import report_cards
from courses.models import Block, Course, CourseStudent, Grade, MarkRange, Rank, Semester
from courses.report_cards import (
    CUT_MARKER, EMAIL_PLACEHOLDER, KEY_COLUMNS, LINK_PLACEHOLDER, MAX_TEXT_LENGTH, PEER_PLACEHOLDER,
    STUDENT_PLACEHOLDER, NameScrubber, group_roster, html_to_text, report_card_data, student_code, student_key_csv,
)
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from quest_manager.models import Category, Quest, QuestSubmission
from questions.models import Question, QuestionSubmission
from siteconfig.models import SiteConfig

User = get_user_model()


def _moment(day):
    """Noon, local time, on a day given as "YYYY-MM-DD": far enough from midnight that the day
    it falls on does not depend on the time zone."""
    return timezone.make_aware(datetime.datetime.fromisoformat(f"{day}T12:00:00"))


class NameScrubberTests(ByteDeckTenantTestCase):
    """Replacing students' names, and addresses, in what was written."""

    def setUp(self):
        """A scrubber that knows two students: 1 is Jamie Smith-Lee (jsmith24), 2 is Will Brown."""
        self.scrubber = NameScrubber([
            (1, "Jamie", "Smith-Lee", "J", "jsmith24"),
            (2, "Will", "Brown", None, "wbrown"),
        ])

    def test_scrub__own_name_becomes_student_placeholder(self):
        """The names of the student the text belongs to are replaced with the student placeholder,
        each part of a hyphenated name by itself."""
        text = self.scrubber.scrub("Great work, Jamie! Signed, Jamie Smith-Lee.", 1)
        self.assertEqual(text, f"Great work, {STUDENT_PLACEHOLDER}! Signed, {STUDENT_PLACEHOLDER} {STUDENT_PLACEHOLDER}-{STUDENT_PLACEHOLDER}.")

    def test_scrub__another_students_name_becomes_peer_placeholder(self):
        """Another current student's name is replaced with the peer placeholder."""
        self.assertEqual(self.scrubber.scrub("I worked with Will Brown.", 1), f"I worked with {PEER_PLACEHOLDER} {PEER_PLACEHOLDER}.")

    def test_scrub__lower_case_word_is_left_alone(self):
        """A name that is also an ordinary word is only replaced where it is capitalized, so
        "I will fix it" keeps its sense."""
        self.assertEqual(self.scrubber.scrub("I will fix the brown border.", 1), "I will fix the brown border.")

    def test_scrub__word_with_a_digit_is_replaced_in_lower_case(self):
        """A username holding a digit is replaced however it is typed, since it is no ordinary word."""
        self.assertEqual(self.scrubber.scrub("my login is jsmith24", 1), f"my login is {STUDENT_PLACEHOLDER}")

    def test_scrub__single_letter_name_is_not_learned(self):
        """A one-letter name (an initial) is not replaced, or every sentence starting with it would be."""
        self.assertEqual(self.scrubber.scrub("J is for jump.", 1), "J is for jump.")

    def test_scrub__addresses_are_replaced_whole(self):
        """Web and email addresses are replaced, since they often carry their author's name."""
        text = self.scrubber.scrub("See https://github.com/jamiesmith/site and www.example.com or mail me@example.com", 1)
        self.assertEqual(text, f"See {LINK_PLACEHOLDER} and {LINK_PLACEHOLDER} or mail {EMAIL_PLACEHOLDER}")

    def test_clean__strips_html_and_replaces_names(self):
        """Typed HTML comes out as one line of text with the names replaced."""
        self.assertEqual(self.scrubber.clean("<p>Nice,&nbsp;<b>Jamie</b></p>\n<p>Keep going</p>", 1), f"Nice, {STUDENT_PLACEHOLDER} Keep going")

    def test_clean__cuts_long_text_short(self):
        """Text over the limit is cut to it and marked as cut."""
        text = self.scrubber.clean("x" * (MAX_TEXT_LENGTH + 50), 1)
        self.assertEqual(text, "x" * MAX_TEXT_LENGTH + CUT_MARKER)

    def test_html_to_text__nothing(self):
        """No HTML at all is no text."""
        self.assertEqual(html_to_text(None), "")


class ReportCardHelperTests(ByteDeckTenantTestCase):
    """The small pure helpers behind the files."""

    def test_student_code(self):
        """A student's code is made from their id."""
        self.assertEqual(student_code(42), "S42")

    def test_compact__keeps_zero(self):
        """Entries that say nothing are dropped, but a zero says something and stays."""
        record = {"a": 0, "b": None, "c": False, "d": "", "e": [], "f": {}, "g": "x"}
        self.assertEqual(report_cards._compact(record), {"a": 0, "g": "x"})

    def test_csv_cell__formula_is_defused(self):
        """A value a spreadsheet would run as a formula gets a leading apostrophe; others are untouched."""
        self.assertEqual(report_cards._csv_cell("=1+1"), "'=1+1")
        self.assertEqual(report_cards._csv_cell("Jamie"), "Jamie")
        self.assertEqual(report_cards._csv_cell(None), "")


class ReportCardDataTests(ByteDeckTenantTestCase):
    """The data file and the key file for a group."""

    @classmethod
    def setUpTestData(cls):
        """A group with two students in it, one of them also in a course in another group, and a
        third student in neither."""
        cls.teacher = User.objects.create_user('ms_teacher', is_staff=True, first_name='Terry', last_name='Teacher')
        cls.semester = SiteConfig.get().active_semester
        # a semester that is partway through whatever day the tests run on, so marks are not all 0
        cls.semester.first_day = timezone.localdate() - datetime.timedelta(days=30)
        cls.semester.last_day = timezone.localdate() + datetime.timedelta(days=30)
        cls.semester.save()

        cls.block = baker.make(Block, name='A Block')
        cls.other_block = baker.make(Block, name='B Block')
        cls.course = baker.make(Course, title='ADST 9', xp_for_100_percent=1000)
        cls.xp_only_course = baker.make(Course, title='Clubhouse', uses_marks=False)
        cls.grade_9 = Grade.objects.get_or_create(name='9', defaults={'value': 9})[0]

        cls.jamie = User.objects.create_user('jsmith24', first_name='Jamie', last_name='Smith')
        cls.jamie.profile.preferred_name = 'Jay'
        cls.jamie.profile.save()
        cls.will = User.objects.create_user('wbrown', first_name='Will', last_name='Brown')
        cls.grace = User.objects.create_user('glee', first_name='Grace', last_name='Lee')

        cls.jamie_registration = baker.make(
            CourseStudent, user=cls.jamie, course=cls.course, block=cls.block, semester=cls.semester,
            grade_fk=cls.grade_9, xp_adjustment=-20, xp_adjust_explanation='Jamie lost a bet',
        )
        cls.jamie_other_registration = baker.make(
            CourseStudent, user=cls.jamie, course=cls.xp_only_course, block=cls.other_block, semester=cls.semester,
        )
        cls.will_registration = baker.make(CourseStudent, user=cls.will, course=cls.course, block=cls.block, semester=cls.semester)
        baker.make(CourseStudent, user=cls.grace, course=cls.course, block=cls.other_block, semester=cls.semester)

    def _submission(self, quest, user=None, **kwargs):
        """An attempt at a quest in the open semester, by Jamie unless told otherwise."""
        return baker.make(QuestSubmission, quest=quest, user=user or self.jamie, semester=self.semester, **kwargs)

    def _comment(self, submission, user, text):
        """A comment on an attempt."""
        return Comment.objects.create_comment(user=user, text=text, path='/x/', target=submission)

    def _jamie(self, data):
        """Jamie's record in a data file."""
        return next(student for student in data["students"] if student["student_code"] == student_code(self.jamie.pk))

    def test_group_roster__lists_the_groups_current_students(self):
        """The roster is the students registered in the group in an open semester, each with every
        current registration they hold, including one in another group."""
        roster = group_roster(self.block)
        self.assertEqual([profile.user for profile, _registrations in roster], [self.jamie, self.will])
        self.assertEqual(roster[0][1], [self.jamie_registration, self.jamie_other_registration])
        self.assertEqual(roster[1][1], [self.will_registration])

    def test_group_roster__leaves_out_staff_test_archived_and_past_students(self):
        """Staff, test accounts, archived accounts and students only here in a closed semester are
        not in the roster."""
        closed = baker.make(Semester, status=Semester.Status.ARCHIVED)
        past = User.objects.create_user('past_student')
        baker.make(CourseStudent, user=past, course=self.course, block=self.block, semester=closed)
        baker.make(CourseStudent, user=self.teacher, course=self.course, block=self.block, semester=self.semester)
        tester = User.objects.create_user('tester')
        tester.profile.is_test_account = True
        tester.profile.save()
        baker.make(CourseStudent, user=tester, course=self.course, block=self.block, semester=self.semester)
        archived = User.objects.create_user('archived_student', is_active=False)
        baker.make(CourseStudent, user=archived, course=self.course, block=self.block, semester=self.semester)

        self.assertEqual([profile.user for profile, _registrations in group_roster(self.block)], [self.jamie, self.will])

    def test_student_key_csv__names_each_student(self):
        """The key file has a row per student giving the name behind their code, with their grade
        from this group's registration and all of their courses."""
        rows = list(csv.reader(io.StringIO(student_key_csv(self.block))))
        self.assertEqual(tuple(rows[0]), KEY_COLUMNS)
        self.assertEqual(rows[1], [student_code(self.jamie.pk), 'Smith', 'Jamie', 'Jay', 'jsmith24', '9', 'ADST 9; Clubhouse'])
        self.assertEqual(rows[2], [student_code(self.will.pk), 'Brown', 'Will', '', 'wbrown', '', 'ADST 9'])
        self.assertEqual(len(rows), 3)

    def test_student_key_csv__registration_without_a_course(self):
        """A registration whose course is gone adds nothing to the student's courses."""
        CourseStudent.objects.filter(pk=self.will_registration.pk).update(course=None)
        rows = list(csv.reader(io.StringIO(student_key_csv(self.block))))
        self.assertEqual(rows[2][-1], '')

    def test_report_card_data__about(self):
        """The file starts by saying what it is, how to read it, and what the deck's semester,
        courses, ranks, mark ranges and campaigns are."""
        campaign = baker.make(Category, title='Web Design', short_description='Build a site')
        baker.make(Quest, name='HTML Basics', campaign=campaign, xp=30)
        self._submission(baker.make(Quest, name='CSS Basics', campaign=campaign, xp=20))
        baker.make(Quest, name='Old one', campaign=campaign, xp=500, archived=True)
        baker.make(Quest, name='Draft one', campaign=campaign, xp=500, published=False)
        baker.make(Category, title='Never tried')
        baker.make(MarkRange, name='Passing', minimum_mark=49.5)

        about = report_card_data(self.block)["about"]

        self.assertEqual(about["group"], 'A Block')
        self.assertEqual(about["generated_on"], timezone.localdate().isoformat())
        self.assertEqual(about["how_to_read"], report_cards.HOW_TO_READ)
        self.assertEqual(about["semesters"], [{
            "semester": str(self.semester),
            "first_day": self.semester.first_day.isoformat(),
            "last_day": self.semester.last_day.isoformat(),
            "class_days_so_far": self.semester.days_so_far(),
            "class_days_in_all": self.semester.num_days(),
        }])
        # the XP-only course has no XP that makes 100%
        self.assertEqual(about["courses"], [{"course": 'ADST 9', "xp_for_100_percent": 1000}, {"course": 'Clubhouse'}])
        self.assertEqual(about["ranks"], [{"rank": rank.name, "from_xp": rank.xp} for rank in Rank.objects.get_ranks_cached()])
        self.assertIn({"mark_range": 'Passing', "from_percent": 49.5}, about["mark_ranges"])
        # only the campaign a student in the file has worked in, counting only its published, unarchived quests
        self.assertEqual(about["campaigns"], [{"campaign": 'Web Design', "description": 'Build a site', "quests": 2, "xp_available": 50}])

    def test_report_card_data__student_standing(self):
        """A student's record gives their grade, XP and rank, and for each course its share of
        their XP, its mark and mark range, and any XP adjustment with its reason (names replaced)."""
        baker.make(MarkRange, name='Everyone', minimum_mark=0)
        self.jamie.profile.xp_cached = 400
        self.jamie.profile.save()

        jamie = self._jamie(report_card_data(self.block))

        self.assertEqual(jamie["grade"], '9')
        self.assertEqual(jamie["total_xp"], 400)
        self.assertEqual(jamie["rank"], Rank.objects.get_rank(400).name)
        split = dict(CourseStudent.objects.xp_across(
            self.jamie, [self.jamie_registration, self.jamie_other_registration], profile=self.jamie.profile))
        adst, clubhouse = jamie["courses"]
        self.assertEqual(adst["course"], 'ADST 9')
        self.assertEqual(adst["group"], 'A Block')
        self.assertEqual(adst["semester"], str(self.semester))
        self.assertEqual(adst["xp"], round(split[self.jamie_registration]))
        self.assertEqual(adst["mark_percent"], round(self.jamie_registration.mark(xp=split[self.jamie_registration]), 1))
        self.assertGreater(adst["mark_percent"], 0)
        self.assertEqual(adst["mark_range"], MarkRange.objects.get_range(adst["mark_percent"], [self.course]).name)
        self.assertEqual(adst["xp_per_class_day"], round(self.jamie_registration.xp_per_day_ave(split[self.jamie_registration]), 1))
        self.assertEqual(adst["xp_adjustment"], -20)
        self.assertEqual(adst["xp_adjustment_reason"], f'{STUDENT_PLACEHOLDER} lost a bet')
        # a course run on XP alone has no mark, and this one has no adjustment
        self.assertEqual(clubhouse["course"], 'Clubhouse')
        for absent in ("mark_percent", "mark_range", "xp_adjustment", "xp_adjustment_reason"):
            self.assertNotIn(absent, clubhouse)

    def test_report_card_data__registration_without_a_course_or_grade(self):
        """A student whose registration has lost its course is still in the file, with no course
        named and no grade."""
        CourseStudent.objects.filter(pk=self.will_registration.pk).update(course=None)
        data = report_card_data(self.block)
        will = next(student for student in data["students"] if student["student_code"] == student_code(self.will.pk))
        self.assertNotIn("grade", will)
        self.assertNotIn("course", will["courses"][0])
        self.assertEqual(will["courses"][0]["group"], 'A Block')
        self.assertNotIn({"course": 'None'}, data["about"]["courses"])

    def test_report_card_data__quests(self):
        """Each attempt at a quest is listed, oldest first, with where it stands, what it earned
        and the days it moved on, and the work summary counts them."""
        campaign = baker.make(Category, title='Web Design')
        tagged = baker.make(Quest, name='HTML Basics', campaign=campaign, xp=30, max_repeats=-1)
        tagged.tags.add('html', 'web')
        loose = baker.make(Quest, name='Free Choice', xp=10, xp_can_be_entered_by_students=True)
        archived = baker.make(Quest, name='Retired Quest', campaign=campaign, xp=5, archived=True)

        first = self._submission(
            tagged, is_completed=True, is_approved=True, registration=self.jamie_registration, flagged_by=self.teacher,
            time_completed=_moment("2026-10-13"), time_returned=_moment("2026-10-12"), time_approved=_moment("2026-10-14"),
        )
        self._submission(
            tagged, ordinal=2, is_completed=True, is_approved=True, do_not_grant_xp=True,
            time_completed=_moment("2026-10-20"), time_approved=_moment("2026-10-21"),
        )
        self._submission(loose, is_completed=True, is_approved=True, xp_requested=25,
                         time_completed=_moment("2026-10-15"), time_approved=_moment("2026-10-16"))
        self._submission(archived, is_completed=True, time_completed=_moment("2026-10-22"))
        self._submission(baker.make(Quest, name='Sent Back', campaign=campaign), time_completed=_moment("2026-10-23"),
                         time_returned=_moment("2026-10-24"))
        self._submission(baker.make(Quest, name='Just Started'))
        # someone else's work, and Jamie's work from a semester that has ended, are not Jamie's this semester
        self._submission(tagged, user=self.grace, is_completed=True, is_approved=True)
        baker.make(QuestSubmission, quest=loose, user=self.jamie, is_completed=True, is_approved=True,
                   semester=baker.make(Semester, status=Semester.Status.ARCHIVED))
        QuestSubmission.objects.filter(pk=first.pk).update(timestamp=_moment("2026-10-10"))

        jamie = self._jamie(report_card_data(self.block))

        quests = {(quest["quest"], quest.get("attempt")): quest for quest in jamie["quests"]}
        self.assertEqual(len(jamie["quests"]), 6)
        self.assertEqual(jamie["quests"][0]["quest"], 'HTML Basics')
        self.assertEqual(quests[('HTML Basics', None)], {
            "quest": 'HTML Basics', "campaign": 'Web Design', "tags": ['html', 'web'], "status": 'approved', "xp_earned": 30,
            "counts_toward": 'ADST 9', "flagged_for_follow_up": True, "started_on": '2026-10-10',
            "handed_in_on": '2026-10-13', "returned_on": '2026-10-12', "approved_on": '2026-10-14',
        })
        repeat = quests[('HTML Basics', 2)]
        self.assertEqual((repeat["status"], repeat["xp_earned"], repeat["approved_without_xp"]), ('approved', 0, True))
        # a quest that lets students name their XP earned what was asked for
        self.assertEqual(quests[('Free Choice', None)]["xp_earned"], 25)
        self.assertNotIn("campaign", quests[('Free Choice', None)])
        self.assertEqual(quests[('Retired Quest', None)]["status"], 'awaiting approval')
        self.assertEqual(quests[('Sent Back', None)]["status"], 'returned')
        self.assertEqual(quests[('Just Started', None)]["status"], 'in progress')
        self.assertEqual(quests[('Just Started', None)]["xp_earned"], 0)

        self.assertEqual(jamie["work_summary"], {
            "quests_approved": 3, "quests_awaiting_approval": 1, "quests_returned": 1, "quests_in_progress": 1,
            "last_handed_in_on": '2026-10-23',
            # keyed by the Monday of the week the XP was approved in
            "xp_approved_by_week": {'2026-10-12': 55},
        })
        self.assertEqual(jamie["campaigns"], [
            # two attempts at one quest are one quest approved; the other two are not approved yet
            {"campaign": 'Web Design', "quests_approved": 1, "quests_not_yet_approved": 2, "xp_earned": 30},
        ])
        self.assertEqual(jamie["xp_by_tag"], {'html': 30, 'web': 30})

    def test_report_card_data__student_with_no_work(self):
        """A student who has done nothing yet has a record that says so."""
        jamie = self._jamie(report_card_data(self.block))
        self.assertEqual(jamie["work_summary"], {
            "quests_approved": 0, "quests_awaiting_approval": 0, "quests_returned": 0, "quests_in_progress": 0,
        })
        for absent in ("quests", "campaigns", "badges", "xp_by_tag"):
            self.assertNotIn(absent, jamie)

    def test_report_card_data__conversation(self):
        """The comments on an attempt are listed oldest first, saying who wrote each, with names and
        addresses replaced, attached files given by type only, and the student's answers."""
        quest = baker.make(Quest, name='Reflection')
        submission = self._submission(quest, is_completed=True, is_approved=True)
        handed_in = self._comment(submission, self.jamie, "<p>Done! I paired with Grace. See https://docs.example.com/jamie-smith</p>")
        Document.objects.create(comment=handed_in, docfile='documents/2026/10/14/jamie_smith_essay.PDF')
        Document.objects.create(comment=handed_in, docfile='documents/2026/10/14/README')
        question = baker.make(Question, quest=quest, ordinal=1, instructions='<p>What did you learn?</p>')
        baker.make(QuestionSubmission, quest_submission=submission, question=question, comment=handed_in,
                   response_text='Flexbox, with help from Will', is_correct=True)
        baker.make(QuestionSubmission, quest_submission=submission, question=None, comment=handed_in,
                   response_text='', response_file='quest/question/submission/jamie.png', is_correct=False)
        second_question = baker.make(Question, quest=quest, ordinal=2, instructions='Anything else?')
        baker.make(QuestionSubmission, quest_submission=submission, question=second_question, comment=handed_in, response_text='No')
        self._comment(submission, self.teacher, "<p>Lovely work Jamie.</p><p>The <b>Helper</b> badge was granted for this quest</p>")
        self._comment(submission, self.will, "nice one")
        # a comment on someone else's attempt is not part of this conversation
        self._comment(self._submission(quest, user=self.will), self.will, "mine")
        Comment.objects.filter(pk=handed_in.pk).update(timestamp=_moment("2026-10-14"))

        jamie = self._jamie(report_card_data(self.block))

        conversation = jamie["quests"][0]["conversation"]
        self.assertEqual([entry["from"] for entry in conversation], ['student', 'teacher', 'other'])
        self.assertEqual(conversation[0], {
            "from": 'student',
            "on": '2026-10-14',
            "text": f"Done! I paired with {PEER_PLACEHOLDER}. See {LINK_PLACEHOLDER}",
            "files": ['pdf', 'file'],
            "answers": [
                {"question": 'What did you learn?', "answer": f'Flexbox, with help from {PEER_PLACEHOLDER}', "marked": 'correct'},
                {"question": 'Anything else?', "answer": 'No'},
                # the answer to a question deleted since comes after the others
                {"file": 'png', "marked": 'wrong'},
            ],
        })
        self.assertEqual(conversation[1]["text"], f"Lovely work {STUDENT_PLACEHOLDER}. The Helper badge was granted for this quest")
        self.assertNotIn("files", conversation[1])
        self.assertNotIn("answers", conversation[1])

    def test_report_card_data__draft_comment_is_left_out(self):
        """What a student has typed but not handed in is not part of the conversation."""
        submission = self._submission(baker.make(Quest, name='Half done'))
        draft = self._comment(submission, self.jamie, "not ready yet")
        submission.draft_comment = draft
        submission.save()

        jamie = self._jamie(report_card_data(self.block))

        self.assertNotIn("conversation", jamie["quests"][0])

    def test_report_card_data__badges(self):
        """A student's badges from this semester are listed once each with every day they were
        granted, saying whether a teacher chose to grant them, and their XP counts toward their tags."""
        talent = baker.make(Badge, name='Coder', xp=5, short_description='<p>Wrote some code</p>',
                            badge_type=BadgeType.objects.get_or_create(name='Talent')[0])
        talent.tags.add('code')
        talent.add_simple_prereqs([baker.make(Quest)])
        award = baker.make(Badge, name='Helper', xp=10, badge_type=BadgeType.objects.get_or_create(name='Award')[0])
        award.tags.add('code')
        deck_ai = SiteConfig.get().deck_ai
        first = baker.make(BadgeAssertion, badge=talent, user=self.jamie, semester=self.semester, issued_by=deck_ai)
        baker.make(BadgeAssertion, badge=talent, user=self.jamie, semester=self.semester, issued_by=None, ordinal=2, do_not_grant_xp=True)
        baker.make(BadgeAssertion, badge=award, user=self.jamie, semester=self.semester, issued_by=self.teacher)
        # the deck's own account is a member of staff, who can grant by hand a badge that has no prerequisites
        manual = baker.make(Badge, name='Kind', xp=0, badge_type=award.badge_type)
        baker.make(BadgeAssertion, badge=manual, user=self.jamie, semester=self.semester, issued_by=deck_ai)
        # not this semester's, and not Jamie's
        baker.make(BadgeAssertion, badge=award, user=self.jamie, issued_by=self.teacher,
                   semester=baker.make(Semester, status=Semester.Status.ARCHIVED))
        baker.make(BadgeAssertion, badge=award, user=self.grace, semester=self.semester, issued_by=self.teacher)
        BadgeAssertion.objects.filter(pk=first.pk).update(timestamp=_moment("2026-10-01"))

        jamie = self._jamie(report_card_data(self.block))

        today = timezone.localdate().isoformat()
        self.assertEqual(jamie["badges"], [
            {"badge": 'Coder', "type": 'Talent', "description": 'Wrote some code', "xp_each": 5, "granted_by": 'automatic',
             "granted_on": ['2026-10-01', today]},
            {"badge": 'Helper', "type": 'Award', "xp_each": 10, "granted_by": 'teacher', "granted_on": [today]},
            {"badge": 'Kind', "type": 'Award', "xp_each": 0, "granted_by": 'teacher', "granted_on": [today]},
        ])
        # the badge granted without XP adds nothing
        self.assertEqual(jamie["xp_by_tag"], {'code': 15})

    def test_report_card_data__names_no_student(self):
        """The data file can be written as JSON, and no student's name, username or email is in it."""
        self.jamie.email = 'jamie.smith@example.com'
        self.jamie.save()
        submission = self._submission(baker.make(Quest, name='Portfolio'), is_completed=True)
        self._comment(submission, self.jamie, "By Jamie Smith (Jay), jsmith24, jamie.smith@example.com. Thanks Will Brown and Grace Lee!")

        text = json.dumps(report_card_data(self.block))

        for name in ('Jamie', 'Smith', 'Jay', 'jsmith24', 'example.com', 'Will', 'Brown', 'Grace', 'Lee', 'wbrown', 'glee'):
            self.assertNotIn(name, text)
        self.assertIn(student_code(self.jamie.pk), text)


class ReportCardViewTests(ByteDeckTenantTestCase):
    """The staff page that offers a group's report card files, and the two downloads."""

    @classmethod
    def setUpTestData(cls):
        """A teacher, and a group with one student in it."""
        cls.teacher = User.objects.create_user('ms_teacher', is_staff=True)
        cls.student = User.objects.create_user('jsmith24', first_name='Zoë', last_name='Smith')
        cls.block = baker.make(Block, name='A Block')
        baker.make(CourseStudent, user=cls.student, course=baker.make(Course), block=cls.block,
                   semester=SiteConfig.get().active_semester)
        cls.page = reverse('courses:report_card_data', args=[cls.block.pk])
        cls.data_file = reverse('courses:report_card_data_file', args=[cls.block.pk])
        cls.student_files = reverse('courses:report_card_student_files', args=[cls.block.pk])
        cls.key_file = reverse('courses:report_card_key_file', args=[cls.block.pk])

    #: The names of the page's URL and of its downloads'.
    URL_NAMES = (
        'courses:report_card_data', 'courses:report_card_data_file', 'courses:report_card_student_files',
        'courses:report_card_key_file',
    )

    def test_views__staff_only(self):
        """The page and its downloads send an anonymous visitor to sign in and refuse a student."""
        for name in self.URL_NAMES:
            self.assertRedirectsLogin(name, args=[self.block.pk])
        self.client.force_login(self.student)
        for name in self.URL_NAMES:
            self.assert403(name, args=[self.block.pk])

    def test_views__no_such_group(self):
        """A group that does not exist is a 404 on the page and on each download."""
        self.client.force_login(self.teacher)
        for name in self.URL_NAMES:
            self.assert404(name, args=[self.block.pk + 1000])

    def test_report_card_data__offers_both_files(self):
        """The page says how many students the files cover and links to each download."""
        self.client.force_login(self.teacher)
        response = self.client.get(self.page)
        self.assertContains(response, "Report card data: A Block")
        self.assertContains(response, "the 1 student")
        self.assertContains(response, self.data_file)
        self.assertContains(response, self.student_files)
        self.assertContains(response, self.key_file)

    def test_report_card_data__empty_group(self):
        """A group with no current students offers no downloads."""
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('courses:report_card_data', args=[baker.make(Block).pk]))
        self.assertContains(response, "nothing to download")
        self.assertNotContains(response, "students.json")

    def test_report_card_data_file__downloads_json(self):
        """The data file downloads as JSON, named for the group and the day."""
        self.client.force_login(self.teacher)
        response = self.client.get(self.data_file)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(
            response['Content-Disposition'],
            f'attachment; filename="report-card-data-a-block-{timezone.localdate().isoformat()}.json"',
        )
        data = json.loads(response.content)
        self.assertEqual([student["student_code"] for student in data["students"]], [student_code(self.student.pk)])
        self.assertEqual(data["about"]["group"], 'A Block')
        # accented letters are written as themselves, and the file is indented, to be readable
        self.assertIn('\n "students": [', response.content.decode())

    def test_report_card_student_files__downloads_zip(self):
        """The file per student downloads as a zip, each file holding the same "about" as the whole
        data file and its one student's record."""
        self.client.force_login(self.teacher)
        response = self.client.get(self.student_files)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/zip')
        self.assertEqual(
            response['Content-Disposition'],
            f'attachment; filename="report-card-data-a-block-{timezone.localdate().isoformat()}.zip"',
        )
        whole = json.loads(self.client.get(self.data_file).content)
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            self.assertEqual(archive.namelist(), [f"{student_code(self.student.pk)}.json"])
            one = json.loads(archive.read(archive.namelist()[0]))
        self.assertEqual(one, {"about": whole["about"], "student": whole["students"][0]})

    def test_report_card_key_file__downloads_csv(self):
        """The key file downloads as a CSV a spreadsheet reads as UTF-8, named for the group and the day."""
        self.client.force_login(self.teacher)
        response = self.client.get(self.key_file)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        self.assertEqual(
            response['Content-Disposition'],
            f'attachment; filename="report-card-key-a-block-{timezone.localdate().isoformat()}.csv"',
        )
        rows = list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
        self.assertTrue(response.content.startswith(b'\xef\xbb\xbf'))
        self.assertEqual(rows[1][:3], [student_code(self.student.pk), 'Smith', 'Zoë'])

    def test_group_page__links_to_report_card_data(self):
        """A group's own page has a button leading to its report card data."""
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('profiles:profile_list_block', args=[self.block.pk]))
        self.assertContains(response, self.page)
