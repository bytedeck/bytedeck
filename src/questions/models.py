from django.db import models
from django.urls import reverse

from comments.models import Comment
from quest_manager.models import Quest
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


class Question(models.Model):
    """Used for adding additional submission fields to Quests.

    This model is used for all types of questions, including short answer, long answer, file upload, and hopefully more
    in the future. Different types of questions are distinguished by the question_type field. This field is used in
    the views and forms to determine what type of question is being created, and to show/hide specific fields.

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
        null=True,
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

    # Each tuple contains the file type as both the stored value and the display value
    # e.g. ("media", "Media") or ("image", "Image")
    allowed_file_type = models.CharField(
        max_length=50,
        choices=[(key, key.capitalize()) for key in FILE_MIME_TYPES.keys()],
        default="all",
        help_text=(
            "The types of files that can be uploaded by a student for this question."
        ),
    )

    marker_notes = models.TextField(
        null=True,
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

    quest = models.ForeignKey(Quest, on_delete=models.CASCADE)
    type = models.CharField(
        max_length=20, choices=QuestionType.choices, default=QuestionType.SHORT_ANSWER
    )

    class Meta:
        ordering = ["ordinal"]
        # ensure two questions in the same quest cannot have the same ordinal
        constraints = [
            models.UniqueConstraint(fields=['quest', 'ordinal'], name='unique_ordinals'),
        ]
        unique_together = ["quest", "ordinal"]

    def __str__(self):
        """Return string representation in format of: [Question Ordinal] - [Question Type]
        e.g. "1 - short_answer" for the first question in the quest with type short_answer
        """
        return f"{self.ordinal} - {self.type}"

    @classmethod
    def next_ordinal(cls, quest):
        """Return the next ordinal value for a question in this quest"""
        last_question = Question.objects.filter(quest=quest).last()
        if last_question:
            return last_question.ordinal + 1
        else:  # no questions in this quest yet
            return 1

    def get_absolute_url(self):
        """Return the URL to the question's update view."""
        return reverse("questions:update", kwargs={"quest_id": self.quest.id, "pk": self.pk})

    def get_list_url(self):
        """Return the URL to the question's list view."""
        return reverse("questions:list", args=[self.quest.pk])


class QuestionSubmission(models.Model):
    """Used for storing a student's submission for a question.

    This model is used for all types of questions, including multiple choice, short answer, file upload, etc.
    When a student submits a quest, each Question will have a QuestionSubmission created for it.
    """

    response_text = models.TextField(
        null=True,
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

    # Similar to a quest's submission being deleted, a question's submission should not be deleted if the question is
    question = models.ForeignKey(Question, on_delete=models.SET_NULL, null=True)

    # Since we're treating the QuestionSubmission and comment both as the student's "submission", it wouldn't make sense
    # to have a QuestionSubmission without a comment. If the comment is deleted, the QuestionSubmission should be too.
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE)

    class Meta:
        ordering = ["question__ordinal"]

    def __str__(self):
        """Return string representation in format of: [Comment datetime string] - ([question ordinal])
        e.g. "2022-3-22 1:00PM - (1)" for the first question in the student's quest submission
        If the question is None, return: [Comment datetime string] - (?)
        """
        comment_time = self.comment.timestamp.strftime("%Y-%m-%d %-I:%M%p")
        if self.question:
            return f"{comment_time} - ({self.question.ordinal})"
        else:
            return f"{comment_time} - (?)"
