# Hackerspace Changelog
This file chronologically records all notable changes to this website, including new features, tweaks, and bug fixes.

[Changelogs](http://keepachangelog.com/en/0.3.0/) | [Versioning](http://semver.org/)
## [1.8.0] 2017-10-21
### Added
* Students can create and edit quests by turning on the TA flag in their profile
* codemirror formatting when using codeview
* Grade can now be used as a prerequisite
* Added emoji insertion, fontawesome insertion, new semantic formats, and better video insertion
* Teachers can flag submissions for future follow up
* New histogram chart on student XP page
* Teachers can choose to only see quests in their own blocks (default)
### Changed
* Quests not visible to students now appear in a Drafts tab
* Fullscreen view of quest maps
* Length of displayed Aliases are now limited
* [bugfix] Fix badge granting bugs from Django 1.11
* [bugfix] Repeatable quest bug fixed
* [bugfix] Map creation was showing non-visible quests
* [bugfix] Add manual course XP adjustment to grade calcs
* Other minor tweaks
 

## [1.7.0] 2017-05-28
### Added
* Updated Django to 1.11 LTS (support to 2020)
### Changed
* Fixed bugs preventing initial migrations when setting up the django app

## [1.6.0]
### Added
* Bulk badge granting
* TOC generator for FAQ
### Changed
* List all dates that badges were granted in profile (as opposed to only the latest one)
* XP Chart formatting tweaks

## [1.5.0] 2017-02-01
### Added
* This changelog!
* Archive quests
### Changed
* XP is now cached so it doesn't recalculate unless a new quest is approve/returned or badge awarded.
* Other minor optimizations to improve page load speeds.
* Changed license to GPL v3.
