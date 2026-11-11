"""Report card data: what a group's students have done this semester, gathered into one file a
teacher can hand to an AI model to draft report card comments from.

The file names no student. Each one is known by a code (see student_code), and the names of the
deck's current students are replaced wherever they turn up in what was written (see NameScrubber),
so the file can leave the deck while the key that turns a code back into a name (student_key_csv)
stays with the teacher.
"""

import csv
import io
import json
import os
import re
import zipfile
from collections import defaultdict
from datetime import timedelta

from bs4 import BeautifulSoup
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Prefetch, Sum
from django.utils import timezone

from badges.models import Badge, BadgeAssertion
from comments.models import Comment
from prerequisites.models import Prereq
from profile_manager.models import Profile
from quest_manager.models import Category, Quest, QuestSubmission
from questions.models import QuestionSubmission
from siteconfig.models import SiteConfig

from .models import CourseStudent, MarkRange, Rank, Semester

#: Stands in for the name of the student a record is about, wherever it turned up in their work.
STUDENT_PLACEHOLDER = "[STUDENT]"
#: Stands in for the name of any other current student.
PEER_PLACEHOLDER = "[PEER]"
#: Stands in for a web address, which often names its author (a shared document, a code repository).
LINK_PLACEHOLDER = "[link]"
#: Stands in for an email address.
EMAIL_PLACEHOLDER = "[email]"

#: The most characters of one piece of writing (a comment, an answer) the file carries. A comment
#: is seldom longer unless something was pasted into it, and thirty students' pasted code would
#: crowd out the conversations the file is for.
MAX_TEXT_LENGTH = 2000
#: Ends a piece of writing that was longer than MAX_TEXT_LENGTH.
CUT_MARKER = " [cut short]"

#: The columns of the key file (see student_key_csv).
KEY_COLUMNS = ("student_code", "last_name", "first_name", "preferred_name", "username", "grade", "courses")

_WORD_RE = re.compile(r"[^\W_]+")
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\S+@\S+\.\S+")

#: What the file tells its reader about itself, so the AI model reading it needs nothing explained.
HOW_TO_READ = {
    "student_code": "Stands in for the student's name, which is not in this file. Use the code, or "
                    f"{STUDENT_PLACEHOLDER}, wherever the student's name would go.",
    "names": f"{STUDENT_PLACEHOLDER} replaces the student's own name in what was written, and {PEER_PLACEHOLDER} "
             f"another student's. {LINK_PLACEHOLDER} and {EMAIL_PLACEHOLDER} replace web and email addresses.",
    "xp": "Experience points. A student earns a quest's XP when a teacher approves their work on it, "
          "and a badge's XP when the badge is granted.",
    "quests": "A quest is one piece of course work. Each entry is one attempt, oldest first. Its status is "
              "'approved', 'awaiting approval' (handed in, not yet looked at), 'returned' (handed back for "
              "more work, not yet handed in again) or 'in progress' (started, never handed in). 'returned_on' "
              "is the last time it was handed back, even if it was approved later.",
    "conversation": "What the student and their teachers wrote to each other about that attempt, oldest first. "
                    "'answers' are the student's answers to the questions the quest asks. Text longer than "
                    f"{MAX_TEXT_LENGTH} characters ends with '{CUT_MARKER.strip()}'. 'files' lists the types of the "
                    "files attached, not their names.",
    "campaigns": "A campaign is a set of related quests. 'about.campaigns' describes each one the students in "
                 "this file have worked in, and how many quests and how much XP it offers.",
    "badges": "Recognition for an accomplishment. 'granted_by' is 'automatic' when the badge came from meeting "
              "its prerequisites and 'teacher' when a teacher chose to grant it. A badge a teacher granted while "
              "approving a quest is also noted in that quest's conversation ('The ... badge was granted for this "
              "quest').",
    "mark_percent": "The course mark so far: the student's XP as a percentage of the XP expected by this point "
                    "in the semester for 100% ('xp_for_100_percent' is the full semester's). Absent for a course "
                    "that runs on XP alone.",
    "xp_approved_by_week": "XP from quests approved in each week, keyed by the Monday that starts it. A week "
                           "that is missing had no work approved.",
    "xp_by_tag": "XP from the quests and badges listed here, by the topic tags on them. A quest with two tags "
                 "counts toward both.",
}


def student_code(user_id):
    """The code a student is known by in the data file.

    It is made from their account's id, so it stays the same from one download to the next and the
    key file always matches the data file, whenever each was downloaded.

    Args:
        user_id (int): the student's User pk.

    Returns:
        str: the code, e.g. "S42".
    """
    return f"S{user_id}"


def html_to_text(html):
    """The words of a piece of HTML that a person typed, on one line.

    Args:
        html (str or None): the HTML, e.g. a comment's text.

    Returns:
        str: its text with the tags gone and every run of whitespace collapsed to one space.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    return " ".join(soup.get_text(" ").split())


class NameScrubber:
    """Replaces students' names in text, so writing can leave the deck without saying whose it is.

    A word is replaced when it is one of the words in a current student's first name, last name,
    preferred name or username, and it starts with a capital letter or holds a digit. Words that
    start in lower case are left alone, since so many names are also ordinary words (will, mark,
    grace) that replacing those would take the sense out of what was written. Web and email
    addresses are replaced whole, since they often carry a name.

    It is a best effort: a nickname, a misspelling, or a name typed without its capital is not
    caught.
    """

    def __init__(self, students):
        """
        Args:
            students (iterable): a (user_id, name, ...) tuple for each student whose names are to
                be replaced. A name may be None or empty.
        """
        self._owners = {}
        for user_id, *names in students:
            for name in names:
                for word in _WORD_RE.findall(name or ""):
                    # a single letter (an initial) would match every sentence that starts with it
                    if len(word) > 1:
                        self._owners.setdefault(word.lower(), set()).add(user_id)

    def scrub(self, text, student_id):
        """Replace names and addresses in a piece of text.

        Args:
            text (str): plain text.
            student_id (int): the User pk of the student the text belongs to, whose own name
                becomes STUDENT_PLACEHOLDER while every other student's becomes PEER_PLACEHOLDER.

        Returns:
            str: the text with the replacements made.
        """
        def replace(match):
            """The placeholder for a word that is a student's name, else the word itself."""
            word = match.group()
            owners = self._owners.get(word.lower())
            if not owners or not (word[0].isupper() or any(character.isdigit() for character in word)):
                return word
            return STUDENT_PLACEHOLDER if student_id in owners else PEER_PLACEHOLDER

        text = _URL_RE.sub(LINK_PLACEHOLDER, text)
        text = _EMAIL_RE.sub(EMAIL_PLACEHOLDER, text)
        return _WORD_RE.sub(replace, text)

    def clean(self, html, student_id):
        """A piece of typed HTML as text that is ready for the data file.

        Args:
            html (str or None): the HTML, e.g. a comment's text.
            student_id (int): the User pk of the student it belongs to (see scrub).

        Returns:
            str: its text with names and addresses replaced, cut to MAX_TEXT_LENGTH.
        """
        text = self.scrub(html_to_text(html), student_id)
        if len(text) > MAX_TEXT_LENGTH:
            text = text[:MAX_TEXT_LENGTH].rstrip() + CUT_MARKER
        return text


def _compact(record):
    """A record without the entries that say nothing, so the file holds no "campaign": null lines.

    Args:
        record (dict): the record.

    Returns:
        dict: the record without the entries whose value is None, False, or empty. A zero stays: no
        XP is something to say.
    """
    return {
        key: value for key, value in record.items()
        if value is not None and value is not False and value != "" and value != [] and value != {}
    }


def _day(moment):
    """The local date of a moment, as text.

    Args:
        moment (datetime or None): an aware datetime.

    Returns:
        str or None: the date in ISO format, e.g. "2026-11-13", or None when there is no moment.
    """
    return timezone.localtime(moment).date().isoformat() if moment else None


def _file_type(file):
    """The type of an attached file, which is all the data file says about it (its name is left
    out, since a student's files are so often named after them).

    Args:
        file: a FieldFile.

    Returns:
        str: the file's extension in lower case without its dot, or "file" when it has none.
    """
    return os.path.splitext(file.name)[1].lstrip(".").lower() or "file"


def group_roster(block):
    """The students currently in a group, each with the courses they are taking.

    The students are the ones the group's own page lists (ProfileListBlock): registered in the
    group in a semester that is open right now, leaving out staff, test accounts and archived
    accounts. Each comes with every registration they hold in that semester, including any that
    are in another group, since their XP is shared between all of their courses.

    Args:
        block (Block): the group.

    Returns:
        list[tuple]: (Profile, list[CourseStudent]) for each student, ordered by the student's id.
    """
    in_group = CourseStudent.objects.filter(
        block=block, semester__status=Semester.Status.OPEN,
    ).values_list('user_id', flat=True)
    profiles = list(Profile.objects.all_in_open_semesters().filter(user_id__in=in_group).order_by('user_id'))

    registrations = defaultdict(list)
    current = CourseStudent.objects.filter(
        user_id__in=[profile.user_id for profile in profiles], semester__status=Semester.Status.OPEN,
    ).select_related('course', 'block', 'semester', 'grade_fk').order_by('pk')
    for registration in current:
        registrations[registration.user_id].append(registration)
    return [(profile, registrations[profile.user_id]) for profile in profiles]


def _grade(registrations, block):
    """A student's grade: the one on their registration in this group, else on any other.

    Args:
        registrations (list[CourseStudent]): the student's current registrations.
        block (Block): the group the file is for.

    Returns:
        str or None: the grade's name, e.g. "9", or None when no registration of theirs has one.
    """
    in_group_first = sorted(registrations, key=lambda registration: registration.block_id != block.pk)
    return next((registration.grade_fk.name for registration in in_group_first if registration.grade_fk), None)


def _csv_cell(value):
    """A value as a spreadsheet cell that is always read as text.

    A spreadsheet reads a cell that starts with =, +, - or @ as a formula, and a student chooses
    their own name, so such a cell gets a leading apostrophe:
    https://owasp.org/www-community/attacks/CSV_Injection

    Args:
        value: the value, or None for an empty cell.

    Returns:
        str: the cell's text.
    """
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text


def student_key_csv(block):
    """The key file: who each code in the group's data file stands for.

    Args:
        block (Block): the group.

    Returns:
        str: a CSV with a row per student, in the order of the data file, under KEY_COLUMNS.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(KEY_COLUMNS)
    for profile, registrations in group_roster(block):
        user = profile.user
        courses = "; ".join(str(registration.course) for registration in registrations if registration.course)
        row = (
            student_code(user.pk), user.last_name, user.first_name, profile.preferred_name, user.username,
            _grade(registrations, block), courses,
        )
        writer.writerow([_csv_cell(value) for value in row])
    return output.getvalue()


def _submission_status(submission):
    """Where an attempt at a quest stands, in the words HOW_TO_READ explains.

    Args:
        submission (QuestSubmission): the attempt.

    Returns:
        str: "approved", "awaiting approval", "returned" or "in progress".
    """
    if submission.is_approved:
        return "approved"
    if submission.is_completed:
        return "awaiting approval"
    if submission.is_returned():
        return "returned"
    return "in progress"


def _xp_earned(submission):
    """The XP an attempt earned: the quest's, or what the student asked for when the quest lets them.

    Args:
        submission (QuestSubmission): the attempt.

    Returns:
        int: the XP, 0 until the attempt is approved or when it was approved without XP.
    """
    if not submission.is_approved or submission.do_not_grant_xp:
        return 0
    return max(submission.quest.xp, submission.xp_requested)


def _author(comment, student_id):
    """Who wrote a comment, as their part in the conversation.

    Args:
        comment (Comment): the comment, with its user loaded.
        student_id (int): the User pk of the student whose work the comment is on.

    Returns:
        str: "student", "teacher", or "other" for anyone else (another student).
    """
    if comment.user_id == student_id:
        return "student"
    return "teacher" if comment.user.is_staff else "other"


def _conversation(comments, student_id, scrubber):
    """The comments on one attempt at a quest, ready for the data file.

    Args:
        comments (list[Comment]): the comments, oldest first, with their documents and their
            published answers prefetched.
        student_id (int): the User pk of the student whose attempt it is.
        scrubber (NameScrubber): replaces names in what was written.

    Returns:
        list[dict]: an entry per comment.
    """
    entries = []
    for comment in comments:
        answers = [
            _compact({
                # a question deleted since leaves its answers behind (QuestionSubmission.question)
                "question": scrubber.clean(answer.question.instructions, student_id) if answer.question else None,
                "answer": scrubber.clean(answer.response_text, student_id),
                "file": _file_type(answer.response_file) if answer.response_file else None,
                "marked": {True: "correct", False: "wrong"}.get(answer.is_correct),
            })
            for answer in comment.question_submissions.all()
        ]
        entries.append(_compact({
            "from": _author(comment, student_id),
            "on": _day(comment.timestamp),
            "text": scrubber.clean(comment.text, student_id),
            "files": [_file_type(document.docfile) for document in comment.document_set.all()],
            "answers": answers,
        }))
    return entries


def _quest_entries(submissions, comments, student_id, scrubber):
    """A student's attempts at quests, ready for the data file.

    Args:
        submissions (list[QuestSubmission]): the student's attempts, oldest first.
        comments (dict): the comments on each attempt, by the attempt's pk.
        student_id (int): the student's User pk.
        scrubber (NameScrubber): replaces names in what was written.

    Returns:
        list[dict]: an entry per attempt.
    """
    entries = []
    for submission in submissions:
        quest = submission.quest
        registration = submission.registration
        entries.append(_compact({
            "quest": quest.name,
            "campaign": quest.campaign.title if quest.campaign else None,
            "tags": [tag.name for tag in quest.tags.all()],
            "status": _submission_status(submission),
            "xp_earned": _xp_earned(submission),
            # a quest that can be repeated is listed once per attempt
            "attempt": submission.ordinal if submission.ordinal > 1 else None,
            "counts_toward": str(registration.course) if registration and registration.course else None,
            "approved_without_xp": submission.is_approved and submission.do_not_grant_xp,
            "flagged_for_follow_up": submission.flagged_by_id is not None,
            "started_on": _day(submission.timestamp),
            "handed_in_on": _day(submission.time_completed),
            "returned_on": _day(submission.time_returned),
            "approved_on": _day(submission.time_approved),
            "conversation": _conversation(comments.get(submission.pk, []), student_id, scrubber),
        }))
    return entries


def _work_summary(submissions):
    """How much a student has done and when, counted from their attempts at quests.

    Args:
        submissions (list[QuestSubmission]): the student's attempts.

    Returns:
        dict: how many attempts stand at each status, the last day anything was handed in, and the
        XP approved in each week (see HOW_TO_READ).
    """
    counts = defaultdict(int)
    by_week = defaultdict(int)
    for submission in submissions:
        counts[_submission_status(submission)] += 1
        xp = _xp_earned(submission)
        if xp:
            approved_on = timezone.localtime(submission.time_approved).date()
            by_week[(approved_on - timedelta(days=approved_on.weekday())).isoformat()] += xp
    handed_in = [submission.time_completed for submission in submissions if submission.time_completed]
    return _compact({
        "quests_approved": counts["approved"],
        "quests_awaiting_approval": counts["awaiting approval"],
        "quests_returned": counts["returned"],
        "quests_in_progress": counts["in progress"],
        "last_handed_in_on": _day(max(handed_in, default=None)),
        "xp_approved_by_week": dict(sorted(by_week.items())),
    })


def _campaign_entries(submissions):
    """How far a student has got in each campaign they have worked in.

    Args:
        submissions (list[QuestSubmission]): the student's attempts.

    Returns:
        list[dict]: for each campaign, in the order the student first worked in it: how many of its
        quests they have had approved, how many more they have started, and the XP earned in it.
    """
    campaigns = {}
    for submission in submissions:
        campaign = submission.quest.campaign
        if campaign is None:
            continue
        entry = campaigns.setdefault(campaign.pk, {"campaign": campaign.title, "approved": set(), "started": set(), "xp": 0})
        entry["approved" if submission.is_approved else "started"].add(submission.quest_id)
        entry["xp"] += _xp_earned(submission)
    return [
        _compact({
            "campaign": entry["campaign"],
            "quests_approved": len(entry["approved"]),
            # a quest approved once and started again is counted as approved
            "quests_not_yet_approved": len(entry["started"] - entry["approved"]),
            "xp_earned": entry["xp"],
        })
        for entry in campaigns.values()
    ]


def _badge_entries(assertions, deck_ai_id, badges_with_prerequisites):
    """The badges a student has been granted, each listed once however often it was granted.

    A badge counts as granted automatically when it has prerequisites to meet and came from the
    deck's own account. The account alone does not say so: it is one of the staff's (the deck's
    first, unless the deck chose another), who may grant badges by hand as well, and a badge with
    no prerequisites is only ever granted by hand.

    Args:
        assertions (list[BadgeAssertion]): the student's badges, oldest first.
        deck_ai_id (int or None): the User pk of the deck's own account, which grants the badges
            that come from meeting their prerequisites.
        badges_with_prerequisites (set): the pks of the badges that have prerequisites.

    Returns:
        list[dict]: an entry per badge, with every day it was granted.
    """
    badges = {}
    for assertion in assertions:
        badge = assertion.badge
        automatic = assertion.issued_by_id in (None, deck_ai_id) and badge.pk in badges_with_prerequisites
        entry = badges.setdefault((badge.pk, automatic), {
            "badge": badge.name,
            "type": badge.badge_type.name,
            "description": html_to_text(badge.short_description),
            "xp_each": badge.xp,
            "granted_by": "automatic" if automatic else "teacher",
            "granted_on": [],
        })
        entry["granted_on"].append(_day(assertion.timestamp))
    return [_compact(entry) for entry in badges.values()]


def _xp_by_tag(submissions, assertions):
    """A student's XP by topic, from the tags on the quests and badges that earned it.

    Args:
        submissions (list[QuestSubmission]): the student's attempts, with their quests' tags prefetched.
        assertions (list[BadgeAssertion]): the student's badges, with their badges' tags prefetched.

    Returns:
        dict: the XP for each tag's name, most first.
    """
    totals = defaultdict(int)
    for submission in submissions:
        for tag in submission.quest.tags.all():
            totals[tag.name] += _xp_earned(submission)
    for assertion in assertions:
        if not assertion.do_not_grant_xp:
            for tag in assertion.badge.tags.all():
                totals[tag.name] += assertion.badge.xp
    return {name: xp for name, xp in sorted(totals.items(), key=lambda item: (-item[1], item[0])) if xp}


def _course_entries(profile, registrations, scrubber):
    """Where a student stands in each of their courses.

    Args:
        profile (Profile): the student's profile.
        registrations (list[CourseStudent]): their current registrations.
        scrubber (NameScrubber): replaces names in a teacher's note on an XP adjustment.

    Returns:
        list[dict]: an entry per registration, with its share of the student's XP and its mark.
    """
    entries = []
    for registration, xp in CourseStudent.objects.xp_across(profile.user, registrations, profile=profile):
        mark = registration.mark(xp=xp)
        # a registration can outlive its course (CourseStudent.course is nullable)
        courses = [registration.course] if registration.course else []
        mark_range = MarkRange.objects.get_range(mark, courses) if mark is not None else None
        entries.append(_compact({
            "course": str(registration.course) if registration.course else None,
            "group": str(registration.block) if registration.block else None,
            "semester": str(registration.semester),
            "xp": round(xp),
            "mark_percent": None if mark is None else round(mark, 1),
            "mark_range": mark_range.name if mark_range else None,
            "xp_per_class_day": round(registration.xp_per_day_ave(xp), 1),
            "xp_adjustment": registration.xp_adjustment or None,
            "xp_adjustment_reason": scrubber.scrub(registration.xp_adjust_explanation or "", profile.user_id),
        }))
    return entries


def _about(block, roster, campaign_ids):
    """What the data file says about itself and about the deck, ahead of the students.

    Args:
        block (Block): the group the file is for.
        roster (list[tuple]): the group's students (see group_roster).
        campaign_ids (set): the pks of the campaigns those students have worked in.

    Returns:
        dict: the file's purpose and how to read it, then the semester, courses, ranks, mark ranges
        and campaigns its students' records refer to.
    """
    registrations = [registration for _profile, mine in roster for registration in mine]
    semesters = {registration.semester_id: registration.semester for registration in registrations}
    courses = {registration.course_id: registration.course for registration in registrations if registration.course}

    # what each campaign offers: its published quests, leaving out archived ones
    offered = {
        row['campaign']: row for row in
        Quest.objects.filter(campaign__in=campaign_ids, published=True).values('campaign').annotate(quests=Count('pk'), xp=Sum('xp'))
    }
    return {
        "what_this_is": "A record of what each student in one group has done this semester on ByteDeck, a "
                        "learning management system where course work is done as quests. It is meant to be read "
                        "by an AI model drafting report card comments for the students' teacher to review.",
        "generated_on": timezone.localdate().isoformat(),
        "group": block.name,
        "how_to_read": HOW_TO_READ,
        "semesters": [
            {
                "semester": str(semester),
                "first_day": semester.first_day.isoformat() if semester.first_day else None,
                "last_day": semester.last_day.isoformat() if semester.last_day else None,
                "class_days_so_far": semester.days_so_far(),
                "class_days_in_all": semester.num_days(),
            }
            for semester in semesters.values()
        ],
        "courses": [
            _compact({"course": course.title, "xp_for_100_percent": course.xp_for_100_percent if course.uses_marks else None})
            for course in courses.values()
        ],
        "ranks": [{"rank": rank.name, "from_xp": rank.xp} for rank in Rank.objects.get_ranks_cached()],
        "mark_ranges": [
            {"mark_range": mark_range.name, "from_percent": mark_range.minimum_mark}
            for mark_range in MarkRange.objects.filter(active=True).order_by('minimum_mark')
        ],
        "campaigns": [
            _compact({
                "campaign": campaign.title,
                "description": campaign.short_description,
                "quests": offered.get(campaign.pk, {}).get('quests', 0),
                "xp_available": offered.get(campaign.pk, {}).get('xp', 0),
            })
            for campaign in Category.objects.filter(pk__in=campaign_ids).order_by('title')
        ],
    }


def report_card_data(block):
    """Everything the students currently in a group have done this semester, as the data file.

    A student's work is everything of theirs that belongs to an open semester, whichever of their
    courses it counted toward, since a teacher writing about one course still wants the whole
    picture and work a student never assigned to a course belongs to all of them.

    The file identifies no student (see the module docstring), and is made of nothing but
    dicts, lists, strings and numbers, so it can be written as JSON as it is.

    Args:
        block (Block): the group.

    Returns:
        dict: "about" (see _about), then "students": a record per student, in the order of the key
        file (see student_key_csv).
    """
    roster = group_roster(block)
    student_ids = [profile.user_id for profile, _registrations in roster]
    scrubber = NameScrubber(
        Profile.objects.all_in_open_semesters().values_list(
            'user_id', 'user__first_name', 'user__last_name', 'preferred_name', 'user__username',
        )
    )
    deck_ai_id = SiteConfig.get().deck_ai_id

    # Work on a quest that has since been archived or unpublished is still work the student did.
    submissions = defaultdict(list)
    drafts = set()
    in_semester = QuestSubmission.objects.get_queryset(
        exclude_archived_quests=False, exclude_quests_not_published=False,
    ).filter(
        user_id__in=student_ids, semester__status=Semester.Status.OPEN,
    ).select_related('registration__course').order_by('timestamp', 'pk')
    for submission in in_semester:
        submissions[submission.user_id].append(submission)
        if submission.draft_comment_id:
            drafts.add(submission.draft_comment_id)

    # A draft is what a student has typed but not yet handed in, so it is not part of the conversation.
    comments = defaultdict(list)
    on_submissions = Comment.objects.filter(
        target_content_type=ContentType.objects.get_for_model(QuestSubmission),
        target_object_id__in=[submission.pk for mine in submissions.values() for submission in mine],
    ).exclude(pk__in=drafts).prefetch_related(
        'document_set',
        Prefetch('question_submissions', queryset=QuestionSubmission.objects.select_related('question')),
    ).order_by('timestamp', 'pk')
    for comment in on_submissions:
        comments[comment.target_object_id].append(comment)

    assertions = defaultdict(list)
    granted = BadgeAssertion.objects.filter(
        user_id__in=student_ids, semester__status=Semester.Status.OPEN,
    ).select_related('badge__badge_type').prefetch_related('badge__tags').order_by('timestamp', 'pk')
    for assertion in granted:
        assertions[assertion.user_id].append(assertion)
    badges_with_prerequisites = set(Prereq.objects.filter(
        parent_content_type=ContentType.objects.get_for_model(Badge),
        parent_object_id__in={assertion.badge_id for mine in assertions.values() for assertion in mine},
    ).values_list('parent_object_id', flat=True))

    students = []
    campaign_ids = set()
    for profile, registrations in roster:
        mine = submissions[profile.user_id]
        campaign_ids.update(submission.quest.campaign_id for submission in mine if submission.quest.campaign_id)
        students.append(_compact({
            "student_code": student_code(profile.user_id),
            "grade": _grade(registrations, block),
            "total_xp": profile.xp_cached,
            "rank": Rank.objects.get_rank(profile.xp_cached).name,
            "courses": _course_entries(profile, registrations, scrubber),
            "work_summary": _work_summary(mine),
            "campaigns": _campaign_entries(mine),
            "xp_by_tag": _xp_by_tag(mine, assertions[profile.user_id]),
            "badges": _badge_entries(assertions[profile.user_id], deck_ai_id, badges_with_prerequisites),
            "quests": _quest_entries(mine, comments, profile.user_id, scrubber),
        }))

    return {"about": _about(block, roster, campaign_ids), "students": students}


def to_json(data):
    """A data file, or one student's part of it, as JSON text.

    It is indented, with accented letters as themselves, so a teacher can look through it before
    sharing it.

    Args:
        data (dict): the data (see report_card_data).

    Returns:
        str: the JSON.
    """
    return json.dumps(data, indent=1, ensure_ascii=False)


def student_files_zip(data):
    """A data file split into a file per student, zipped, for an AI model that cannot take a whole
    group at once, or a teacher who wants to hand it a few students at a time.

    Each file stands alone: it carries the same "about" as the whole data file, then its one
    student's record under "student".

    Args:
        data (dict): the group's data file (see report_card_data).

    Returns:
        bytes: a zip archive holding "<student code>.json" for each student.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for student in data["students"]:
            archive.writestr(f'{student["student_code"]}.json', to_json({"about": data["about"], "student": student}))
    return buffer.getvalue()
