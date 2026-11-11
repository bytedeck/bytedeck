# Report card data

When report cards are due, an AI model can draft a comment for each student, if it knows what the student has done. **Report card data** gathers that for one group at a time: every student's courses, marks, quests and badges this semester, with the conversations you had about their work, in a file made to be read by an AI model.

The file names no student. You get the names separately, in a key that stays with you.

## Download the files

Open **Admin > Groups** and press the view button on the group's row to see its students. Then press the report card data button beside the group's name:

![The heading "Students in Group: Block A" with three buttons beside it: edit, delete, and the report card data button (outlined)](../images/report-card-data/group-button.png)
/// caption
A group's page. The outlined button opens its report card data.
///

The page that opens offers the students' data and its key as separate downloads:

![The Report card data page for Block A, covering 8 students: under "1. Student data", the buttons Download as one file (JSON) (1) and Download a file per student (ZIP) (2); under "2. Key", the button Download key (CSV) (3)](../images/report-card-data/downloads.png)
/// caption
The report card data for a group of eight students.
///

1. **Download as one file (JSON)**: a record for every student in the group, in one file.
2. **Download a file per student (ZIP)**: the same records, as a file for each student. Use it if your AI tool says the single file is too large, or to give it a few students at a time.
3. **Download key (CSV)**: a spreadsheet that says which student each code stands for, with their name, username, grade and courses. Keep this one to yourself: anyone holding both the data and the key can tell whose record is whose.

The files cover the students who are in the group now: those registered in it in a semester that is open. Staff, test accounts and archived students are left out.

## What the data holds

Each student's record covers their work in the open semester, in all of their courses:

- their **grade**, total XP and rank;
- for each **course**: their XP in it, their mark and mark range (for a course that uses marks), their average XP per class day, and any XP adjustment with its explanation;
- a **summary of their work**: how many quests are approved, awaiting approval, returned or in progress, when they last handed something in, and the XP approved week by week;
- the **campaigns** they have worked in, with how many quests they have had approved in each;
- their XP by **tag**;
- their **badges**, with the days they were granted and whether each came from meeting its prerequisites or from a teacher;
- every **quest** they have started, with its dates and status, and the whole **conversation** on it: what the student wrote when handing it in, their answers to the quest's questions, and what you wrote back.

The file opens with a section that explains each of these to the AI model reading it, and describes the semester, courses, ranks, mark ranges and campaigns the records refer to, so you don't have to explain how your deck works.

A few things are left out or shortened on purpose:

- Attached files are listed by type only (`pdf`, `png`), not by name, and their contents are not included.
- A comment or an answer longer than 2000 characters is cut short and marked as cut.
- A comment a student has started but not yet handed in is not included.

## How names are kept out

In the data, a student is known by a code such as `S42`. A student's code never changes, so the key you downloaded once still matches data you download later.

Students' names also turn up in what people write ("Great work, Jamie!"), so they are replaced there too:

- the student's own name becomes `[STUDENT]`, and another student's becomes `[PEER]`;
- web addresses become `[link]` and email addresses become `[email]`, since they often contain a name.

The names replaced are the first name, last name, preferred name and username of every student currently registered in a course on your deck. A word is only replaced when it starts with a capital letter or contains a digit, so that "I will fix it" survives a student named Will.

!!! warning "Look through the file before you share it"
    Replacing names is a best effort. A nickname, a misspelled name, or a name typed without its capital letter is not caught. Search the file for a few of your students' names before you give it to anyone, and only use an AI tool your school or district allows for student work.

## Drafting comments with it

Any AI model that accepts a file can work from the data. It will write better comments if you also give it:

- **what a comment must contain**: your school or district's reporting criteria, and the length you have room for;
- **what the course teaches**: the learning standards or outcomes you assessed, since the data shows what students did but not which standards it was evidence of;
- **your own judgement**: the grade or proficiency level you have decided on for each student, by code, and anything you saw in class that never reached ByteDeck;
- **your voice**: two or three comments you have written before.

Ask it to list, beside each comment, the quests and conversations the comment rests on, so that you can check each claim. Then use the key to put the names back, and edit each comment as your own.
