# Submission questions

**Submission questions** let a quest ask for exactly the answers you want, instead of hoping a student's comment covers them. Each question you add becomes its own answer field on the quest's submission form: a one-line text box, a rich-text editor, or a file upload. Students see them in your order, above the usual comment box.

Questions are set up by teachers; students only meet them while completing a quest. Solutions and marker notes are for the person marking, and students never see them.

## How questions fit into a quest

Without questions, a student submits a quest by writing one comment, with files attached if they like. Questions don't replace that: the comment box and its attachments stay. Questions add structure above it, and when the student submits, each answer comes back beside the question it answers, with your solution right there to compare.

A question is one of three types:

Short Answer
:   A single line of text, up to 200 characters. Good for a definition, a link, or one precise fact.

Long Answer
:   A full rich-text response in the same editor as the comment box, so formatting, images and links all work.

File Upload
:   One file, of a kind you choose: **Image**, **Video**, **Audio**, **Image or Video**, or **All**. A file can be up to 16 MB.

Each question is either **required** (the quest can't be submitted until it's answered) or optional (marked *(optional)* on the form, and can be left blank).

## Add questions to a quest

**Manage Questions** is in two places: in the row of buttons at the top of the quest's edit form,

![The top of the Update Quest form: Cancel, Update, Edit Prerequisites and Manage Questions](../images/submission-questions/quest-form-button.png)

and on the **Submission Questions** panel of the quest's own page:

![The Submission Questions panel heading on a quest's page, with a Manage Questions button](../images/submission-questions/quest-detail-button.png)

Either one opens the quest's **Questions** page. On a quest with no questions yet, it explains the three types:

![The Questions page of a quest with no questions: Short Answer, Long Answer and File Upload buttons, and an explanation of each](../images/submission-questions/questions-empty.png)

!!! note
    A new quest has to be saved before you can add questions to it.

### Create a question

1. Press the button for the type you want: **Short Answer**, **Long Answer** or **File Upload**.
2. Write the **Instructions**. This is what the student sees, so put the actual prompt or problem here. It's a full editor, so you can include images, links and formatting.
3. Decide whether the question is **Required**. It starts ticked: untick it to make the question optional.
4. Give the marker something to compare against, if you like:
    * **Solution text** (text questions) or a **Solution file** (file questions): an ideal or example answer, shown beside the student's answer when you mark it.
    * **Marker notes**: anything else the person marking should know, such as what counts as an acceptable answer.

    ![The Create "Short Answer" Question form, with its instructions, solution text and marker notes filled in](../images/submission-questions/create-short-answer.png)

5. For a **File Upload** question, choose the **Allowed file type**. The legend under it lists exactly which file formats each choice accepts.

    ![The Create "File Upload" Question form, with a solution file, Image as the allowed file type, and the legend of file formats](../images/submission-questions/create-file-upload.png)

6. Press **Create**.

!!! warning "Files that can carry a script"
    **Also allow file types that can carry a script** adds SVG to the image choices, and SVG, HTML, XML and similar to **All**. A browser can run a script from these, so ByteDeck hands such an answer to you as a download rather than opening it. Tick it only for a quest that asks for one, such as a web design quest.

A question's type is fixed once it's created. To turn a short answer into a long answer, delete it and create a new one.

### Reorder, edit and delete questions

Once a quest has questions, the Questions page lists them with their type, instructions, whether they're required, and their solution and marker notes:

![The Questions page listing a short answer, a long answer and a file upload, each with up and down arrows, an edit button and a delete button](../images/submission-questions/question-list.png)

* The **arrows** move a question up or down. Students see the questions in this order, numbered from the top.
* The **pencil** opens the question for editing.
* The **bin** deletes it, after you confirm. Answers students have already submitted are kept, labelled *(question was deleted)*.

## What students see

The submission form gains one numbered answer field per question, in your order, above the usual comment box. Required questions must be answered before the quest can be submitted; optional ones say *(optional)*:

![A student's submission form: Question 1 with a one-line box and "0 / 200 characters", Question 2 (optional) with a rich-text editor, and Question 3 (optional) with an "Attach a file" heading, a Choose file button, and help ending "Allowed file types: Image"](../images/submission-questions/submission-form.png)

Short answers
:   A counter under the box shows how much of the 200 characters is used, and the box stops accepting typing when it's full.

    ![A short answer with "102 / 200 characters" under it](../images/submission-questions/short-counter.png)

Long answers
:   The same editor as the comment box, so students can format their answer and include images and links.

File uploads
:   The student picks one file with **Choose file**. The help under the button says what the question accepts, and the info icon lists the exact file formats. A file of the wrong type, or over 16 MB, is refused with a message saying why, so the student can pick another.

### Answers save with the student's draft

Students don't lose work in progress. Their answers are saved with their draft as they work: the draft saves itself about once a minute, and **Save Draft** saves it at once.

A chosen file is saved straight away, and listed above the button with a **Delete** button beside it, the same way files attached to the comment box are listed:

![A file question after choosing a file: quest-map.png listed with a Delete button beside it, and the Choose file button below](../images/submission-questions/answer-file-saved.png)

* **Choosing another file** replaces the saved one: a file question holds one file.
* **Delete** removes the saved file, for a file chosen by mistake. On an optional question it's how a student leaves the answer empty again.

When the student comes back later, their text answers are filled back in and their saved file is still listed. If submitting sends the student back to the form (a required answer was left blank, say), the saved files are kept, so nothing needs choosing twice.

## Mark the answers

When a student submits, their answers appear with the submission, on **Quest Approvals** and on the submission's own page, in three columns: each **Question**, the **Answer provided**, and your **Solution**, so comparing takes one glance. The Solution column is marked *(visible to staff only)*, because students never see it.

![A submission's answers in three columns: Question, Answer provided, and Solution (visible to staff only), with an X button beside each answer and an info button beside the first solution](../images/submission-questions/marking-answers.png)

Images are shown in place, video and audio get a player, and every file has a link to the original. Any other kind of file is shown as its link. On a phone the columns stack: the question, then the answer, then the solution.

A question with **marker notes** has an info button beside its solution. Press it to read the notes, formatting and all; they stay open until you press it again, press Escape or click elsewhere:

![The marker notes open in a popup beside the first solution, reading "Look for campaigns as columns."](../images/submission-questions/marker-notes.png)

### Mark answers wrong

Beside each answer is an **X**. Press it to mark that answer wrong: the X turns red and the answer's row is highlighted. Press it again to take the mark back. Each press is saved at once, and until you return or approve the quest, only teachers see it.

![The first answer marked wrong: its X is red and its row highlighted, and the other two answers are unmarked](../images/submission-questions/marking-wrong.png)

When you **Return** or **Approve** the quest, every answer of that submission gets its mark, which the student sees too: a green check, or a red X (on a highlighted row) for each answer you marked wrong.

* **Returning** the quest brings back only the questions you marked wrong. Each keeps its number, and a text answer starts with what the student wrote before, so they fix it rather than retype it. A file answer starts empty, with their earlier file still shown above. If you mark nothing wrong, no questions come back: the student just gets the comment box.
* **Approving** works with or without marks: you can mark some answers wrong and still approve the quest, and the student sees which ones were wrong.
* **Marks are final** once you return or approve. If you forget to mark an answer before returning, the student can answer in the comment box instead, or hand the quest back for you to look at again.

Here's what the student sees after a return with the first answer marked wrong: their earlier answers with a red X or a green check,

![The student's earlier answers: the first with a red X on a highlighted row, the other two with green checks](../images/submission-questions/returned-marks.png)

and only Question 1 back on their form, holding their earlier answer:

![The submission form after the return, with only Question 1, its box holding the earlier answer](../images/submission-questions/returned-redo.png)

Students see the answers table on their own submission headed **Your answer**, without the Solution column or your marker notes.

Approve, comment on or return the submission as usual: see [Review submissions](../quick-start/review-submissions.md).

## Questions travel with the quest

* **Copying a quest** copies its questions too, so the copy asks the same things.
* **Sharing a quest to the Shared Library** carries its questions, and importing it brings them along.

!!! note
    A question's solution and marker notes travel with it. Like a quest's instructor notes, teachers on every deck that imports the quest can read them, so check them before you share.
