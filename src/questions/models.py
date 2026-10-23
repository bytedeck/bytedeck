import os
import uuid

from django.db import models
from django.utils.functional import cached_property
from django.urls import reverse

from comments.models import Comment
from utilities.fields import (
    ALL_SCRIPT_CAPABLE_TYPES,
    FILE_MIME_TYPES,
    NO_SCRIPT_CAPABLE_TYPES,
    SVG_SCRIPT_CAPABLE_TYPES,
    UNSAFE_UPLOAD_EXTENSIONS,
)
from utilities.models import RestrictedFileField
from utilities.uploads import UploadToOwnFolder


class QuestionType(models.TextChoices):
    """Identifies what types of questions can be created.

    This is used in the views and forms to determine what type of question is being created, and to show/hide specific
    fields. For example, with a short answer question, the solution_file field is hidden, but with a file upload question,
    the solution_file field is shown.
    """

    SHORT_ANSWER = "short_answer"
    LONG_ANSWER = "long_answer"
    FILE_UPLOAD = "file_upload"


# Choices for Question.allowed_file_type. Keys must exist in FILE_MIME_TYPES
# (utilities.fields); they are declared explicitly here (rather than derived from
# the dict) so that editing FILE_MIME_TYPES can never change this model's choices
# behind a migration's back and trip CI's `makemigrations --check`.
ALLOWED_FILE_TYPE_CHOICES = [
    ("image", "Image"),
    ("video", "Video"),
    ("audio", "Audio"),
    ("media", "Image or Video"),
    ("all", "All"),
]

# What ticking `allow_script_capable_files` adds, per allowed_file_type. SVG is an image, so
# that is what the two image settings gain; "all" gains the whole set, which is what a web
# design quest asks for. Video and audio have no script-capable member, so the tick adds
# nothing there and those settings are deliberately absent (#2559).
SCRIPT_CAPABLE_TYPES_BY_FILE_TYPE = {
    "image": SVG_SCRIPT_CAPABLE_TYPES,
    "media": SVG_SCRIPT_CAPABLE_TYPES,
    "all": ALL_SCRIPT_CAPABLE_TYPES,
}


def is_script_capable_file(file):
    """Whether a stored file is one a browser would run a script from, judged by its name.

    Args:
        file: a file field's value (a ``FieldFile``), or None/empty when there is no file.

    Returns:
        bool: True for a stored HTML, SVG, XML or MHTML file; False for anything else,
        including no file at all.
    """
    if not file:
        return False
    return os.path.splitext(file.name.lower())[1] in UNSAFE_UPLOAD_EXTENSIONS


class Question(models.Model):
    """A single additional submission field a teacher attaches to a Quest.

    This model is used for all types of questions, including short answer, long answer and file upload (and hopefully
    more in the future). Different types of questions are distinguished by the ``type`` field, which the views and
    forms use to determine what type of question is being created and to show/hide specific fields.

    For example, with a short_answer question, the solution_file/response_file fields are hidden and the solution_text/
    response_text fields are shown, but with a file_upload question, the solution_file/response_file fields are shown etc.

    For file_upload questions, teachers can specify what type of file is expected. For example, if they specify "video",
    the student will only be able to upload a video file. This is enforced in the form validation, allowing only specific
    MIME types. The allowed MIME types are specified in the FILE_MIME_TYPES dictionary.
    """

    instructions = models.TextField(
        help_text=(
            "Appears to the student when they are completing the quest. Should provide "
            "specific guidance, a prompt, or a problem statement for the student to address."
        )
    )
    solution_text = models.TextField(
        blank=True,
        help_text=(
            "This text will appear to the marker, allowing for an easy comparison of "
            "the student's submission to an ideal or example solution."
        ),
    )
    solution_file = RestrictedFileField(
        blank=True,
        null=True,
        upload_to="quest/question/solution/%Y/%m/%d",
        help_text=(
            "This file will appear to the marker, allowing them to easily compare "
            "the student's submission to an ideal or example solution for file-based questions."
        ),
    )
    allowed_file_type = models.CharField(
        max_length=50,
        choices=ALLOWED_FILE_TYPE_CHOICES,
        default="all",
        help_text="The types of files that can be uploaded by a student for this question.",
    )
    allow_script_capable_files = models.BooleanField(
        default=False,
        verbose_name="Also allow file types that can carry a script",
        help_text=(
            "Tick this only for a quest that asks for one: with <b>Image</b> or "
            "<b>Image or Video</b> it also accepts SVG, and with <b>All</b> it also accepts "
            "SVG, HTML, XML and similar. A browser can run a script from these, so such an "
            "answer is handed to you as a download rather than opened in ByteDeck. An SVG is "
            "shown as a picture as well, which browsers never run script in. Leave it "
            "unticked with <b>Video</b> or <b>Audio</b>: neither has such a file type."
        ),
    )
    marker_notes = models.TextField(
        blank=True,
        help_text=(
            "This text will appear to the marker, providing additional "
            "context and info, if needed."
        ),
    )
    required = models.BooleanField(
        default=True,
        help_text=(
            "If this field is unchecked, the student can complete the quest without "
            "answering this question."
        ),
    )
    datetime_created = models.DateTimeField(auto_now_add=True)
    datetime_last_edit = models.DateTimeField(auto_now=True)
    ordinal = models.PositiveIntegerField(
        default=1,
        help_text=(
            "Questions will be displayed to the student in order from lowest ordinal to "
            "highest ordinal."
        ),
    )

    quest = models.ForeignKey('quest_manager.Quest', on_delete=models.CASCADE)
    type = models.CharField(
        max_length=20, choices=QuestionType.choices, default=QuestionType.SHORT_ANSWER
    )
    import_id = models.UUIDField(
        default=uuid.uuid4,
        help_text=(
            "Identifies this question within its quest wherever the quest is shared, so "
            "re-importing the quest updates this question rather than a different one. "
            "Only change this if you want to disconnect it from the shared version."
        ),
    )

    class Meta:
        ordering = ["ordinal"]
        constraints = [
            # ensure two questions in the same quest cannot have the same ordinal
            models.UniqueConstraint(fields=["quest", "ordinal"], name="unique_ordinals"),
            # A question's import_id identifies it within its quest, not across the whole
            # deck: two copies of a quest are two quests, and their questions legitimately
            # share the identity they were copied from.
            models.UniqueConstraint(fields=["quest", "import_id"], name="unique_question_import_ids"),
        ]

    def __str__(self):
        """Return string representation in format of: [Question Ordinal] - [Question Type]
        e.g. "1 - short_answer" for the first question in the quest with type short_answer
        """
        return f"{self.ordinal} - {self.type}"

    @classmethod
    def next_ordinal(cls, quest):
        """Return the next ordinal value for a question in this quest."""
        highest = cls.objects.filter(quest=quest).aggregate(models.Max("ordinal"))["ordinal__max"]
        return (highest or 0) + 1

    @cached_property
    def number(self):
        """This question's 1-based place among its quest's questions, by ordinal.

        The submission page and the marking table both number questions this way, so a student
        answering only some of them again after a return still sees each under the number it
        had the first time (#2933).
        """
        return Question.objects.filter(quest_id=self.quest_id, ordinal__lt=self.ordinal).count() + 1

    def get_absolute_url(self):
        """Return the URL to the question's update view."""
        return reverse("questions:update", kwargs={"quest_id": self.quest_id, "pk": self.pk})

    def get_list_url(self):
        """Return the URL to the list of the quest's questions."""
        return reverse("questions:list", args=[self.quest_id])

    def allowed_mime_types(self):
        """Return the list of MIME types a student's file response may have, or the string
        sentinel "All" (understood by RestrictedFileFormField) when any type is allowed.

        The script-capable types this question opted into are part of the list, because
        ``validate_file`` checks its allow-list separately from the script-capable rule: a
        question that accepts SVG has to say so in both or the SVG is refused by the other one.
        """
        mime_types = FILE_MIME_TYPES[self.allowed_file_type]

        if mime_types == "All":
            return mime_types

        return mime_types + sorted(self.script_capable_types().mime_types)

    def script_capable_types(self):
        """Return the script-capable files this question accepts, as a ``ScriptCapableTypes``.

        Script-capable files (SVG, HTML, XML, MHTML) are refused from every upload, because a
        browser opening one from the app's own origin runs whatever script it carries in the
        viewer's session, usually the marker's (#2559). A teacher lifts that here, per question
        and only as far as the chosen file type reaches: an Image question that opted in takes
        an SVG and still refuses an HTML page.

        Returns:
            ScriptCapableTypes: the extensions and declared types to accept anyway, empty
            unless the teacher ticked the opt-in on a file type that has such a member.
        """
        if not self.allow_script_capable_files:
            return NO_SCRIPT_CAPABLE_TYPES

        return SCRIPT_CAPABLE_TYPES_BY_FILE_TYPE.get(self.allowed_file_type, NO_SCRIPT_CAPABLE_TYPES)

    @property
    def solution_file_is_script_capable(self):
        """Whether this question's solution file is one a browser would run a script from.

        A solution file can be of any type, so a teacher can show the marker an example in the
        format the students answer in (#2924). Such a file is handed over as a download, never
        linked at its storage URL, for the reason an answer's is (#2559). A quest imported from
        the Shared Library brings its solution file with it, so the teacher who uploaded it
        need not be on this deck at all.

        Returns:
            bool: True for a stored HTML, SVG, XML or MHTML file; False for anything else,
            including a question with no solution file.
        """
        return is_script_capable_file(self.solution_file)


class QuestionSubmission(models.Model):
    """A student's answer to a single Question, as part of one quest submission cycle.

    Answers are owned by the student's QuestSubmission (the submission is their lifecycle anchor:
    dropping/deleting the submission removes its answers). While the student is still drafting,
    ``comment`` is NULL; when the answers are published together with the student's completion
    comment, ``comment`` is set to that comment. A returned-and-resubmitted quest gets a fresh
    set of QuestionSubmissions for the new cycle, so each published comment keeps the answers
    that were submitted with it.
    """

    response_text = models.TextField(
        blank=True,
        help_text=(
            "A text response to a question. This is what the teacher will "
            "look at when marking the question."
        ),
    )
    response_file = RestrictedFileField(
        blank=True,
        null=True,
        upload_to=UploadToOwnFolder("quest/question/submission/%Y/%m/%d"),
        # the dated folder and a folder of its own come before the name; see Document.docfile
        max_length=255,
        help_text=(
            "A file response to a question. This is what the teacher will "
            "look at when marking the question."
        ),
    )

    # The answer's owner and lifecycle anchor: delete the quest submission, delete its answers.
    quest_submission = models.ForeignKey(
        'quest_manager.QuestSubmission', on_delete=models.CASCADE, related_name="question_submissions"
    )

    # Similar to a quest's submission not being deleted when its quest is, a question's answers
    # should survive the question being deleted (the marker may still want to see them);
    # consumers must therefore handle question=None gracefully.
    question = models.ForeignKey(Question, on_delete=models.SET_NULL, null=True, blank=True)

    # NULL while the answer is a draft; set to the student's completion comment when published.
    # If the comment is later deleted the answers revert to unpublished rather than disappearing.
    comment = models.ForeignKey(
        Comment, on_delete=models.SET_NULL, null=True, blank=True, related_name="question_submissions"
    )

    # The marker's verdict on this answer (#2933). `marked_wrong` is what the X beside the answer
    # in the marking table toggles while the submission waits for review: seen only by staff, and
    # changeable until the teacher returns or approves the quest. That sets `is_correct` from it
    # (questions.utils.finalize_answer_marks), and `is_correct` is what everyone is shown: a check
    # or an X. It stays NULL for an answer that was never judged this way, such as one published
    # before marking existed, which shows neither.
    #
    # db_default as well as default: during a deploy the outgoing version still inserts answers
    # without this column, so the database has to fill it in (CONTRIBUTING.md, "Migrations and
    # the deploy window").
    marked_wrong = models.BooleanField(
        default=False,
        db_default=False,
        help_text="Marked wrong by a teacher reviewing the submission. Seen only by staff until the quest is returned or approved.",
    )
    is_correct = models.BooleanField(
        null=True,
        blank=True,
        help_text="Set when the quest is returned or approved: whether the answer was right. Empty for an answer never marked.",
    )

    datetime_created = models.DateTimeField(auto_now_add=True)
    datetime_last_edit = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["question__ordinal"]

    def __str__(self):
        """Return string representation in format of: [creation datetime] - ([question ordinal])
        e.g. "2022-03-22 1:00PM - (1)" for the first question in the student's quest submission.
        If the question has been deleted, return: [creation datetime] - (?)
        """
        created = self.datetime_created.strftime("%Y-%m-%d %-I:%M%p")
        if self.question:
            return f"{created} - ({self.question.ordinal})"
        else:
            return f"{created} - (?)"

    @cached_property
    def awaiting_mark(self):
        """Whether a teacher can still mark this answer right or wrong (#2933).

        Only the answers handed in with the submission's latest completion, while the submission
        waits for review: completed and not yet approved, and not already marked. Once the quest
        is returned or approved the marks are set and shown, and an earlier hand-in's answers were
        judged when that one came back.

        Returns:
            bool: True for an unmarked answer from the latest hand-in of a submission awaiting
            review.
        """
        submission = self.quest_submission
        if self.is_correct is not None or self.comment_id is None:
            return False
        if not submission.is_completed or submission.is_approved:
            return False
        latest = QuestionSubmission.objects.filter(
            quest_submission_id=self.quest_submission_id, comment__isnull=False,
        ).aggregate(models.Max("comment_id"))["comment_id__max"]
        return self.comment_id == latest

    @property
    def is_published(self):
        """Whether this answer has been published with a completion comment (vs still a draft)."""
        return self.comment_id is not None

    @property
    def response_file_is_script_capable(self):
        """Whether this answer's file is one a browser would run a script from (#2559).

        Answered from the stored file rather than from the question, deliberately. A question
        can be deleted (``question`` is ``SET_NULL``), or have its opt-in unticked, long after
        the answer was published, and neither changes the file sitting on the row. Asking the
        question instead would quietly start linking a stored HTML answer at its storage URL
        again, which is the whole vulnerability.

        Returns:
            bool: True for a stored HTML, SVG, XML or MHTML file; False for anything else,
            including an answer with no file.
        """
        return is_script_capable_file(self.response_file)
