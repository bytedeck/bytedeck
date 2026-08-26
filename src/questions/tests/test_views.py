from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string
from django.urls import reverse

from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from quest_manager.models import Quest
from questions.models import Question

User = get_user_model()


class QuestionCRUDViewTest(ByteDeckTenantTestCase):
    """Tests for the staff-only question CRUD views (list/create/update/delete)."""

    @classmethod
    def setUpTestData(cls):
        """A teacher, a student, and a quest with short- and long-answer questions
        (the file-upload question is created per-test in setUp, since its uploaded
        file is consumed when read)."""
        cls.test_teacher = User.objects.create_user("test_teacher", password="password", is_staff=True)
        cls.test_student = User.objects.create_user("test_student", password="password")

        cls.quest = baker.make(Quest, xp=5)
        cls.other_quest = baker.make(Quest)
        cls.question1 = baker.make(
            Question, quest=cls.quest, ordinal=1, instructions="Test instructions 1",
        )
        cls.question2 = baker.make(
            Question, quest=cls.quest, ordinal=2, instructions="Test instructions 2",
        )
        cls.long_question1 = baker.make(
            Question, quest=cls.quest, ordinal=4, type="long_answer",
            instructions="Test instructions", solution_text="Test solution text",
        )

    def setUp(self):
        """Set up per-test form data and a file_upload question
        (per-test because its uploaded file is consumed when read)."""
        self.question_form_data = {
            "type": "short_answer",
            "instructions": "Test instructions",
            "solution_text": "Test solution text",
            "required": True,
        }
        self.file_upload = SimpleUploadedFile("file.mp4", b"file_content", content_type="video/mp4")
        self.file_question1 = baker.make(
            Question, quest=self.quest, ordinal=5, type="file_upload",
            instructions="Test instructions", solution_file=self.file_upload,
        )
        self.question_form_file_data = {
            "type": "file_upload",
            "instructions": "Test instructions",
            "required": True,
            "solution_file": SimpleUploadedFile("file2.mp4", b"file_content", content_type="video/mp4"),
            "allowed_file_type": "video",
        }

    def assertNoFormErrors(self, response):
        """Fail with the form's errors if the response re-rendered the form instead of redirecting."""
        if response.context and "form" in response.context:
            self.fail(f"Form errors: {response.context['form'].errors}")
        self.assertEqual(response.status_code, 302)

    def test_all_question_page_status_codes__anonymous(self):
        """If not logged in then all question views should redirect to the login page."""
        self.assertRedirectsLogin("questions:list", kwargs={"quest_id": self.quest.id})
        self.assertRedirectsLogin(
            "questions:create", kwargs={"quest_id": self.quest.id, "question_type": "short_answer"})
        self.assertRedirectsLogin(
            "questions:update", kwargs={"quest_id": self.quest.id, "pk": self.question1.id})
        self.assertRedirectsLogin(
            "questions:delete", kwargs={"quest_id": self.quest.id, "pk": self.question1.id})

    def test_all_question_page_status_codes__student(self):
        """Students get a 403 from every question view: question CRUD is staff-only."""
        self.client.force_login(self.test_student)
        self.assert403("questions:list", kwargs={"quest_id": self.quest.id})
        self.assert403(
            "questions:create", kwargs={"quest_id": self.quest.id, "question_type": "short_answer"})
        self.assert403(
            "questions:update", kwargs={"quest_id": self.quest.id, "pk": self.question1.id})
        self.assert403(
            "questions:delete", kwargs={"quest_id": self.quest.id, "pk": self.question1.id})

    def test_list__teacher_sees_questions(self):
        """Teachers can view a quest's question list, which displays each question's
        (truncated) instructions."""
        self.client.force_login(self.test_teacher)
        response = self.assert200("questions:list", kwargs={"quest_id": self.quest.id})
        self.assertTemplateUsed(response, "questions/question_list.html")
        # NOTE: instructions are truncated at 20 characters in the table, so these
        # fixture instructions must be shorter than that to assert on them
        self.assertContains(response, self.question1.instructions)
        self.assertContains(response, self.question2.instructions)

    def test_list__help_text_uses_no_em_dashes(self):
        """The page's copy keeps to the project's punctuation (#2357).

        Em dashes are ruled out in anything users read, so the help text explaining what
        questions do uses a colon and a comma where it needs a break in a sentence.
        """
        self.client.force_login(self.test_teacher)

        response = self.assert200("questions:list", kwargs={"quest_id": self.quest.id})

        self.assertNotContains(response, "—")
        self.assertNotContains(response, "&mdash;")

    def test_list__help_text_says_files_save_with_the_draft(self):
        """The page's copy matches how draft saving works (#2551).

        Files save with the student's draft (#1459), so the sentence explaining answers to
        teachers must not claim a file waits for the submit: a teacher reading that would
        tell students their files are not safe until they submit.
        """
        self.client.force_login(self.test_teacher)

        response = self.assert200("questions:list", kwargs={"quest_id": self.quest.id})

        self.assertContains(response, "any chosen files too")
        self.assertNotContains(response, "upload when the quest is submitted")

    def test_list__an_image_solution_shows_as_a_thumbnail(self):
        """A picture used as a solution is shown in the table, not just named (#2172).

        The Solution column is narrow, so the thumbnail stands in for the download link
        rather than sitting beside it.
        """
        image_question = baker.make(
            Question, quest=self.quest, ordinal=7, type="file_upload",
            instructions="Upload a photo", solution_file=SimpleUploadedFile("example.png", b"pretend image"),
        )
        self.client.force_login(self.test_teacher)

        response = self.assert200("questions:list", kwargs={"quest_id": self.quest.id})

        self.assertContains(response, '<img class="question-media-thumb"')
        self.assertContains(response, image_question.solution_file.url)

    def test_list__a_video_solution_stays_a_link(self):
        """A video solution is named rather than embedded: a player has no room in the column."""
        self.client.force_login(self.test_teacher)

        response = self.assert200("questions:list", kwargs={"quest_id": self.quest.id})

        # the setUp file question's solution is an .mp4
        self.assertNotContains(response, "<video")
        self.assertContains(response, self.file_question1.solution_file.url)

    def test_list__invalid_quest_404(self):
        """The question list for a nonexistent quest is a 404."""
        self.client.force_login(self.test_teacher)
        self.assert404("questions:list", kwargs={"quest_id": 99999999})

    def test_create__teacher_get(self):
        """Teachers can open the create form for a supported question type."""
        self.client.force_login(self.test_teacher)
        self.assert200(
            "questions:create", kwargs={"quest_id": self.quest.id, "question_type": "short_answer"})

    def test_create__invalid_type_404(self):
        """Creating a question with an unsupported type in the URL is a 404 (not a crash)."""
        self.client.force_login(self.test_teacher)
        self.assert404(
            "questions:create",
            kwargs={"quest_id": self.quest.id, "question_type": "invalid_question_type"})

    def test_create__student_denied_nothing_created(self):
        """A student POSTing to the create view gets a 403 and no question is created."""
        self.client.force_login(self.test_student)
        question_count_before = Question.objects.count()
        response = self.client.post(
            reverse("questions:create",
                    kwargs={"quest_id": self.quest.id, "question_type": "short_answer"}),
            data=self.question_form_data,
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Question.objects.count(), question_count_before)

    def test_create__teacher_short_answer(self):
        """A teacher can create a short answer question; it lands on the quest at the next
        ordinal and redirects back to the question list."""
        self.client.force_login(self.test_teacher)
        question_count_before = Question.objects.count()
        response = self.client.post(
            reverse("questions:create",
                    kwargs={"quest_id": self.quest.id, "question_type": "short_answer"}),
            data=self.question_form_data,
        )
        self.assertNoFormErrors(response)
        self.assertRedirects(response, reverse("questions:list", kwargs={"quest_id": self.quest.id}))
        self.assertEqual(Question.objects.count(), question_count_before + 1)
        new_question = Question.objects.filter(quest=self.quest).order_by("ordinal").last()
        self.assertEqual(new_question.instructions, "Test instructions")
        self.assertEqual(new_question.ordinal, 6)  # next_ordinal: after the setUp file question's ordinal 5

    def test_create__teacher_file_upload(self):
        """A teacher can create a file upload question, including its solution file."""
        self.client.force_login(self.test_teacher)
        question_count_before = Question.objects.count()
        response = self.client.post(
            reverse("questions:create",
                    kwargs={"quest_id": self.quest.id, "question_type": "file_upload"}),
            data=self.question_form_file_data,
        )
        self.assertNoFormErrors(response)
        self.assertEqual(Question.objects.count(), question_count_before + 1)
        new_question = Question.objects.filter(quest=self.quest, type="file_upload").order_by("ordinal").last()
        self.assertEqual(new_question.allowed_file_type, "video")
        self.assertEqual(new_question.solution_file.read(), b"file_content")

    def test_update__teacher_get_short_answer(self):
        """The update form shows the question's existing content."""
        self.client.force_login(self.test_teacher)
        response = self.client.get(
            reverse("questions:update",
                    kwargs={"quest_id": self.quest.id, "pk": self.question2.id}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.question2.instructions)

    def test_update__teacher_get_long_answer(self):
        """The update form for a long answer question shows its instructions and solution text."""
        self.client.force_login(self.test_teacher)
        response = self.client.get(
            reverse("questions:update",
                    kwargs={"quest_id": self.quest.id, "pk": self.long_question1.id}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.long_question1.instructions)
        self.assertContains(response, self.long_question1.solution_text)

    def test_update__teacher_get_file_upload(self):
        """The update form for a file upload question shows its instructions and keeps the
        existing solution file."""
        self.client.force_login(self.test_teacher)
        response = self.client.get(
            reverse("questions:update",
                    kwargs={"quest_id": self.quest.id, "pk": self.file_question1.id}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.file_question1.instructions)
        self.assertEqual(response.context["question"].solution_file.read(), b"file_content")

    def test_update__teacher_post(self):
        """A teacher can update a question; the changes persist."""
        self.client.force_login(self.test_teacher)
        self.question_form_data["instructions"] = "Updated instructions"
        response = self.client.post(
            reverse("questions:update",
                    kwargs={"quest_id": self.quest.id, "pk": self.question1.id}),
            data=self.question_form_data,
        )
        self.assertNoFormErrors(response)
        self.question1.refresh_from_db()
        self.assertEqual(self.question1.instructions, "Updated instructions")

    def test_update__wrong_quest_404(self):
        """A question can't be addressed through another quest's URL: the update view 404s
        when the quest_id doesn't match the question's quest."""
        self.client.force_login(self.test_teacher)
        self.assert404(
            "questions:update",
            kwargs={"quest_id": self.other_quest.id, "pk": self.question1.id})

    def test_delete__teacher_get_confirmation(self):
        """The delete view shows a confirmation page."""
        self.client.force_login(self.test_teacher)
        self.assert200(
            "questions:delete", kwargs={"quest_id": self.quest.id, "pk": self.question1.id})

    def test_delete__teacher_post(self):
        """A teacher can delete a question; only that question is removed, and the view
        redirects back to the question list."""
        self.client.force_login(self.test_teacher)
        previous_question_count = Question.objects.count()
        response = self.client.post(
            reverse("questions:delete",
                    kwargs={"quest_id": self.quest.id, "pk": self.question1.id}))
        self.assertRedirects(response, reverse("questions:list", kwargs={"quest_id": self.quest.id}))
        self.assertFalse(Question.objects.filter(id=self.question1.id).exists())
        self.assertTrue(Question.objects.filter(id=self.question2.id).exists())
        self.assertEqual(Question.objects.count(), previous_question_count - 1)

    def test_delete__wrong_quest_404(self):
        """A question can't be deleted through another quest's URL."""
        self.client.force_login(self.test_teacher)
        self.assert404(
            "questions:delete",
            kwargs={"quest_id": self.other_quest.id, "pk": self.question1.id})
        self.assertTrue(Question.objects.filter(id=self.question1.id).exists())


class QuestionTableMoveArrowsTest(ByteDeckTenantTestCase):
    """The move arrows render only where the page can act on them (#2568).

    The snippet's arrows post to `questions:move`, whose non-AJAX path redirects to the
    question list. Only the question list binds the handler that posts them in the background
    instead, so anywhere else a click would silently relocate the reader: off a quest they were
    reading, off a submission they were marking, or out of a Library export they were partway
    through.
    """

    @classmethod
    def setUpTestData(cls):
        """A teacher and a quest with two questions, so the table has rows to act on."""
        cls.test_teacher = User.objects.create_user("test_teacher", password="password", is_staff=True)
        cls.quest = baker.make(Quest, name="Reorderable Quest")
        cls.q1 = baker.make(Question, quest=cls.quest, ordinal=1, instructions="First question")
        cls.q2 = baker.make(Question, quest=cls.quest, ordinal=2, instructions="Second question")

    def _render_snippet(self, **extra):
        """Render the question table snippet directly, with `extra` merged into its context."""
        return render_to_string(
            "questions/snippets/question_table.html",
            {"quest": self.quest, "questions": Question.objects.filter(quest=self.quest), **extra},
        )

    def test_question_table__withholds_the_move_arrows_by_default(self):
        """A template that includes this snippet gets no arrows unless it asks for them.

        The default is off so a page cannot inherit buttons whose handler it does not have,
        which is how they came to be on three pages that strand the reader.
        """
        table = self._render_snippet()

        self.assertNotIn("question-move-form", table)

    def test_question_table__keeps_edit_and_delete_without_the_arrows(self):
        """Only the arrows are withheld: Edit and Delete are plain links to other pages.

        Leaving the page is what a link promises, so those stay wherever the table renders
        with actions at all.
        """
        table = self._render_snippet()

        self.assertIn('title="Edit"', table)
        self.assertIn('title="Delete"', table)

    def test_question_table__renders_the_move_arrows_when_asked(self):
        """A caller that binds the handler gets the arrows by passing the flag."""
        table = self._render_snippet(can_reorder_questions=True)

        self.assertIn("question-move-form", table)
        self.assertIn('title="Move up"', table)
        self.assertIn('title="Move down"', table)

    def test_QuestionList__renders_the_move_arrows(self):
        """The question list is the page built to reorder from, so it shows them."""
        self.client.force_login(self.test_teacher)

        response = self.client.get(reverse("questions:list", kwargs={"quest_id": self.quest.id}))

        self.assertContains(response, "question-move-form")

    def test_quest_detail__shows_the_questions_without_the_move_arrows(self):
        """A teacher reading a quest sees its questions but cannot reorder from there.

        Asserting the panel is present matters as much as the arrows being absent: without it
        this passes for the wrong reason on any page that renders no question table at all.
        The panel's own Manage Questions button is the way to the page that can reorder.
        """
        self.client.force_login(self.test_teacher)

        response = self.client.get(reverse("quests:quest_detail", args=[self.quest.id]))

        self.assertContains(response, "Submission Questions")
        self.assertContains(response, "First question")
        self.assertContains(response, "Manage Questions")
        self.assertNotContains(response, "question-move-form")


class QuestionMoveViewTest(ByteDeckTenantTestCase):
    """Tests for QuestionMoveView: staff-only up/down reordering of a quest's questions."""

    @classmethod
    def setUpTestData(cls):
        """A teacher, a student, and a quest with three questions at ordinals 1, 2, 3
        (and a second quest to test cross-quest URL rejection)."""
        cls.test_teacher = User.objects.create_user("test_teacher", password="password", is_staff=True)
        cls.test_student = User.objects.create_user("test_student", password="password")

        cls.quest = baker.make(Quest)
        cls.other_quest = baker.make(Quest)
        cls.q1 = baker.make(Question, quest=cls.quest, ordinal=1, instructions="Q1")
        cls.q2 = baker.make(Question, quest=cls.quest, ordinal=2, instructions="Q2")
        cls.q3 = baker.make(Question, quest=cls.quest, ordinal=3, instructions="Q3")

    def _move(self, question, direction, quest=None):
        """POST to move `question` in `direction`, scoped to `quest` (defaults to its own quest)."""
        quest = quest or self.quest
        return self.client.post(reverse(
            "questions:move", kwargs={"quest_id": quest.id, "pk": question.id, "direction": direction}))

    def _ordinals(self):
        """Return {instructions: ordinal} for the quest's questions, read fresh from the DB."""
        return {q.instructions: q.ordinal for q in Question.objects.filter(quest=self.quest)}

    def test_move__anonymous_redirected_to_login(self):
        """Anonymous users are redirected to login and can't reorder questions."""
        self.assertRedirectsLogin(
            "questions:move", kwargs={"quest_id": self.quest.id, "pk": self.q2.id, "direction": "up"})

    def test_move__student_denied(self):
        """A student gets a 403 and the ordering is unchanged: reordering is staff-only."""
        self.client.force_login(self.test_student)
        response = self._move(self.q2, "up")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self._ordinals(), {"Q1": 1, "Q2": 2, "Q3": 3})

    def test_move__down_swaps_with_next(self):
        """Moving a question down swaps its ordinal with the next question's, and redirects
        back to the question list."""
        self.client.force_login(self.test_teacher)
        response = self._move(self.q1, "down")
        self.assertRedirects(response, reverse("questions:list", kwargs={"quest_id": self.quest.id}))
        self.assertEqual(self._ordinals(), {"Q1": 2, "Q2": 1, "Q3": 3})

    def test_move__up_swaps_with_previous(self):
        """Moving a question up swaps its ordinal with the previous question's."""
        self.client.force_login(self.test_teacher)
        self._move(self.q3, "up")
        self.assertEqual(self._ordinals(), {"Q1": 1, "Q2": 3, "Q3": 2})

    def test_move__up_at_top_is_noop(self):
        """Moving the first question up does nothing (there is no neighbour above it)."""
        self.client.force_login(self.test_teacher)
        response = self._move(self.q1, "up")
        self.assertRedirects(response, reverse("questions:list", kwargs={"quest_id": self.quest.id}))
        self.assertEqual(self._ordinals(), {"Q1": 1, "Q2": 2, "Q3": 3})

    def test_move__down_at_bottom_is_noop(self):
        """Moving the last question down does nothing (there is no neighbour below it)."""
        self.client.force_login(self.test_teacher)
        self._move(self.q3, "down")
        self.assertEqual(self._ordinals(), {"Q1": 1, "Q2": 2, "Q3": 3})

    def test_move__follows_display_order_across_ordinal_gaps(self):
        """Reordering follows display order, not ordinal arithmetic: a question moves past its
        nearest neighbour even when ordinals are non-contiguous (e.g. after deletions)."""
        self.client.force_login(self.test_teacher)
        # open gaps so ordinals are 1, 5, 9 (as could happen after deleting questions)
        Question.objects.filter(pk=self.q2.pk).update(ordinal=5)
        Question.objects.filter(pk=self.q3.pk).update(ordinal=9)
        # moving Q3 (last, ordinal 9) up swaps it with its nearest neighbour Q2 (ordinal 5)
        self._move(self.q3, "up")
        self.assertEqual(self._ordinals(), {"Q1": 1, "Q2": 9, "Q3": 5})
        # the resulting display order is Q1, Q3, Q2
        ordered = list(Question.objects.filter(quest=self.quest).values_list("instructions", flat=True))
        self.assertEqual(ordered, ["Q1", "Q3", "Q2"])

    def test_move__invalid_direction_404(self):
        """A direction other than up/down in the URL is a 404, and nothing is reordered."""
        self.client.force_login(self.test_teacher)
        response = self.client.post(reverse(
            "questions:move", kwargs={"quest_id": self.quest.id, "pk": self.q1.id, "direction": "sideways"}))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self._ordinals(), {"Q1": 1, "Q2": 2, "Q3": 3})

    def test_move__wrong_quest_404(self):
        """A question can't be moved through another quest's URL; the ordering is unchanged."""
        self.client.force_login(self.test_teacher)
        response = self._move(self.q1, "down", quest=self.other_quest)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self._ordinals(), {"Q1": 1, "Q2": 2, "Q3": 3})

    def test_move__get_not_allowed(self):
        """The move endpoint is POST-only; a GET returns 405 Method Not Allowed."""
        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse(
            "questions:move", kwargs={"quest_id": self.quest.id, "pk": self.q1.id, "direction": "up"}))
        self.assertEqual(response.status_code, 405)

    def _move_by_ajax(self, question, direction):
        """POST a move the way the question list's JavaScript does.

        Args:
            question (Question): the question to move.
            direction (str): 'up' or 'down'.

        Returns:
            HttpResponse: the view's response to an XHR.
        """
        return self.client.post(
            reverse("questions:move", kwargs={"quest_id": self.quest.id, "pk": question.id, "direction": direction}),
            headers={"x-requested-with": "XMLHttpRequest"},
        )

    def test_move__ajax_returns_the_table_in_the_new_order(self):
        """A background move answers with the re-rendered table, in the order it just set (#2216).

        The page swaps that HTML into the list, which is what keeps the teacher's place on a
        long list of questions.
        """
        self.client.force_login(self.test_teacher)

        response = self._move_by_ajax(self.q1, "down")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._ordinals(), {"Q1": 2, "Q2": 1, "Q3": 3})
        table = response.json()["question_table_html"]
        self.assertLess(table.index("Q2"), table.index("Q1"), "the table came back in the old order")

    def test_move__ajax_table_still_carries_the_move_arrows(self):
        """The table a move hands back can itself be moved from, so a reorder can continue.

        This HTML replaces the one the teacher just clicked in, and reordering takes several
        clicks. The snippet withholds the arrows unless the caller asks for them (#2568), so
        the view has to ask: without that a move would work once and return a table with
        nothing left to click.
        """
        self.client.force_login(self.test_teacher)

        response = self._move_by_ajax(self.q1, "down")

        table = response.json()["question_table_html"]
        self.assertIn("question-move-form", table)
        self.assertIn("Move up", table)
        self.assertIn("Move down", table)

    def test_move__ajax_table_disables_the_arrows_at_the_ends_of_the_list(self):
        """The re-rendered table decides which arrows are dead, so the page never has to.

        A question moved to the top can go no further, and the returned HTML says so: it is
        the same template the page was built from, rendered by the same server.
        """
        self.client.force_login(self.test_teacher)

        table = self._move_by_ajax(self.q2, "up").json()["question_table_html"]

        up_at_top = reverse(
            "questions:move", kwargs={"quest_id": self.quest.id, "pk": self.q2.id, "direction": "up"})
        # the form of the question now at the top, up to its button's disabled attribute
        form_start = table.index(up_at_top)
        self.assertIn("disabled", table[form_start:table.index("</form>", form_start)])

    def test_move__ajax_at_the_end_of_the_list_still_returns_the_table(self):
        """A move with nowhere to go answers with the list as it stands.

        The arrows at the ends are disabled, so this happens when a stale page is clicked
        after someone else reordered the quest: the reply shows that person's order.
        """
        self.client.force_login(self.test_teacher)

        response = self._move_by_ajax(self.q1, "up")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._ordinals(), {"Q1": 1, "Q2": 2, "Q3": 3})
        self.assertIn("Q1", response.json()["question_table_html"])

    def test_move__a_plain_post_redirects_to_the_list(self):
        """A form post that is not an XHR redirects to the question list.

        That is the path a browser running no JavaScript takes, so reordering works there
        too: each click reloads the list in its new order.
        """
        self.client.force_login(self.test_teacher)

        response = self._move(self.q1, "down")

        self.assertRedirects(response, reverse("questions:list", kwargs={"quest_id": self.quest.id}))
