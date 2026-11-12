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

![The Report card data page for Block A, covering 8 students: under "1. Proficiency scale", four XP boxes, Emerging from 100, Developing from 250, Proficient from 330 and Extending from 430 (1); under "2. Student data", the buttons Download as one file (JSON) (2) and Download a file per student (ZIP) (3); under "3. Key", the button Download key (CSV) (4)](../images/report-card-data/downloads.png)
/// caption
The report card data for a group of eight students, with the proficiency scale as the page first shows it.
///

1. **Proficiency scale**: the XP at which each level starts. Every download places each student on it. [Map XP onto the proficiency scale](#map-xp-onto-the-proficiency-scale) explains how to choose the numbers.
2. **Download as one file (JSON)**: a record for every student in the group, in one file.
3. **Download a file per student (ZIP)**: the same records, as a file for each student. Use it if your AI tool says the single file is too large, or to give it a few students at a time.
4. **Download key (CSV)**: a spreadsheet that says which student each code stands for, with their name, username, grade and courses, and their XP and proficiency level in each course. Keep this one to yourself: anyone holding both the data and the key can tell whose record is whose.

The files cover the students who are in the group now: those registered in it in a semester that is open. Staff, test accounts and archived students are left out.

## Map XP onto the proficiency scale

A report card that uses the proficiency scale needs a level for each student, and ByteDeck counts XP. The **Proficiency scale** boxes say how one becomes the other: each holds the XP at which a level starts, and a student is at the highest level their XP in the course reaches. With less than the first level's XP, they are at **Insufficient Evidence**.

The page opens with this scale:

| XP in the course | Level |
| --- | --- |
| under 100 | Insufficient Evidence |
| 100 to 249 | Emerging |
| 250 to 329 | Developing |
| 330 to 429 | Proficient |
| 430 or more | Extending |

Those numbers suit one course at one point in its semester. XP keeps growing as the semester goes on, so choose your own each time you report:

1. **Find what 100% is today.** Under the heading, the page lists each course in the group that uses marks, with the XP that earns a mark of 100% today: the course's XP for 100%, times the share of the semester's class days that have passed. In the picture above it is 475 XP.
2. **Decide what share of that each level needs.** The opening scale is close to 20%, 50%, 70% and 90% of 475 XP. If 100% were 800 XP today, the same shares would start the levels at about 170, 420, 555 and 725 XP.
3. **Type your numbers into the four boxes.** Each level has to start at more XP than the one before it.
4. **Download.** The numbers go with each download you make from the page. They are not saved, so the page opens with its own scale again next time.

Each student's level then appears in the data, as `proficiency_level` in each of their courses, and in the key, where you can read it beside their name. The data also records the scale you used.

Two things to keep in mind:

- One scale covers every course in the group. If the group mixes courses that need different numbers, download once for each, changing the boxes in between.
- A level drawn from XP is a starting point. XP counts how much approved work a student has done, so check each level against the work itself before you report it.

## What the data holds

Each student's record covers their work in the open semester, in all of their courses:

- their **grade**, total XP and rank;
- for each **course**: their XP in it, their level on the proficiency scale, their mark and mark range (for a course that uses marks), their average XP per class day, and any XP adjustment with its explanation;
- a **summary of their work**: how many quests are approved, awaiting approval, returned or in progress, when they last handed something in, and the XP approved week by week;
- the **campaigns** they have worked in, with how many quests they have had approved in each;
- their XP by **tag**;
- their **badges**, with the days they were granted and whether each came from meeting its prerequisites or from a teacher;
- every **quest** they have started, with its dates and status, and the whole **conversation** on it: what the student wrote when handing it in, their answers to the quest's questions, and what you wrote back.

The file opens with a section that explains each of these to the AI model reading it, and describes the semester, courses, proficiency scale, ranks, mark ranges and campaigns the records refer to, so you don't have to explain how your deck works.

A few things are left out or shortened on purpose:

- Attached files are listed by type only (`pdf`, `png`), not by name, and their contents are not included.
- A comment or an answer longer than 2000 characters is cut short and marked as cut.
- A comment a student has started but not yet handed in is not included.

## How names are kept out

In the data, a student is known by a code such as `S42`. A student's code never changes, but the key lists only the students who are in the group when you download it, so download the key each time you download the data.

Students' names also turn up in what people write ("Great work, Jamie!"), so they are replaced there too:

- the student's own name becomes `[STUDENT]`, and another student's becomes `[PEER]`;
- web addresses become `[link]` and email addresses become `[email]`, since they often contain a name.

The names replaced are the first name, last name, preferred name and username of every student currently registered in a course on your deck. A word is only replaced when it starts with a capital letter or contains a digit, so that "I will fix it" survives a student named Will. A username of three or more characters is replaced however it is typed, unless it is simply one of the student's names.

!!! warning "Look through the file before you share it"
    Replacing names is a best effort. A nickname, a misspelled name, or a name typed without its capital letter is not caught. Search the file for a few of your students' names before you give it to anyone, and only use an AI tool your school or district allows for student work.

## Drafting comments with it

Any AI model that accepts a file can work from the data. It will write better comments if you also give it:

- **what a comment must contain**: your school or district's reporting criteria, and the length you have room for;
- **what the course teaches**: the learning standards or outcomes you assessed, since the data shows what students did but not which standards it was evidence of;
- **your own judgement**: the grade you have decided on for each student, by code, any proficiency level you changed from the one in the data, and anything you saw in class that never reached ByteDeck;
- **your voice**: two or three comments you have written before.

Ask it to list, beside each comment, the quests and conversations the comment rests on, so that you can check each claim. Then use the key to put the names back, and edit each comment as your own.
