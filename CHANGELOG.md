
# Bytedeck Changelog
This file chronologically records all notable changes to this website, including new features, tweaks, and bug fixes.

[Changelogs](http://keepachangelog.com/en/0.3.0/) | [Versioning](http://semver.org/) | [Branch model](https://nvie.com/posts/a-successful-git-branching-model/)

### [1.26.0] 2025-07-10 Marcus I
* New Features:
 - New Campaign 'Description' field [#1772](https://github.com/bytedeck/bytedeck/issues/1772)
 - Add optional start and end times to youtube video insert widget [#1556](https://github.com/bytedeck/bytedeck/issues/1556)
 - Preview quests on the Library tab [#1757](https://github.com/bytedeck/bytedeck/issues/1757)
* Tweaks:
 - Redirect to bytedeck.com when deck name isn't found (or typo) [#1583](https://github.com/bytedeck/bytedeck/issues/1583)
 - Extend email confirmation link to 90 days [#1767](https://github.com/bytedeck/bytedeck/issues/1767)
 - Remove 'active' column from campaign list (redundant since only active campaigns will appear in this tab) [#1749](https://github.com/bytedeck/bytedeck/issues/1749)
 - Announcement notifications can now be removed from the New Notifications menu [#1233](https://github.com/bytedeck/bytedeck/issues/1233)
 - Improve the "form already submitted" alert message [#1778](https://github.com/bytedeck/bytedeck/issues/1778)
 - Prevent deletion of Campaign if it has quests in it [#1773](https://github.com/bytedeck/bytedeck/issues/1773)
 - Quest (and other) search fields now search on all words seperately [#1791](https://github.com/bytedeck/bytedeck/issues/1791)
 - Avatar styling on profile page [#822](https://github.com/bytedeck/bytedeck/issues/822)
* Refactor/Optimizations:
* Bugfixes:
 - Add rate limit 429 error page [#1776](https://github.com/bytedeck/bytedeck/issues/1776)
 - Handle empty 'XP Requested' field [#1561](https://github.com/bytedeck/bytedeck/issues/1561)
 - Add blank values for Quests in Campaign and Total XP available on Campaign detail view [#1748](https://github.com/bytedeck/bytedeck/issues/1748)
 - Fix user access to the Library tab.  Only authenticated staff can access [#1789](https://github.com/bytedeck/bytedeck/issues/1789)
 - Fix automated link creation of urls in comments [#930](https://github.com/bytedeck/bytedeck/issues/930)
 - Remove uneccessary notification for a submission on a quest when the teacher is set to be notified already [#699](https://github.com/bytedeck/bytedeck/issues/699)
 - Fix various campaign import issues [#1764](https://github.com/bytedeck/bytedeck/issues/1764)
* Devops:
 - Upgrade database to Postgres 16
 - Update automated testing to use Ubuntu 22.04
 - Update CodeQL Analysis to V2 [#1784](https://github.com/bytedeck/bytedeck/issues/1784)


### [1.25.2] 2025-02-19
* New Features:
  - Add ability to fully delete users from their profile [#1751](https://github.com/bytedeck/bytedeck/issues/1751)
* Refactor/Optimizations:
  - Quest and Submission list accordion contents now load when clicked, vastly improving loading speeds of large quest and submission lists [#1474](https://github.com/bytedeck/bytedeck/issues/1474)
* Bugfixes:
  - Fix broken widget styling on all forms [#1750](https://github.com/bytedeck/bytedeck/issues/1750)
  - Fix broken QuestSubmission and Comment edit views in Django Admin
* Devops:
  - Update to Python 3.10


### [1.25.1] 2025-02-09
* Tweaks:
  - Improve map update messages [#1721](https://github.com/bytedeck/bytedeck/issues/1721)
  - Auto-delete notifications older than 90 days [#757](https://github.com/bytedeck/bytedeck/issues/757)
* Bugfixes:
  - Recalc student's XP when a badge is revoked from a student [#1743](https://github.com/bytedeck/bytedeck/issues/1743)
  - Fix broken "Available Date" field's default value when creating a new quest [#1741](https://github.com/bytedeck/bytedeck/issues/1741)
  - Fix alert message margins [#1720](https://github.com/bytedeck/bytedeck/issues/1720)
  - Fix timestamps on submission comments [#1716](https://github.com/bytedeck/bytedeck/issues/1716)
  - Fix broken form field when trying to grant badges in bulk [#1574](https://github.com/bytedeck/bytedeck/issues/1574) and [#1472](https://github.com/bytedeck/bytedeck/issues/1472)
* Devops:
  - Remove save() from full_clean management command and run on all decks, fix all warnings
  - fix broken workflow badges in README, e.g. [![Build and Tests Status](https://github.com/bytedeck/bytedeck/actions/workflows/build_and_test.yml/badge.svg?branch=develop)](https://github.com/bytedeck/bytedeck/actions?query=workflow%3A%22Build+and+Tests%22+branch%3Adevelop)
  - remove old draft_text field (was replaced by a draft Comment object)


### [1.25.0] 2024-09-04
* New Features
  - Maps auto-update when an item within the map is updated [#1660](https://github.com/bytedeck/bytedeck/issues/1660)
  - Custom, otional field for student profiles. This can be set in Site Config;  Previously "Grad Year" field [#1273](https://github.com/bytedeck/bytedeck/issues/1273)
  - When students earn badges and ranks, there is now a popup message congratulating/informing them [#551](https://github.com/bytedeck/bytedeck/issues/551)
  - Library feature can now import entire campaigns [#1667](https://github.com/bytedeck/bytedeck/issues/1667)
  - Submission return and approval no longer reloads page [#1349](https://github.com/bytedeck/bytedeck/issues/1349)
* Bugfixes:
  - Typo in default Ranks
  - Expired quests in the available quests tab now appear at the top of the list [#1430](https://github.com/bytedeck/bytedeck/issues/1430)
  - Adding an Excluded Dates to a semester does not activate datepicker; [#1682](https://github.com/bytedeck/bytedeck/issues/1682)
* Devops:
  - Update Django to 4.2 LTS
  - Enhance Campaign and Quest Library Management with new templates and routing
  - Refactored approvals and quest_list to use enums for tabs [#1150](https://github.com/bytedeck/bytedeck/issues/1150)
  - full_clean clearer error printout [#1669](https://github.com/bytedeck/bytedeck/issues/1669)
  - add hash_to_link script to make Changelogs easier to write
  - remove 'future' dependancy; update Dockerfile and docker-compose legacy code
  - many dependancy updates
  - Added CRISPY_FAIL_SILENTLY to settings.py; [#629](https://github.com/bytedeck/bytedeck/issues/629)

### [1.24.2] 2024-07-28 - Prep for big submission questions update
* Tweaks:
  - List related maps in Quest and Badge detail views [#273](https://github.com/bytedeck/bytedeck/issues/273)
  - Add Library link to quest submenu on sidebar if Library turned on in Site Config [#1656](https://github.com/bytedeck/bytedeck/issues/1656)
* Bugfixes:
  - Notifications to comments don't jump to comment when clicked [#1541](https://github.com/bytedeck/bytedeck/issues/1541)
  - Only allow Site Owner to toggle experimental Library option [#1651](https://github.com/bytedeck/bytedeck/issues/1651)
* Devops:
  - Replaced submission draft_text with draft_comment using comment model [#1627](https://github.com/bytedeck/bytedeck/issues/1627)
  - Full clean all models management command [#1643](https://github.com/bytedeck/bytedeck/issues/1643)
  - Update tons of dependancies


### [1.24.1] 2024-07-15 - Loads of Tweaks Update
* Tweaks:
  - Adding a Rank as a prereq to an object automatically generates a map for that Rank on the Rank list page [#88](https://github.com/bytedeck/bytedeck/issues/88)
  - New Site Config option added to only show tags that students have earned XP on (instead of all tags) [#1143](https://github.com/bytedeck/bytedeck/issues/1143)
  - Add Mark Range values below the XP progress chart if using Mark Calculations option [#1508](https://github.com/bytedeck/bytedeck/issues/1508)
  - Added name field to Semesters # 1565
  - Added "Intro" tags to starter quests and badges for new decks [#1207](https://github.com/bytedeck/bytedeck/issues/1207)
* Bugfixes:
  - XP Progress Chart not showing XP earned over weekends and excluded days until next day of class [#1513](https://github.com/bytedeck/bytedeck/issues/1513)
  - Fixed spacing in some comments [#1235](https://github.com/bytedeck/bytedeck/issues/1235)
  - Delete Comment form's Cancel button did nothing [#1497](https://github.com/bytedeck/bytedeck/issues/1497)
  - Tag detail view showed duplicate ordinals for repeatable quests [#1210](https://github.com/bytedeck/bytedeck/issues/1210)
  - XP earned by tag on profiles showed unapproved quests [#1208](https://github.com/bytedeck/bytedeck/issues/1208)
  - Clicking student list from portfolios pages gave an error [#1539](https://github.com/bytedeck/bytedeck/issues/1539)
  - Importing a Badge with a new Badge Type no longer fails. [#794](https://github.com/bytedeck/bytedeck/issues/794)
  - Fix error in certbot override command.
* Devops:
  - Fix failing tests due to extra Library tenant [#1590](https://github.com/bytedeck/bytedeck/issues/1590)
  - Fix github actions crash/test fail at 11pm Pacific Time [#1327](https://github.com/bytedeck/bytedeck/issues/1327)
  - Add configuration for @coderabbitai [#1626](https://github.com/bytedeck/bytedeck/issues/1626)
  - `generate_content` refactored as management command and now creatses campaigns (Category objects) for quests [#1014](https://github.com/bytedeck/bytedeck/issues/1014)
  - Flake8 local run, precommit hook, and github action all use same config file [#1623](https://github.com/bytedeck/bytedeck/issues/1623)


### [1.24.0] 2024-05-19 - Quest Library MVP
* Features:
  - Minimally viable Quest Library Feature!!  Turn on this feature in the Site Settings which will enable a new "Library" tab when viewing your quests. This allows you to import quests shared from the special Library deck.  Currently the feature is very limited.
* Tweaks:
  - Verify existance of email domains to prevent some typos and fake user email addresses [#1562](https://github.com/bytedeck/bytedeck/issues/1562)
  - Add helpful message when saving a profile doesn't work, since the form is long and might not be clear what the problem is.
  - New deck workflow improvements, including more helpful intro emails when new decks are created [#1489](https://github.com/bytedeck/bytedeck/issues/1489)
* Bugfixes:
  - Fix announcement emails being sent to old/removed email addresses, and inactive students [#1551](https://github.com/bytedeck/bytedeck/issues/1551)
  - Multi-file uploads are now possible again (Hold Ctrl to select multiple files) [#1353](https://github.com/bytedeck/bytedeck/issues/1353)


### [1.23.5] 2024-02-17
* Bugfixes:
  - Prevent submission buttons from covering text on small/mobile widths; closes [#1218](https://github.com/bytedeck/bytedeck/issues/1218)
  - Make archived announcements inaccessible to students [#1483](https://github.com/bytedeck/bytedeck/issues/1483)
  - Add template to error page for inactive accounts [#1553](https://github.com/bytedeck/bytedeck/issues/1553)
  - Confirmation not displaying when closing a semester [#1563](https://github.com/bytedeck/bytedeck/issues/1563)
* Code cleanup:
  - Refactor project to use docker compose v2
  - Remove name field from Profile model (not used) [#1549](https://github.com/bytedeck/bytedeck/issues/1549)
  - Remove old Grade field from course form [#1230](https://github.com/bytedeck/bytedeck/issues/1230)


### [1.23.4] 2023-12-10
* Tweak:
  - Simplify Badge popups by removing all the buttons and providing info only.  Now when you click a badge, it will take you to the badge detail page (which most users probably don't even know exists).  Specific badges that were granted to a student can still be revoked through the user's profile (same as before: click the badge on their profile page, then in the list of badges granted to the user, hit the delete button beside the one you want to revoke.)
* Bugfixes:
  - Only send announcement and notification emails to users with verified email addresses (to prevent bounceback and other rejection issues) [#1374](https://github.com/bytedeck/bytedeck/issues/1374)
  - Quest accordions not loading in Campaign detail view [#1512](https://github.com/bytedeck/bytedeck/issues/1512)
  - Remove default admin email address on new tenants
  - Fix latest submission time on Quest Summary (experimental) page [#1542](https://github.com/bytedeck/bytedeck/issues/1542)
  - Fix access permission for Quest Summary page (should have been staff and TAs only)
  - Fix Quest Summary page to only include approved submissions in queryset.
  - Fix Quest Summary page NaN error when 0 completed quests
* Bytedeck Admin:
  - Exclude admin user from a tenant's "last staff login" date.


### [1.23.3] 2023-11-28
* Optimizations:
  - Upgrade celery-beat and tenant-schemas-celery dependancies and refactor periodic task creation [#1510](https://github.com/bytedeck/bytedeck/issues/1510)

* Bugfixes:
  - When a quest is deleted, delete all submissions of it as well, instead of having them hang around like zombies [#1488](https://github.com/bytedeck/bytedeck/issues/1488)
  - Fix: quest available outside course and no prereqs doesn't appear for an existing student without a course [#957](https://github.com/bytedeck/bytedeck/issues/957)
  - Fix: Email verfication link on new deck creation [#1492](https://github.com/bytedeck/bytedeck/issues/1492)
  - Add queue when running celery tasks... so they actually run [#1540](https://github.com/bytedeck/bytedeck/issues/1540)


### [1.23.2] 2023-11-24 Many bugs squashed
* Bugfixes:
  - Fix sort order of Badge Types [#1484](https://github.com/bytedeck/bytedeck/issues/1484)
  - Fix error when accessing notifications list [#1527](https://github.com/bytedeck/bytedeck/issues/1527)
  - Do not allow auto-publish on archived announcements [#1216](https://github.com/bytedeck/bytedeck/issues/1216)
  - Fix new user portfolio creation [#1496](https://github.com/bytedeck/bytedeck/issues/1496)
  - Prevent duplicate calculation of avaialable quests (waste of resources) [#1405](https://github.com/bytedeck/bytedeck/issues/1405)
  - Trigger mark re-calculation daily [#1500](https://github.com/bytedeck/bytedeck/issues/1500)
  - Prevent notification emails from being sent to inactive students[#1206](https://github.com/bytedeck/bytedeck/issues/1206)
  - Fix bug preventing uploads of more than 2MB (should be 16 MB) [#1486](https://github.com/bytedeck/bytedeck/issues/1486)
  - Add `th`, `caption`, and `scope` to allowable tags in Summernote Safe Widget[#1487](https://github.com/bytedeck/bytedeck/issues/1487)
  - Remove unused DateType model that was causing errors in some decks [#1241](https://github.com/bytedeck/bytedeck/issues/1241)


### [1.23.1] 2023-09-10 Just bugs
* Bugfixes:
  - Creating maps with duplicate initial objects results in error [#1370](https://github.com/bytedeck/bytedeck/issues/1370)
  - Fix submissions table column widths
  - Fix CSS bug that removed first column of tables in accordion



### [1.23.0] 2023-09-04
* Feature:
  - Pages for creating, editing, and listing Mark Ranges (appears in Admin menu if when "Use mark percentages" feature is enabled in a deck's Site Config)
* Tweaks:
  - Add column showing number of students on Group/Block list page, and hyperlink to Group detail page.
  - Add column showing number of students in acourses in a semester.
* Bugfixes:
  - Internal server error when reading notifications sometimes [#1446](https://github.com/bytedeck/bytedeck/issues/1446)
  - non-relative menu links always open in a new tab regardless of setting [#1397](https://github.com/bytedeck/bytedeck/issues/1397)
  - Don't render duplicate mark ranges in Mark Calculations graph legend [#1242](https://github.com/bytedeck/bytedeck/issues/1242)
  - Provide proper error message when uploading too much text [#1350](https://github.com/bytedeck/bytedeck/issues/1350)
  - Badges without a sort order break profile page [#1342](https://github.com/bytedeck/bytedeck/issues/1342)
  - Quest and submission ID conflicts in list views [#1466](https://github.com/bytedeck/bytedeck/pull/1466)
  - Calendar button sometimes doesn't add additional exclude dates [#1416](https://github.com/bytedeck/bytedeck/issues/1416)
  - Too long name of Quest and large XP value causes map generation to fail [#929](https://github.com/bytedeck/bytedeck/issues/929)
  - Only load quest details for quests listed in the active tab [#1467](https://github.com/bytedeck/bytedeck/issues/1467)
  - Fix formatting of default replies/comments [#1235](https://github.com/bytedeck/bytedeck/issues/1235)
  - Missing icons [#1132](https://github.com/bytedeck/bytedeck/issues/1132)
* Devops:
  - filterable QuerySetSequence in GFK Select Field/Widget [#1472](https://github.com/bytedeck/bytedeck/issues/1472)
  - Wrap INTERNAL_IPS getter inside try/except [#1463](https://github.com/bytedeck/bytedeck/pull/1463)
* Bytedeck Admin:
  - Expansion of the New Deck form allows entry of deck owner email and name, sets this to the deck owner profile, and sends verification email.
  - Tenant list view shows deck owner info from the deck itself



### [1.22.0] 2023-07-31
 * Feature: Add simplified registration option to SiteConfig
 * Admin Features:
   - Admin action on public tenant to send emails to deck owners
   - Delete old decks with security protection
 * Optimizations
   - Major refactor of Students lists to speed up page load times
   - Refactor of some Quest and Submission pages to speed up page load times
 * Tweaks:
   - Refactor status icons on quest list for minor performance improvements
 * Bugfixes:
   - Wrap long urls [#1425](https://github.com/bytedeck/bytedeck/issues/1425)
   - Add back missing quest completion dates on profiles [#1427](https://github.com/bytedeck/bytedeck/issues/1427);
   - Inconsistant tag name creation [#1282](https://github.com/bytedeck/bytedeck/issues/1282);
   - Tagg error duplicate key value violates unique constraint [#1351](https://github.com/bytedeck/bytedeck/issues/1351);


### [1.21.2] 2023-07-03 - Summer speed up 1
 * Feature: Campaign lists are now searchable and sortable (via bootstrap-tables)
 * Optimizations
   - Major refactor of Students lists to speed up page load times
   - Refactor of some Quest and Submission pages to speed up page load times
 * Tweaks:
   - Organize Quest related items in Admin menu and add Common Info
   - Reorganize Quests submenu for consistancy with Admin menu items
   - Clean up mobile layout of content for quest asnd submission previews (accordian expansion)
   - Indicate skipepd quests in status field of submissions and approvals tabs
 * Bugfixes:
   - Skipped quests now save comments
   - Ignore draft and archived quests when considering Campaign completion; [#1286](https://github.com/bytedeck/bytedeck/issues/1286)
   - Sort badges by sort_order on profiles [#1411](https://github.com/bytedeck/bytedeck/issues/1411);
   - Allow deletion of (non-current) semesters with no students [#1418](https://github.com/bytedeck/bytedeck/issues/1418);
   - Added proper sorting to status column [#1420](https://github.com/bytedeck/bytedeck/issues/1420);



### [1.21.1] 2023-06-17
 * Feature: Refactor all quest/submission lists to be searchable and sortable.
 * Feature: Add list of badge assertions to the badge detail page
 * Bugfixes:
   - Fix display of My Groups button [#1395](https://github.com/bytedeck/bytedeck/issues/1395)
   - Skipped submissions do no appear in Approved tab [#1400](https://github.com/bytedeck/bytedeck/issues/1400)
   - fix broken announcement permalinks and comment links [#818](https://github.com/bytedeck/bytedeck/issues/818)
   - Add missing html elements to SummernoteSafeWidget, including HTML5 media tags
   - Fix get_banner_image_url error on public domain in some views [#1214](https://github.com/bytedeck/bytedeck/issues/1214)
   - Refactor Quest.time_expired and date_expired tests and fix buggy test [#1327](https://github.com/bytedeck/bytedeck/issues/1327)
   - Use whitelabelling for groups in buttons and elsewhere [#393](https://github.com/bytedeck/bytedeck/issues/1393)
   - Changing deck owner now grants new owner superuser permissions [#1390](https://github.com/bytedeck/bytedeck/issues/1390)
 * Devops: Improved automated test coverage throughout app


### [1.21.0] 2023-05-30
* New feature: Deack owners can upload a custom JacaScript file and custom CSS Stylesheet unqiue to their decks (Admin > Site Configuration > Advanced)
* Whitelabelling for Announcements, Students, and Badges (Admin > Site Configuration)
* Quest list refactored to use bootstrap-table for sort and search features.
* Bugfixes:
  - Fix figure and figcaption in Safe Summernote Widget.
  - Pluralize bug [#1366](https://github.com/bytedeck/bytedeck/issues/1366)
  - Alphabetical Maps list [#1346](https://github.com/bytedeck/bytedeck/issues/1346)
  - XP button doesn't work on mobile [#1283](https://github.com/bytedeck/bytedeck/issues/1283)
  - Runaway whitespace bug [#771](https://github.com/bytedeck/bytedeck/issues/771), [#889](https://github.com/bytedeck/bytedeck/issues/771),[#1357](https://github.com/bytedeck/bytedeck/issues/771)
* Devops:
  - Improvements and updates to development envronment setup and contributing guidelines
  - Fix docker network for pg-admin container
  - Codecov CI


### [1.20.0] 2023-04-16
* New feature: Users can now sign in or sign up using their Google/Gmail account via OAuth2.  This feature must be specifically requested for a deck as it requires manually registering the deck's url with Google.
* New feature: Summernote Advanced WYSIWYG widget allows scripts to run.  Currently implemented on the Quest Description, Submission Details, and Instructor Notes fields.  Indicated with a red CodeView button when hovered.
* Email authentication.  Users will now be reminded on login to verify their email addresses by clicking the verification link sent to the email address they enter in their profile.  Users can resend the verification link from their profile.  Unverified emails will be ignored when sending notifications or announcements.  This only affects user who do not register with Google Sign In unless they change the email address in their profile.
* Set login session expiry to 8 weeks (when you tick "Remember Me")
* Bugfixes:
  - Summernote "Safe" widget properly escapes HTML and strips script tags.
  - Archived quests should not apopear in maps [#1291](https://github.com/bytedeck/bytedeck/issues/1291)
* Devops:
  - Bump build pipeline to use Ubuntu 20.04
  - Add missing migration check to build and pre-commit hooks
  - Pre-commit hooks run on entire codebase
  - Upgrade dependancies


### [1.19.4] 2023-03-20
* Add links to public tenant landing page header and footer
* Bugfixs:
  - Autofix ordinal duplicates in repeatable quests [#1260](https://github.com/bytedeck/bytedeck/issues/1260)
  - [#1266](https://github.com/bytedeck/bytedeck/issues/1266)



### [1.19.3] 2023-01-02
* Bugfixs:
  - Advanced prerequisite widget upgrade compelte (replaced DAL with select2)
  - Ordering error issue [#1266](https://github.com/bytedeck/bytedeck/issues/1266)
  - Do not return None when creating a new quest submission, issue [#1225](https://github.com/bytedeck/bytedeck/issues/1225)
* Development:
  - Update precommit config
  - Update Contributing guidelines
  - Add Pull Request template

### [1.19.2] 2022-12-04
* Add courses as a column and sort option in student profile list.
* Bugfixes:
  - Advanced prerequisites form now loads (though slow and needs more work)
  - New map form (same problem as above)
  - Handle negative XP when closing a semester
  - Quest list alphabetical sort
  - Last staff login (Bytedeck)
  - URLs for menu items now accepts external urls properly
  - Missing delete option added for student's courses
  - Custom pages (flatpages) auto generated Table of Contents repaired. Add this to the top of a custom page's HTML and it will generate a simple ToC based on "Heading 3" styled text (i.e `<h3>`):
  ```<div id="TOC"></div>```

### [1.19.1] 2022-09-03 - Beta Release
* Visual representation of tags by student, linked to in profile and in mark calculations page
* Students now have a quick reply option for returned and completed submissions.
* Campaign "active" field now works.  Quests that are part of inactive campaigns will not be visible to students and won't show up on maps (a quick way for teachers to make a group of quests dissappear)
* Homepage/landing page is now a Flatpage.  For development it's created during initdb, home url `/` redirects to the flatpage.  This allows for easier editing of the homepage in production.
* Features that no longer require acces to the Django/Site Admin, and can now be edited in the main site by staff users:
  - Staff can edit student course registrations, and register them in additional courses
* Minor tweaks and bugfixes:
  - tweak: Narrow public tenant flatpage template
  - tweak: Use full wordmark on public flatpages
  - tweak: New map creation uses a better widget to get the initial object
  - tweak: campaign detail views are now accessible to students
  - tweak: change portfolia "Public link" to "personal link"
  - tweak: Tag detail view for students now shows total XP earned and links to all submissions (including all repeats of a quest)
  - tweak: "This page if visible to staff only." added to staff only lists.
  - tweak: Change submit button test to "Submit Quest for Approval" (previousyl said "Submit Quest for Completion")
  - bugfix: tags by XP and tag charts now account for max xp per quest and student xp requested values
  - bugfix: Mark Distribution graphs no more negative values
  - bugfix: quests sort properly again
  - bugfix: account for -1 (unlimited) users in public tenant list higlighting
  - security: update several dependancies
  - many very minor tweaks and typos corrected

### [1.19.0] 2022-08-14 - Beta Release Candidate 02
* Groups (name changed from Blocks) is now a prerequisite option
* New Site Config options: Customize the name of Tags and Groups
* Deprecate 'Grade' field as part of course regsitration.  It will no longer appear and can't be selected for new course registrations
* Features that no longer require acces to the Django/Site Admin, and can now be edited in the main site by staff users:
  - Students page now has new tabs to access: Inactive students, Staff users.
* Minor tweaks and bugfixes:
  - Change quest field "visible to students" field to "published" and added help text explaining Drafts tab
  - Tenant list: fix 'active user' calculation to only include students currently registered in a course
  - Tenant list: add 'last staff login' column
  - Tenant list: Make columns sortable and filterable
  - Prereq edit buttons only visible to staff
  - Add useful info to Common Quest Info list page

### [1.18.0] 2022-08-09 - Beta Release Candidate 01 + TAGS!
* Tags:
  - Tags list can be accessed via Admin menu under Course Setup
  - Viewing a Tag's detail page will show all quests andbadges tagged with it
  - Tags can be added to quests and badges on their forms in the Tags field. Select from existing tags, or new tags will be created if they don't already exist.
  - Student Profile pages now include a list of tags, showing how much XP they have earned for each tag
  - Clicking a tag in a student profile will list which quests/badges they earned the XP from under that tag
  - Tags are listed in Quests and Badges top Info section (Quest/Badge detail view)
  - Copying a quest/badge will also copy the tags
* Notifications to staff now include a list of Quests awaiting approval
* Features that no longer require acces to the Django/Site Admin, and can now be edited in the main site by staff users:
  - "Common Quest Info" items now list/create/edit/delete from the quests submenu.
* Defaults and deck initialization:
  - New tenants (Decks) now default to max_users = 5 and trial_end_date = today + 60 days (though these fields are for info only, and still don't do anything)
  - New tenant "Deck owner" user now defaults to having notification and announcement emails = True
  - The default "Send a Message" quest in a new deck now notifies the deck owner user by default.
  - Teams badges and badge category included in new decks
* Minor tweaks and bugfixes:
  - Quest Maps list view is available to students, and re-formatted
  - Several quest/badge features and forms are now available in the quest/badge submenus
  - email notifications fixed (would only send one until server was restarted)
  - Teams badge category icon fixed
* Development:
  - Tenants in dev environment now displays proper default icons, default icons are now in repo.
  - Flake8 pre-commit hook

### [1.17.0] 2022-07-21 - Summer student contribution 03
* "Deck owner" is no longer a superuser and will not have access to Django Admin.
* Campaign list page (currently Admin > Campaigns) updated with quest count, XP available
* Campign name in quests now link to the detail view of that campaign
* Features that no longer require acces to the Django/Site Admin, and can now be edited in the main site by staff users:
  - Password resetting
  - Ability to set a user as Staff or TA (in profile form)
  - Excluded dates for a semester
* Minor tweaks and bugfixes:
  - Changing semesters is now done in the Semester views
  - "Badge Types" can now be created from Badges page
  - New blocks default to the owner user as the teacher
  - Flatpages added to the public tenant
  - New default Badge Type "Teams" and 3 new default teams badges
  - Various other minor bugfixes and tweaks

### [1.16.0] 2022-07-01 - Summer student contribution 02
* "Deck owner" field added to the Site Configuration form, indicating which user "owns" the deck.  This field can only be changed by the user currently listed as deck owner.  For future use. [#637](https://github.com/bytedeck/bytedeck/issues/637)
* Features that no longer require acces to the Django/Site Admin, and can now be edited in the main site by staff users:
  - Badge and Quest prerequisites (edit buttons can be dound beside each item's prereq list)
  - Menu Items (these appear in the ☰ menu at the top right)
  - Badge Types (edit button appears beside each badge type on the Badges page, and secondary Badge menu item on the main menu to the left)
* Minor tweaks and bugfixes:
  - Broken images and html in notifications [#755](https://github.com/bytedeck/bytedeck/issues/755)
  - Added contact link to site footer [#542](https://github.com/bytedeck/bytedeck/issues/542)
  - Change "/achievements/" urls to "/badges/" for consistancy.  Old links will still work via redirect [#997](https://github.com/bytedeck/bytedeck/issues/997)
  - Fixed broken deletion of blocks. Fix hidden blocks. [#855](https://github.com/bytedeck/bytedeck/issues/855)

### [1.15.0] 2022-06-09 - Summer student contribution 01
* Custom webpages can now be created from the Admin > Custom Pages area.
* Context-specific feedback to students when they see no available quests. [#817](https://github.com/bytedeck/bytedeck/issues/817)
* Mark Ranges are now used in the XP Progress graph
* New decks now start with some default Badge rarities. [#981](https://github.com/bytedeck/bytedeck/issues/981)
* Minor tweaks and bugfixes:
  - [#976](https://github.com/bytedeck/bytedeck/issues/976)
  - [#942](https://github.com/bytedeck/bytedeck/issues/942)
  - [#990](https://github.com/bytedeck/bytedeck/issues/990)
  - [#894](https://github.com/bytedeck/bytedeck/issues/894)
  - [#864](https://github.com/bytedeck/bytedeck/issues/864)
  - [#545](https://github.com/bytedeck/bytedeck/issues/545)
  - [#943](https://github.com/bytedeck/bytedeck/issues/943)
  - [#257](https://github.com/bytedeck/bytedeck/issues/257)
  - [#963](https://github.com/bytedeck/bytedeck/issues/963)
  - [#964](https://github.com/bytedeck/bytedeck/issues/964)


### [1.14.1] 2022-05-14
* Make usernames case insensitive (more mobile friendly due to auto-capitalization on phones)
* Add loading indicator to Notifications drop down [#896](https://github.com/bytedeck/bytedeck/issues/896)
* Bugfixes:
  - Fix loophole allowing students to start quests without a course via maps [#892](https://github.com/bytedeck/bytedeck/issues/892)
  - Trigger a recalculation of available quests for all students when a new quest is created without prereqs [#936](https://github.com/bytedeck/bytedeck/issues/936)
  - Returned quests remembers  XP value entered by student [#915](https://github.com/bytedeck/bytedeck/issues/915)
  - Remove app from prerequisite name [#944](https://github.com/bytedeck/bytedeck/issues/944)

### [1.14.0] 2022-02-21
* New Site Config option to limit displayed marks to 100%
* Improved mobile menus (bigger fonts, better organized)
* Change contact menu item to link to Github Discussions
* Dependancy upgrades:
  * Upgrade Django to 3.2 LTS (support to Apr 2024)
  * Upgrade Celery to V5 (mostly a security fix)
  * Upgrade various minor dependancies

### [1.13.0] 2022-01-16 - Mostly Map Stuff
* Campaigns can now be prerequisites [#890](https://github.com/bytedeck/bytedeck/issues/890)
* Add campaign XP to maps [#819](https://github.com/bytedeck/bytedeck/issues/819)
* Sort unordered campaign maps alphabetically [#793](https://github.com/bytedeck/bytedeck/issues/793)
* Add map transition field to Quests and Badges [#574](https://github.com/bytedeck/bytedeck/issues/574)
* [bytedeck admin] Add new fields to Tenant model [#897](https://github.com/bytedeck/bytedeck/issues/897)

### [1.12.3] 2021-12-14
* Re-enable email notifications feature
* Professionalize language [#887](https://github.com/bytedeck/bytedeck/issues/887)
* [dev] Test coverage reporting to coveralls.io
* Bugfixes:
  - [#874](https://github.com/bytedeck/bytedeck/issues/874)
  - [#862](https://github.com/bytedeck/bytedeck/issues/862)
  - [#875](https://github.com/bytedeck/bytedeck/issues/875)
  - [#885](https://github.com/bytedeck/bytedeck/issues/885)

### [1.12.2] 2021-12-05
* Add ReCaptcha to contact page to rpevent spam
* Dependencies update (Datepicker Widget)[#881](https://github.com/bytedeck/bytedeck/issues/881)
* Bugifxes:
  - [#880](https://github.com/bytedeck/bytedeck/issues/880)
  - [#877](https://github.com/bytedeck/bytedeck/issues/877)
  - [#876](https://github.com/bytedeck/bytedeck/issues/876)
  - [#865](https://github.com/bytedeck/bytedeck/issues/865)
  - [#870](https://github.com/bytedeck/bytedeck/issues/870)
  - [#866](https://github.com/bytedeck/bytedeck/issues/866)
  - [#867](https://github.com/bytedeck/bytedeck/issues/867)

### [1.12.1] 2021-11-24
* Add number indicator on quest tabs [#823](https://github.com/bytedeck/bytedeck/issues/823)
* [bugfix] Deleting quests breaks things [#868](https://github.com/bytedeck/bytedeck/issues/868).

### [1.12.0] 2021-11-20
* Add option for students to request the amount XP for their submission
* Add a max_xp option to repeatable quests, so that students can not earn more than this (per seemster)
* Add buttons to top of submissions for convenience [#701](https://github.com/bytedeck/bytedeck/issues/701)
* Add views/pages on frontend for Ranks and Campaigns
* Styling tweaks [#829](https://github.com/bytedeck/bytedeck/issues/829)
* [bugfix] Courses form icon upload.

### [1.11.5] 2021-06-08
* Add find and replace management command
* [security] Update dependancy versions (Pillow, psycopg2)
* [bugfix] Fix "do not grant xp" for badges [#835](https://github.com/bytedeck/bytedeck/issues/835)

### [1.11.4] 2021-02-15
* Replace "Skipped" tab with much more useful "Flagged" tab
* [bugfix] Limit username display length in various areas to prevent layout getting messed up
* [bugfix] Fix broken `pack` css class for evenly distributing images in a row [#814](https://github.com/bytedeck/bytedeck/issues/814)

### [1.11.3] 2021-02-05
* Add customizable outgoing email signature for announcements etc (Admin > Site Configuration)
* Change multi-select widget timeout from 3mins to Never [#792](https://github.com/bytedeck/bytedeck/issues/792)
* Remove report card dates at bottom of Mark Calculations page
* Improve formatting of avatar and XP bars in profile page
* Bugfixes:
  - Fix missing XP value for multi-course students on Mark Calculations page.
  - [#674](https://github.com/bytedeck/bytedeck/issues/674)
  - [#805](https://github.com/bytedeck/bytedeck/issues/805)
  - [#785](https://github.com/bytedeck/bytedeck/issues/785)
  - [#752](https://github.com/bytedeck/bytedeck/issues/752)
  - [#761](https://github.com/bytedeck/bytedeck/issues/761)
  - [#749](https://github.com/bytedeck/bytedeck/issues/749)

### [1.11.2] 2021-01-31
* Add edit link to quest "General Info" panel at left (Common Data)
* Tweak styling for code elements in dark theme
* Remove "Hackerspace" reference in spam clicking message
* Include teachers in announcements emails
* Bugfixes:
  - [#799](https://github.com/bytedeck/bytedeck/issues/799)
  - [#790](https://github.com/bytedeck/bytedeck/issues/790)
  - [#788](https://github.com/bytedeck/bytedeck/issues/788)

### [1.11.1] 2020-12-15
* [teachers] Submission summary page improvements
* Minor styling tweaks

### [1.11.0] 2020-12-13
* [teachers] Add a summary/metrics page of submission data for each quest, including a histogram of submission times
* [teachers] Add "Initial time to complete" for to each submission, in minutes
* [teachers] Improve styling of selection widgets in dark theme
* [teachers] Upgrade widgets on Badge granting forms
* Minor improvements to Semester list
* Minor styling tweaks
* [bugfix] Remove notification indicator instead of showing 0 after all notifications removed
* [bugfix] Join a Course form now only displays active courses
* [bugfix] Don't archive announcements if semester isn't successfully closed

### [1.10.2] 2020-12-06
* [bugfix] Prevent blocking quests from being hideable
* [bugfix] Proper counting of hidden quests
* [bugfix] Archived announcement pagination working
* [bugfix] Overlapping announcement menus
* [dev] Refactor contenttypes app/table to hopefully fix several bugs

### [1.10.1] 2020-11-22
* Announcement emails only to current students
* Don't archive draft announcements
* Add archived announcements tab for teachers view
* Don't save draft submission comment if not changed
* [bugfix] Funky announcement menu accordian problem
* [dev] use public CDN instead of local for several resource
* [dev] version css to bust cache when changed

### [1.10.0] 2020-11-17 - AWS
* [dev] Move to AWS

### [1.9.3] 2020-11-08
* Improve announcement menu button
* Enhance select2 widget styling for darktheme
* Semester page updates
* [bugfix] Date format inconsistancies
* [bugfix] Quest approval image cutoff
* [bugfix] Duplicate celery tasks eliminated

### [1.9.2] 2020-10-27
* [bugfix] File upload too big error message
* [bugfix] First nad last names in Profile list
* [bugfix] Prevent active semester from being deleted
* [bugfix] Fix announcement menu button
* [bugfix] Fix Mark Ranges to display properly
* [bugfix] Display announcement date in local time
* [bugfix] Minor styling corrections
* [bugfix] Catch redis connection error during initdb

### [1.9.1] 2020-10-20
* Archive announcements when closing a semester
* Minor styling fixes
* Various optimizations and caching
* [teachers] Only display "all blocks" tab if there is more than one active teacher on the deck
* [bugfix] Reset XP to 0 when a semester is closed
* [dev] Move initial data from migration into initdb command

### [1.9.0] 2020-08-31
* Forgotten password reset by email
* Add public landing page for bytedeck.com
* Remove public portfolio list
* Announcement buttons moved to action menu
* Avatars resized on upload
* Update widgets on several forms
* Add styling options in editor (click styles along the bottom of any large text field to toggle them)
* Paginate notifications list
* Add site config option to not display % mark and calculations page
* Stop messages from dissappearing after a few seconds
* Tweak admin menu
* Regenerate large maps in the background
* [bugfix] Fix broken email sending
* [bugfix] Remove references to GameLab [#609](https://github.com/timberline-secondary/hackerspace/issues/609)
* [dev] Move CI from Travis to Github Actions

### [1.8.0] 2020-08-02
* [bugfux] Various minor bug fixes
* [dev] Refactor django settings to use environment variables
* [security] Upgrade Pillow package due to reports of security vulnerability

### [1.7.1] 2020-07-23
* [bugfix] Handle maps that have had their initial object deleted [#566](https://github.com/timberline-secondary/hackerspace/issues/566)
* [bugfix] Better interlink nodes for maps
* [bugfix] Map zooming on mobile only (messes with scrolling otherwise)
* [bugfix] Remove student number field in profile [#572](https://github.com/timberline-secondary/hackerspace/issues/572)

### [1.7.0] 2020-07-17
* [teachers] Seperate nodes for linked quest maps
* [teachers] Maps are zoomable [#534](https://github.com/timberline-secondary/hackerspace/issues/534)
* [teachers] Repeatable quests are indicated on maps
* [teachers] New links in admin menu
* [bugfix] Remove NOT prereqs from the map [#177](https://github.com/timberline-secondary/hackerspace/issues/177)
* [bugfix] Alternate (OR) prerequisites are now properly connected in maps [#149](https://github.com/timberline-secondary/hackerspace/issues/149)
* [bugfix] Minor formatting tweaks and typos
* [dev] Cache maps for faster loading [#559](https://github.com/timberline-secondary/hackerspace/issues/559)
* [dev] Refactor map styling
* [dev] More efficient quest prereq conditions met caching via celery tasks [#563](https://github.com/timberline-secondary/hackerspace/issues/563)

### [1.6.1] 2020-06-21
* [teachers] Add simple prerequisite quest and/or badge to the main quest form [#543](https://github.com/timberline-secondary/hackerspace/issues/543)
* [bugfix] Broken 'close semester' page [#553](https://github.com/timberline-secondary/hackerspace/issues/553)
* [bugifx] Don't create empty campaigns on import [#538](https://github.com/timberline-secondary/hackerspace/issues/538)
* [bugfix] Form jitter when scrolling [#547](https://github.com/timberline-secondary/hackerspace/issues/547)
* [dev] Better 500 Server error message [#554](https://github.com/timberline-secondary/hackerspace/issues/554)
* [dev] Resolve REDIS warnings in production
* [dev] Install PCRE for uwsgi server [#539](https://github.com/timberline-secondary/hackerspace/issues/532)

### [1.6.0] 2020-06-07
* [dev] Upgrade to Python 3.8
* [dev] Optimize uwsgi [#531](https://github.com/timberline-secondary/hackerspace/issues/531)

### [1.5.0] 2020-06-03
* [teachers] Badge prereqs are now imported
* [teachers] Multiple (simple) prereqs can now be imported between badges and quests
* [bugfix] Badge import_id fixed from 1.4.0
* [dev] Many new tests added

### [1.4.0] 2020-06-01
* [teachers] Badges now have an import ID and can be updated by export/import
* [dev] Default graphics updated to ByteDeck
* Bugfixes:
  - [#532](https://github.com/timberline-secondary/hackerspace/issues/532)
  - [#529](https://github.com/timberline-secondary/hackerspace/issues/529)
  - [#525](https://github.com/timberline-secondary/hackerspace/issues/525)
  - [#522](https://github.com/timberline-secondary/hackerspace/issues/522)
  - [#518](https://github.com/timberline-secondary/hackerspace/issues/518)


### [1.3.1] 2020-05-23
* Bugfixes:
  - [#508](https://github.com/timberline-secondary/hackerspace/issues/508)
  - [#512](https://github.com/timberline-secondary/hackerspace/issues/512)
  - [#517](https://github.com/timberline-secondary/hackerspace/issues/517)
  - [#518](https://github.com/timberline-secondary/hackerspace/issues/518)
  - [#519](https://github.com/timberline-secondary/hackerspace/issues/519)

### [1.3.0] 2020-05-20
* Add lastlogin date/time to student profile
* Asynchronously recalculate after auto-approved quests  (this prevents a large browser delay after submitting an auto-approved quest, with the trade-off that new quests areen't immediately available and will require students to refresh after a few moments)
* Quest map canvas shadow added to define bounds
* [teachers] Notify student's teacher if a non-strudent
* [teachers] Send notification to teacher when comment left on autoapproved quest
* [teachers] Marks Calculations page can be toggled via Site Configuration setting
* [bugfix] Notification does not jump to comment [#471](https://github.com/timberline-secondary/hackerspace/issues/471)
* [bugfix] Summernote widget styling bug [#485](https://github.com/timberline-secondary/hackerspace/issues/485)
* [bugfix] Students can drop quests even if they are set as not visible [#483](https://github.com/timberline-secondary/hackerspace/issues/483)
* [bugfix] Button styling bug [#330](https://github.com/timberline-secondary/hackerspace/issues/330)
* [dev] Many tests added and docker cleanup
* [dev] New tenants come with default data
* [dev] Upgrade project to Python 3.7


### [1.2.1] 2020-04-24
* Clean up menu items and profile options
* Last login date added to student list for teachers
* [bugfix] replying to a flagged comment [#459](https://github.com/timberline-secondary/hackerspace/issues/459)
* [bugfix] fix links in emails [#60](https://github.com/timberline-secondary/hackerspace/issues/460)
* [bugfix] redirect instead of 404 when student tries to start same quest twice [#455](https://github.com/timberline-secondary/hackerspace/issues/455)
* [bugfix] asychronous celery processes and beat scheduling for auto-publishing announcements

### [1.2.0] 2020-04-18
* Require an Access Code to register (this can be set in your Site Configuration and defaults to 314159)
* Bugfixes:
  - [#450](https://github.com/timberline-secondary/hackerspace/issues/450)
  - [#447](https://github.com/timberline-secondary/hackerspace/issues/447)
  - [#437](https://github.com/timberline-secondary/hackerspace/issues/434)
  - [#427](https://github.com/timberline-secondary/hackerspace/issues/427)
  - [#424](https://github.com/timberline-secondary/hackerspace/issues/424)
  - [#422](https://github.com/timberline-secondary/hackerspace/issues/422)
  - [#419](https://github.com/timberline-secondary/hackerspace/issues/419)
  - [#369](https://github.com/timberline-secondary/hackerspace/issues/369)
  - [#402](https://github.com/timberline-secondary/hackerspace/issues/402)
  - [#369](https://github.com/timberline-secondary/hackerspace/issues/369)
  - [#400](https://github.com/timberline-secondary/hackerspace/issues/400)
  - [#395](https://github.com/timberline-secondary/hackerspace/issues/395)
  - [#389](https://github.com/timberline-secondary/hackerspace/issues/389)
  - [#392](https://github.com/timberline-secondary/hackerspace/issues/392)
  - [#395](https://github.com/timberline-secondary/hackerspace/issues/395)
  - [#387](https://github.com/timberline-secondary/hackerspace/issues/387)
  - [#386](https://github.com/timberline-secondary/hackerspace/issues/386)
  - [#383](https://github.com/timberline-secondary/hackerspace/issues/386)
  - [#377](https://github.com/timberline-secondary/hackerspace/issues/377)
  - [#375](https://github.com/timberline-secondary/hackerspace/issues/375)

### [1.1.0] 2020-04-07
* Redirect to login page when accessing via mobile device
* remove some janky/old/unused apps including django-postman (Messages) and Suggestions.
* [dev] Add [CONTRIBUTING.md](https://github.com/timberline-secondary/hackerspace/blob/develop/CONTRIBUTING.md) guidelines for code contributers
* [bugfix] Hotfixes to get production server to play nice

### [1.0.0] 2020-04-05 - Multi tenancy
* Multi-tenant support!
* Bazillians of small bugfixes and tweaks to existing features

### [0.25.1] 2020-03-29
* [bugfix] Use new custom course XP in profiles and chart

### [0.25.0] 2020-03-29
* New personlized maps
* [teachers] New map option: taxi-edges
* [teachers] Max-XP per course (default = 1000)
* [bugfix] Don't allow auto publication of announcements with past date
* [bugfix] Various minor bugfixes

### [0.24.1] 2020-02-27

* [bugfix] Login required for maps
* [bugfix] Proper redirects on login
* [bugfix] License in footer should be GPL 3
* [bugfix] Edit button on flat pages visible for all users
* [bugfix] Removes extra ordinal in last repeat of quest
* [bugfix] Global chillax line setting in config

### [0.24.0] 2020-01-24

* Direct links to comments and announcements
* [teachers] Repeat quests by semester
* [bugfix] Announcement email links
* [bugfix] Attachment margins

### [0.23.0] 2020-01-15

* [teachers] Blocking quests
* [bugfix] Runaway whitespace in quests
* [bugfix] Export quests missing

### [0.22.0] 2020-01-06

* [teachers] Courses can now be used as a prerequisite
* [teachers] Custom favicon
* [teachers] No longer receive notification for quest submissions of non-students (since these now show up in your approvals list anyway)
* [bugfix] Upgrade to Summernote 8.11 fixes list numbering bug (for new lists, old lists will require redoing)
* [bugfix] Sender link in messages fixed [#237](https://github.com/bytedeck/bytedeck/issues/237)
* [bugfix] Many other minor bug fixes
* [dev] Upgrade to Django 2.2 LTS (good till April 2022)

### [0.21.2] 2019-09-16

* Display names instead of student numbers in Messages
* [bugfix] Clear draft text after submission
* Other minor bugfixes and styling tweaks
* [dev] More tests

### [0.21.1] 2019-08-30

* [bugfix] Badge descriptions
* [bugfix] DM email link

### [0.21] 2019-08-29 - Final tweaks before new school year

* Remove individual notifications from dropdown
* Require first and last name for new accounts
* DM headings and emails improved
* [teachers] New config fields for custom text
* [teachers] Reorganize submission buttons
* [teachers] Flag subissions via ajax (no page redirect)
* [bugfix] Broken macro text button on full reply

### [0.20] 2019-08-21 - Custom chillax lines

* DM formatting and attachments
* [teachers] DM options (send to teacher only)
* [teachers] Customizable "chillax lines" with MarkRanges
* [bugfix] Force recalc of available quests when auto-approved
* [bugfix] Various DM bug fixes

### [0.19] 2019-08-11 - The big summer update

* Direct Messaging
* Options to receive notifications and announcements by email
* Badge rarities
* Save draft submissions (60s autosave)
* Badges specific pages
* [teachers] Auto-publish announements
* [dev] Add celery-beat for periodic tasks
* [dev] TravisCI and flake8 linting

### [0.18] 2019-07-23 - Docker

* Increase hidden quest limit
* [dev] Refactor to docker use in development

### [0.17.2] 2019-07-02

* [bugfix] Fixed celery caching errors

#### [0.17.1] 2019-06-26

* [bugfix] Fixed locked tasks

### [0.17.0] 2019-06-26 - Redis Caching

* Add redis db and caching to improve performance

#### [0.16.6a] 2019-05-17 - Upwork optimizations

* Upwork optimization 1

#### [0.16.5] 2019-05-09

* [bugfix] drag-and-drop images duplicate comments

#### [0.16.4] 2019-05-02

* [bugfix] html auto-formatting

#### [0.16.3] 2019-04-23

* styling tweaks in dark theme
* security updates
* [teachers] auto-format html when saved
* [bugfix] clean comments (orphaned li, scripts removed)
* [bugfix] remove old grade field in courses

#### [0.16.2] 2019-04-08

* [bugfix] copying quests error fixed

#### [0.16.1] 2019-03-27

* [bugfix] import quests error fixed

### [0.16.0] 2019-03-27

* [teachers] basic import/export of quests from admin menu

#### [0.15.1] 2019-02-19

* [bugfix] new datetime widgets to replace broken ones

### [0.15.0] 2019-02-19

* Formatted descriptions for portfolios
* Security updates
* [teachers] Fix announcement buttons
* [bugfix] Date and Time widgets on quest creation

#### [0.14.1] 2019-02-14

* [bugfix] Deleted quest causing havoc.
* [code] Basic tests added to several apps

### [0.14.0] 2019-02-09

* Silent mode allows user to turn off gong sounds
* [bugfix] View student numbers in admin

#### [0.13.4] 2019-01-24

* Security updates
* Various styling tweaks and fixes

#### [0.13.3] 2019-01-11

* [bugfix] fix summernote widgets

### [0.13.0]

* [teachers] grant multiple awards at once in full-reply
* [teachers] display XP value of awards when selecting them

#### [0.12.1]

* [code] Django 2.0.x (2.1 still has conflicts with some dependencies)
* [code] Resolve security vulnerabilities in dependencies
* [code] First migrations commit

### [0.12.0] 2018-12-18

* File resource for uploading local videos and zip files.
* [bugfix] quick reply parsing
* [code] Start a better defined branching and release model for code base
* [code] Resolve warnings for django2

### [0.11.0] 2018-05-15 - Math!

* Many mobile tweaks
* Added LaTeX math support
* Quest submenu in top navbar
* [teacher only] Customizable menu links

#### [0.10.2] 2018-06-02 - The mobile device update

* force responsive images in submissions (so large images no longer extend past the content area)
* create mobile menu for notifications
* turn off suggestions
* various mobile layout tweaks
* remove left menu on mobile, added to top menu bar.
* [bugfix] only offer to add valid media to portfolios
* [bugfix] create portfolio when adding if it doesn't exist (instead of error)

#### [0.10.1] 2018-03-06

* new button to access in-progress quests directly (much faster)
* students can view unavailable quests as a preview
* [teacher only] indicator when specific teachers are notified by particular quests
* [bugfix] skipped quests bugging out

### [0.10.0] 2018-02-23 - The Studio Tyee update

* [teacher only] Site name and banner as a configurable setting (support for Studio Tyee)

#### [0.9.1] 2018-02-03

* [teacher only] export data as json (for use with browser extension to upload marks to CIMS)
* [bugifx] comment ban was banning wrong person

### [0.9.0] 2018-01-07

* User custom stylesheets!
* New styling options in text editor (summernote plugins)
* [teacher only] Export of student data for report cards
* [teacher only] Figure styles and packed responsive images (see https://hackerspace.sd72.bc.ca/quests/1058/)
* Add support for <439px displays (phones in portrait modes)
* CSS tweaks for images and lists
* [bugfix] Sort marks properly

### [0.8.0] 2017-10-21

* Students can create and edit quests by turning on the TA flag in their profile
* codemirror formatting when using codeview
* New histogram chart on student XP page
* Added emoji insertion, fontawesome insertion, new semantic formats, and better video insertion
* [teacher only] Grade can now be used as a prerequisite
* [teacher only] Teachers can flag submissions for future follow up
* [teacher only] Teachers can choose to only see quests in their own blocks (default)
* Fullscreen view of quest maps
* Length of displayed Aliases are now limited
* [teacher only] Quests not visible to students now appear in a Drafts tab
* [bugfix] Fix badge granting bugs from Django 1.11
* [bugfix] Repeatable quest bug fixed
* [bugfix] Map creation was showing non-visible quests
* [bugfix] Add manual course XP adjustment to grade calcs
* Other minor tweaks

### [0.7.0] 2017-05-28

* Updated Django to 1.11 LTS (support to 2020)
* Fixed bugs preventing initial migrations when setting up the django app

### [0.6.0]

* Bulk badge granting
* TOC generator for FAQ
* List all dates that badges were granted in profile (as opposed to only the latest one)
* XP Chart formatting tweaks

### [0.5.0] 2017-02-01

* This changelog!
* Archive quests
* XP is now cached so it doesn't recalculate unless a new quest is approve/returned or badge awarded.
* Other minor optimizations to improve page load speeds.
* Changed license to GPL v3.
