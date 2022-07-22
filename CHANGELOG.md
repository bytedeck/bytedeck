
# Hackerspace Changelog
This file chronologically records all notable changes to this website, including new features, tweaks, and bug fixes.

[Changelogs](http://keepachangelog.com/en/0.3.0/) | [Versioning](http://semver.org/) | [Branch model](https://nvie.com/posts/a-successful-git-branching-model/)

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
