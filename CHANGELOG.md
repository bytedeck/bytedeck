
# Hackerspace Changelog
This file chronologically records all notable changes to this website, including new features, tweaks, and bug fixes.

[Changelogs](http://keepachangelog.com/en/0.3.0/) | [Versioning](http://semver.org/) | [Branch model](https://nvie.com/posts/a-successful-git-branching-model/)

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
