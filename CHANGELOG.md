
# Hackerspace Changelog
This file chronologically records all notable changes to this website, including new features, tweaks, and bug fixes.

[Changelogs](http://keepachangelog.com/en/0.3.0/) | [Versioning](http://semver.org/) | [Branch model](https://nvie.com/posts/a-successful-git-branching-model/)

### [0.22.0] ?

* [teachers] Courses can now be used as a prerequisite
* [bigfix] Upgrade to Summernote 8.11 fixes list numbering bug
* [bugfix] Sender link in messages fixed #237
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
