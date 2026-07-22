from django.db import models
from django.urls import reverse

from comments.models import Comment
from utilities.fields import FILE_MIME_TYPES
from utilities.models import RestrictedFileField


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
        help_text=(
            "The types of files that can be uploaded by a student for this question."
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

    class Meta:
        ordering = ["ordinal"]
        constraints = [
            # ensure two questions in the same quest cannot have the same ordinal
            models.UniqueConstraint(fields=["quest", "ordinal"], name="unique_ordinals"),
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

    def get_absolute_url(self):
        """Return the URL to the question's update view."""
        return reverse("questions:update", kwargs={"quest_id": self.quest_id, "pk": self.pk})

    def get_list_url(self):
        """Return the URL to the list of the quest's questions."""
        return reverse("questions:list", args=[self.quest_id])

    def allowed_mime_types(self):
        """Return the list of MIME types a student's file response may have, or the string
        sentinel "All" (understood by RestrictedFileFormField) when any type is allowed.
        """
        return FILE_MIME_TYPES[self.allowed_file_type]


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
        upload_to="quest/question/submission/%Y/%m/%d",
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

    @property
    def is_published(self):
        """Whether this answer has been published with a completion comment (vs still a draft)."""
        return self.comment_id is not None
