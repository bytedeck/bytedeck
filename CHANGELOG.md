
# Bytedeck Changelog
This file chronologically records all notable changes to this website, including new features, tweaks, and bug fixes.

[Changelogs](http://keepachangelog.com/en/0.3.0/) | [Versioning](http://semver.org/) | [Branch model](https://nvie.com/posts/a-successful-git-branching-model/)

### [1.34.0] 2026-08-27 Claude VI
* New Features:
  - **You are warned before leaving a submission with unsaved text.** A student's draft saves on a timer, about once a minute, so clicking a navbar link, pressing back, or closing the tab in between silently threw away everything typed since the last save. The submission page now asks first, the same prompt a quest or announcement form already gives, and it stops asking once a draft save has gone through, so the ordinary autosave does not leave you arguing with a dialog. The staff question editor gets the same protection [#2572](https://github.com/bytedeck/bytedeck/issues/2572)
* Tweaks:
  - The **Move up/down** arrows on a quest's Submission Questions panel now appear only on the Questions page, where they reorder in place. Everywhere else the panel shows (a quest's detail page, a submission you are marking, the Library's Share Quest confirmation) clicking one did move the question, then threw you onto the Questions page: you lost your place, and on the share page the licence box you had just ticked [#2568](https://github.com/bytedeck/bytedeck/issues/2568)
  - Long-answer and file-upload answer boxes now say which question they belong to. A student using a screen reader on a quest with three file questions heard "Attach files" three times with nothing to tell them apart, and a long-answer editor announced no label at all, while the short answers beside them announced their question number [#2570](https://github.com/bytedeck/bytedeck/issues/2570)
  - The Questions page help now says how often a draft really saves (about once a minute, plus the **Save Draft** button) instead of "as they type", which promised a student more than it delivered [#2571](https://github.com/bytedeck/bytedeck/issues/2571)
* Bugfixes:
  - **A student could answer a file question with a file that runs their code when you open it.** File answers were accepted on the media type the browser declared, which is whatever the uploader says it is, and SVG and HTML were on the accepted list to begin with; opening one ran the student's script inside your session, as you. Those types are now refused unless the question asks for them: a file question has an **Also allow file types that can carry a script** tick box, off by default, and where it is on the answer is handed over as a download instead of opened in the page. An SVG answer is still shown as a picture, which is the one way a browser will not run it, so a graphic design answer can be marked at a glance. What is stored decides this, so an answer cannot get its direct link back by having its question edited or deleted afterwards [#2559](https://github.com/bytedeck/bytedeck/issues/2559)
  - **The quest map drew campaigns on top of each other.** On a map where one campaign leads into two parallel ones, those two columns were drawn over each other for their whole height: each column's quest names were clipped by the other column's boxes, and one campaign's name ended up buried between them. It happened on decks that had never touched a campaign's **Map order**, so there was nothing to set differently to avoid it [#2627](https://github.com/bytedeck/bytedeck/issues/2627)
  - **The quest and campaign lists came back in no order you could account for.** Campaign lists had stopped sorting altogether and arrived in whatever order the database happened to return, and the quest tabs had never sorted by name: they led with whichever quests carried an expiry date, ordered by that date, which is not a column the table shows. Campaign lists are alphabetical again, and a quest tab is ordered by your own **Sort order** first, then expired quests, then by name, with the heading marked so the list says what it is sorted by [#2623](https://github.com/bytedeck/bytedeck/issues/2623) [#2624](https://github.com/bytedeck/bytedeck/issues/2624)
* Codebase:
  - Em dashes are out of the submission-questions app's copy, docstrings and comments, and a test now reports any that come back [#2569](https://github.com/bytedeck/bytedeck/issues/2569)


### [1.33.0] 2026-08-26 Claude V
* New Features:
  - **Searching and sorting now cover the whole list, not just the page in front of you.** The approvals and submissions tabs and the Shared Library's quest list are paginated, but their search box and sortable column headings only ever worked on the rows your browser happened to be holding. Typing a student's name into an approvals queue of two hundred reported nothing found while their submission sat on page four, which reads as "this student has nothing waiting"; clicking a column heading told you which of the thirty rows on screen came in first, while looking like it had found the oldest submission in the queue. Both now run over every matching row before the page is cut from it, and clicking a sorted column again reverses it. Each tab searches what its own columns show: the approvals tabs match a student's username, their preferred name, and the first and last name behind it, so you can type whichever you know, and the submissions tabs match campaign and tags [#2597](https://github.com/bytedeck/bytedeck/issues/2597) [#2582](https://github.com/bytedeck/bytedeck/issues/2582) [#2410](https://github.com/bytedeck/bytedeck/issues/2410)
  - **The quest tabs are paginated.** Available, drafts and archived were sent whole, so a deck with a few hundred quests built every one of them into a single table on every request. They now arrive a page at a time, with the same search box, sortable headings and pagination controls the Library and submission tabs already use [#2598](https://github.com/bytedeck/bytedeck/issues/2598)
  - **Keep your own version of a quest when you import a campaign.** Importing a campaign overwrote every quest your deck already had, so the only way to protect local edits was to not import the campaign at all. Each quest you already hold now gets a **Keep my version** tick box on the import page: tick it and your copy is left exactly as it is, while still joining the campaign you are importing [#1845](https://github.com/bytedeck/bytedeck/issues/1845)
  - **The searchable icon picker now covers badge types, badge rarities and custom menu items.** Last release put it on ranks; the same Font Awesome picker, with a live preview and toggles for rotate, flip, spin and pulse, now replaces typing class names from memory on those three forms too [#2469](https://github.com/bytedeck/bytedeck/issues/2469)
* Bugfixes:
  - **Several ways of losing a student's work while a draft saved, all closed.** A draft save that landed just after the student pressed submit could quietly turn an answer they had handed in back into an unsubmitted one. A file chosen while a save was already in flight was discarded when that save came back. A custom XP value was thrown away entirely, so a student who set their XP, saw "Draft saved", and came back the next day found the quest's default in the box again. And a single failed save (a brief wifi drop was enough) stopped every later autosave and every click of **Save Draft** for as long as the page stayed open, silently, with nothing to say why: draft saving now reports the failure beside the button and tries again on the next tick [#2565](https://github.com/bytedeck/bytedeck/issues/2565) [#2563](https://github.com/bytedeck/bytedeck/issues/2563) [#2562](https://github.com/bytedeck/bytedeck/issues/2562) [#2561](https://github.com/bytedeck/bytedeck/issues/2561)
  - **A quest could be handed in with nothing in it.** The editor never sends an empty box: click into one and press enter or space and it sends markup that only looks empty. A required long-answer question accepted that as an answer, and an empty comment box satisfied the "you must attach something or comment" rule, so a quest could be completed with no content at all and the marker was left looking at a blank cell with nothing to say the student had skipped it. Teachers were also being notified about comments that turn out to be blank [#2560](https://github.com/bytedeck/bytedeck/issues/2560) [#2609](https://github.com/bytedeck/bytedeck/issues/2609)
  - **The rich-text editors vanished when a submission was sent back for a correction.** If a submission failed validation, the page came back with no editors at all: every answer box and the comment box became a plain text area showing the student their own answer as raw markup, with no formatting tools and no way to paste an image, at exactly the moment they were being asked to fix something [#2608](https://github.com/bytedeck/bytedeck/issues/2608)
  - **Re-importing a shared quest could re-label answers students had already given.** Questions were matched by their position in the quest, but reordering a question swaps positions, so once the author of a shared quest reordered its questions, a re-import overwrote the wrong row: every answer already submitted silently became an answer to a different question [#2566](https://github.com/bytedeck/bytedeck/issues/2566)
  - **Fifteen Font Awesome icons left their ranks with no icon at all.** A migration that split rank icons into a name plus its modifiers misread any icon whose name begins with `fa-li`, `fa-spin` or `fa-stack` (`fa-list`, `fa-space-shuttle` and thirteen others) as a modifier with no name, and a rank with no icon name renders nothing. Those ranks have their icons back [#2600](https://github.com/bytedeck/bytedeck/issues/2600)
  - **Email from a deck could arrive with a malformed sender.** The deck's name was wrapped around a configured sender that already carried a display name of its own, so the From line nested one inside the other [#2602](https://github.com/bytedeck/bytedeck/issues/2602)
* Codebase:
  - Draft answer rows that nothing could ever reach are no longer created, and existing ones are cleaned up: saving a file on an already finished submission used to create an empty answer row per question (undoing the cleanup a skipped quest had just performed), and deleting a question left its unpublished answers behind for good, along with an uploaded file of up to 16 MiB [#2567](https://github.com/bytedeck/bytedeck/issues/2567)
  - Every save receiver that reads other rows now sits out fixture loading, as Django requires: two of the project's twenty-seven honoured that, and several of the rest would not merely fail but compute a wrong answer and store it, including one that recalculates a student's cached XP and mark [#2548](https://github.com/bytedeck/bytedeck/issues/2548)
  - Test names in the tenant and library apps now say which class or method they exercise, so a failure in CI leads back to the code under test [#2591](https://github.com/bytedeck/bytedeck/issues/2591) [#2592](https://github.com/bytedeck/bytedeck/issues/2592)
* Devops:
  - A deck whose subscription renews on its own is now told that it renews, instead of being sent up to five "renew or lose access" emails and shown a warning banner about a date on which it loses nothing. Decks that really are expiring get a trimmed cadence of 30, 14, 7 and 1 days, and a cancelled deck in Maintenance is no longer told it will never expire [#2586](https://github.com/bytedeck/bytedeck/issues/2586) [#2591](https://github.com/bytedeck/bytedeck/issues/2591)


### [1.32.0] 2026-08-23 Claude IV
* New Features:
  - **A deck can now run more than one semester at once, and progress is tracked per course.** A student can be enrolled in several courses across different open semesters at the same time; their XP, rank, and progress chart are now kept and shown separately for each course (a multicourse student sees their rank in every course and a chart per course), and the XP from a submission is attributed to the course it was earned in. When you join a course you're told which group and semester you're joining; archiving now archives one named semester rather than "the open one"; and a deck's student count spans every open semester [#2157](https://github.com/bytedeck/bytedeck/issues/2157) [#2179](https://github.com/bytedeck/bytedeck/issues/2179) [#2440](https://github.com/bytedeck/bytedeck/issues/2440) [#2453](https://github.com/bytedeck/bytedeck/issues/2453)
  - **Per-quest submission questions are now live for students.** A quest can ask its own questions when a student hands it in: short-answer text with a stated character limit and a live count as they type, and file, image, video, and audio uploads that display right on the submission page and are kept when a draft is saved or a submission fails validation. Staff add and reorder a quest's questions from a **Manage Questions** button on the quest edit form (drag to reorder, no page reload), and a quest's questions travel with it through the Shared Library [#1304](https://github.com/bytedeck/bytedeck/issues/1304) [#2216](https://github.com/bytedeck/bytedeck/issues/2216) [#2172](https://github.com/bytedeck/bytedeck/issues/2172) [#2401](https://github.com/bytedeck/bytedeck/issues/2401) [#2482](https://github.com/bytedeck/bytedeck/issues/2482) [#1459](https://github.com/bytedeck/bytedeck/issues/1459)
  - **The Shared Library is far more capable, and safer to share into.** Its quest list is now paginated and searchable; imported content is attributed to who shared it and which deck it came from (the attribution its licence asks for); and the import screen tells you what to do next. A quest whose name clashes on import can be renamed instead of refused, a push to the Library is all-or-nothing, and a quest's submission questions and a prerequisite's full condition (including invert, count, and the OR alternative) now carry across. Before you share, you're warned about anything that will not travel with the content, such as a campaign's General Info block or an OR-alternative prerequisite [#2377](https://github.com/bytedeck/bytedeck/issues/2377) [#2379](https://github.com/bytedeck/bytedeck/issues/2379) [#2364](https://github.com/bytedeck/bytedeck/issues/2364) [#2162](https://github.com/bytedeck/bytedeck/issues/2162) [#2163](https://github.com/bytedeck/bytedeck/issues/2163) [#2398](https://github.com/bytedeck/bytedeck/issues/2398) [#2535](https://github.com/bytedeck/bytedeck/issues/2535)
  - **Sign out in a single click** from the navbar; the extra confirmation page is gone [#2444](https://github.com/bytedeck/bytedeck/issues/2444)
  - **A searchable icon picker for ranks.** The rank form's icon field is now a searchable Font Awesome picker with a live preview, plus toggle buttons for rotate, flip, spin, and pulse, instead of typing class names from memory [#2468](https://github.com/bytedeck/bytedeck/issues/2468)
  - **A course can run on XP alone, with no percentage mark** [#403](https://github.com/bytedeck/bytedeck/issues/403)
  - **Staff are notified in-app when a new version reaches production**, so a deck's teachers see that something changed without checking elsewhere [#2316](https://github.com/bytedeck/bytedeck/issues/2316)
* Tweaks:
  - Action-button tooltips and popovers now initialize across the whole site, so the hover hints on the submission and badge buttons show up consistently [#2166](https://github.com/bytedeck/bytedeck/issues/2166)
  - A mark that is not a number now explains what it means and where it comes from, instead of showing a confusing value [#2486](https://github.com/bytedeck/bytedeck/issues/2486)
* Bugfixes:
  - **A security-hardening pass across the app.** Closed a cross-deck data exposure where a POST parameter could choose which deck's schema a request ran against (letting a signed-in user read another deck's shared content); an open redirect through a notification's redirect target; several missing permission checks (Shared Library views, the content-export endpoints, and completing or previewing a submission that is not yours); and stored cross-site-scripting vectors where a crafted name or flash message was rendered as HTML (flash messages, and the names a notification mentions, are now escaped). Views that change state now require POST [#2304](https://github.com/bytedeck/bytedeck/issues/2304) [#2340](https://github.com/bytedeck/bytedeck/issues/2340) [#2362](https://github.com/bytedeck/bytedeck/issues/2362) [#2363](https://github.com/bytedeck/bytedeck/issues/2363) [#2368](https://github.com/bytedeck/bytedeck/issues/2368) [#2383](https://github.com/bytedeck/bytedeck/issues/2383) [#2167](https://github.com/bytedeck/bytedeck/issues/2167) [#2498](https://github.com/bytedeck/bytedeck/issues/2498) [#2511](https://github.com/bytedeck/bytedeck/issues/2511)
  - One student's rejected email address could abort a deck's entire notification digest; a single rejection no longer stops the rest of the batch [#2510](https://github.com/bytedeck/bytedeck/issues/2510)
  - Comment attachments were dropped when a submission failed validation; they are now kept [#2427](https://github.com/bytedeck/bytedeck/issues/2427)
  - Creating an internal system account no longer sends a spurious "new account" notification [#2320](https://github.com/bytedeck/bytedeck/issues/2320)
  - Uploaded audio and video answers are recognised by every name a recording goes by, so they display reliably [#2492](https://github.com/bytedeck/bytedeck/issues/2492)
* Codebase:
  - Continued the push toward "100% of the code we intend to test," answering long-standing test TODOs and asserting what endpoints actually do rather than only that they redirect [#2296](https://github.com/bytedeck/bytedeck/issues/2296) [#2306](https://github.com/bytedeck/bytedeck/issues/2306)
  - Modernized the Docker and Compose setup, de-hardcoded the production CloudFront domain, gave the Shared Library its own quest serialization and copied content directly between schemas, and filled in the library app's docstrings [#2260](https://github.com/bytedeck/bytedeck/issues/2260) [#2173](https://github.com/bytedeck/bytedeck/issues/2173) [#2378](https://github.com/bytedeck/bytedeck/issues/2378) [#2445](https://github.com/bytedeck/bytedeck/issues/2445) [#2513](https://github.com/bytedeck/bytedeck/issues/2513)
  - Performance: a student's per-course XP and progress chart are computed in a single pass, and the comments list prefetches what its template reads [#2459](https://github.com/bytedeck/bytedeck/issues/2459) [#2168](https://github.com/bytedeck/bytedeck/issues/2168)
  - Routine dependency updates, including Django 5.2.17 (the latest 5.2 LTS security fixes), django-tenants, django-allauth, Stripe, numpy, ruff, and pre-commit [#2339](https://github.com/bytedeck/bytedeck/issues/2339)
  - Refined the repository's Claude Code session conventions in CLAUDE.md [#2466](https://github.com/bytedeck/bytedeck/issues/2466) [#2472](https://github.com/bytedeck/bytedeck/issues/2472) [#2515](https://github.com/bytedeck/bytedeck/issues/2515) [#2517](https://github.com/bytedeck/bytedeck/issues/2517)
* Devops:
  - Continued billing and subscription refinements since the last release: the tenant admin's deck list gains a sortable **Subscription** status column; an expired deck is sent to Stripe checkout instead of a dead-end billing portal; the deck is named on every Stripe page and in platform emails; platform emails now carry the ByteDeck wordmark rather than the deck's own logo; a suspended deck is no longer warned about its seat limit; and each deck's Stripe portal configuration is stored on the deck itself [#2319](https://github.com/bytedeck/bytedeck/issues/2319) [#2326](https://github.com/bytedeck/bytedeck/issues/2326) [#2328](https://github.com/bytedeck/bytedeck/issues/2328) [#2331](https://github.com/bytedeck/bytedeck/issues/2331) [#2332](https://github.com/bytedeck/bytedeck/issues/2332) [#2336](https://github.com/bytedeck/bytedeck/issues/2336) [#2338](https://github.com/bytedeck/bytedeck/issues/2338) [#2504](https://github.com/bytedeck/bytedeck/issues/2504)
  - A deck owner can now request deletion of their own deck [#2505](https://github.com/bytedeck/bytedeck/issues/2505)
  - Deploy builds pull fresh base images, and worker and Redis memory are bounded, with a switch for the September scale-up [#2345](https://github.com/bytedeck/bytedeck/issues/2345) [#2082](https://github.com/bytedeck/bytedeck/issues/2082)
  - The automated changelog announcement posts only a release's not-yet-announced sections to GitHub Discussions [#2305](https://github.com/bytedeck/bytedeck/issues/2305)


### [1.31.0] 2026-08-09 Claude III
* New Features:
  - **Archive students instead of deleting them.** A student's profile page now leads with an **Archive** button in place of the old one-click **Delete**: archiving deactivates the student (they can no longer log in and drop off the active lists) instead of permanently removing them and all of their work. An archived student's profile then offers **Restore** (reactivate) and **Delete**, so a permanent delete is now a deliberate second step rather than the default. Archived students appear under the existing **Inactive** tab of the student list [#2182](https://github.com/bytedeck/bytedeck/issues/2182)
  - **You're warned before losing unsaved form changes.** If you edit a quest, badge, or other form and try to navigate away or close the tab before saving, the browser now prompts you first so a stray click doesn't discard your work [#192](https://github.com/bytedeck/bytedeck/issues/192)
  - **Clearer semester management for staff.** Staff now see a banner when the current semester has ended or none is open (prompting you to open one), archiving a semester goes through a confirmation page, semester state changes happen through buttons rather than plain links (so they can't fire by accident), and the semester list gains a status column [#1177](https://github.com/bytedeck/bytedeck/issues/1177) [#2157](https://github.com/bytedeck/bytedeck/issues/2157)
* Tweaks:
  - The "Please verify your email address" reminder shown at login now includes an actionable **Re-send verification link** instead of being plain text you couldn't act on [#2233](https://github.com/bytedeck/bytedeck/issues/2233)
  - Opening the submission form for a quest that is no longer available now shows an explanatory notice instead of an empty form [#798](https://github.com/bytedeck/bytedeck/issues/798)
  - Campaign **Map order** now also orders connected campaigns on the quest map (and lays them out more compactly) [#1977](https://github.com/bytedeck/bytedeck/issues/1977)
* Bugfixes:
  - First-level bullets in comment lists rendered as hollow circles instead of solid dots; they now show the correct markers [#1388](https://github.com/bytedeck/bytedeck/issues/1388)
  - Anchor links to headings on custom pages scrolled the target up under the fixed top navbar; they now land below it [#821](https://github.com/bytedeck/bytedeck/issues/821)
  - A submission returned to a student after a new semester had started stayed attached to the old (closed) semester; returned submissions now move to the active semester [#1231](https://github.com/bytedeck/bytedeck/issues/1231)
  - The previous release's fix for wrapping campaign names on quest maps wasn't reaching users because the map scripts were cached; those scripts are now cache-busted so the fix applies [#1289](https://github.com/bytedeck/bytedeck/issues/1289)
* Codebase:
  - Vendored the remaining front-end libraries locally (Font Awesome 4.7, KaTeX, Chart.js, the select2-bootstrap theme, bootstrap-table) instead of loading them from third-party CDNs, put version numbers in the vendored filenames, and removed several dead or unused stylesheet/script loads [#2105](https://github.com/bytedeck/bytedeck/issues/2105) [#2129](https://github.com/bytedeck/bytedeck/issues/2129) [#2143](https://github.com/bytedeck/bytedeck/issues/2143) [#2236](https://github.com/bytedeck/bytedeck/issues/2236) [#2240](https://github.com/bytedeck/bytedeck/issues/2240) [#2245](https://github.com/bytedeck/bytedeck/issues/2245) [#2246](https://github.com/bytedeck/bytedeck/issues/2246) [#2250](https://github.com/bytedeck/bytedeck/issues/2250)
  - Scale groundwork for large September decks: bounded the admin quest/badge exports, moved the current-XP recalculation and "regenerate all maps" onto background tasks, and rejected an unbounded "all quests" AJAX branch [#2081](https://github.com/bytedeck/bytedeck/issues/2081) [#2160](https://github.com/bytedeck/bytedeck/issues/2160) [#2177](https://github.com/bytedeck/bytedeck/issues/2177) [#2188](https://github.com/bytedeck/bytedeck/issues/2188) [#2191](https://github.com/bytedeck/bytedeck/issues/2191)
  - Continued groundwork for **per-quest submission questions**: wired into the quest submission flow, with staff UI to add and reorder a quest's questions and to copy them when a quest is copied (still being rolled out) [#1304](https://github.com/bytedeck/bytedeck/issues/1304) [#2161](https://github.com/bytedeck/bytedeck/issues/2161)
  - Continued the push toward full test coverage across many modules (with the explicit-exclusion policy), removed dead code (the disabled 2015 intro tour, `Profile.chillax()`) and fixed a latent `num_hidden` bug found along the way, and took routine dependency updates [#2107](https://github.com/bytedeck/bytedeck/issues/2107) [#2127](https://github.com/bytedeck/bytedeck/issues/2127) [#2141](https://github.com/bytedeck/bytedeck/issues/2141) [#2144](https://github.com/bytedeck/bytedeck/issues/2144) [#2151](https://github.com/bytedeck/bytedeck/issues/2151) [#2155](https://github.com/bytedeck/bytedeck/issues/2155) [#2176](https://github.com/bytedeck/bytedeck/issues/2176) [#2198](https://github.com/bytedeck/bytedeck/issues/2198) [#2215](https://github.com/bytedeck/bytedeck/issues/2215) [#2226](https://github.com/bytedeck/bytedeck/issues/2226) [#2229](https://github.com/bytedeck/bytedeck/issues/2229) [#2247](https://github.com/bytedeck/bytedeck/issues/2247) [#2274](https://github.com/bytedeck/bytedeck/issues/2274) [#2281](https://github.com/bytedeck/bytedeck/issues/2281) [#2285](https://github.com/bytedeck/bytedeck/issues/2285)
* Devops:
  - Continued rollout of automated deck **billing and subscriptions** (Stripe), still gated to report-only by default while it is validated: Stripe changes now flow back into each deck automatically through a verified webhook, backed by a nightly reconcile and a manual "Sync from Stripe" admin action, so renewals, cancellations, payment failures, and plan changes keep a deck's status current; a failed payment emails the deck owner; Stripe customers are labelled with their deck; and a live-testing bug that capped manually-managed decks at the 5-student trial limit (ignoring their admin-set cap) is fixed [#1731](https://github.com/bytedeck/bytedeck/issues/1731) [#2110](https://github.com/bytedeck/bytedeck/issues/2110) [#2300](https://github.com/bytedeck/bytedeck/issues/2300) [#2301](https://github.com/bytedeck/bytedeck/issues/2301)
  - Continued the deck **lifecycle / suspension** redesign that governs the trial and subscription clocks: lapsed trials get the same 30-day grace period as subscriptions, a deck keeps its remaining free trial time through Stripe checkout, only the deck owner can sign in to a suspended deck, a suspension automatically closes the deck's open semester, and a deletion clock is keyed to the suspension date and first warning [#1734](https://github.com/bytedeck/bytedeck/issues/1734) [#2210](https://github.com/bytedeck/bytedeck/issues/2210) [#2224](https://github.com/bytedeck/bytedeck/issues/2224) [#2262](https://github.com/bytedeck/bytedeck/issues/2262) [#2277](https://github.com/bytedeck/bytedeck/issues/2277) [#2279](https://github.com/bytedeck/bytedeck/issues/2279) [#2284](https://github.com/bytedeck/bytedeck/issues/2284)
  - The deck owner's **Subscription details** page now names the plan and its renewal terms after the Subscribed badge (for example "Bytedeck Subscription - 40 Students, renewed annually at $75.00 per year"), shows the manage button at the top as well as the bottom, and limits managing the subscription to the deck owner (other staff see it disabled). "Contact ByteDeck" text now links to contact@bytedeck.com [#1733](https://github.com/bytedeck/bytedeck/issues/1733) [#2308](https://github.com/bytedeck/bytedeck/issues/2308)
  - In-app **deck subscription notices** now name their governing date and link to the subscription page (for example "this deck's free trial ends on Aug. 15, 2026 (7 days left)", or the seat usage for a limit warning), instead of a bare label with no link [#1733](https://github.com/bytedeck/bytedeck/issues/1733) [#2290](https://github.com/bytedeck/bytedeck/issues/2290)
  - **Deploys are gentler:** during an update, nginx serves a branded "we'll be right back" maintenance page (a proper 503 with a Retry-After hint) instead of a raw 502, follows the web container's current address instead of caching a stale one, and prunes stale Docker images and build cache first so a deploy can't fill the host disk [#2313](https://github.com/bytedeck/bytedeck/issues/2313) [#2299](https://github.com/bytedeck/bytedeck/issues/2299) [#2298](https://github.com/bytedeck/bytedeck/issues/2298)
  - Project operators can now **verify a deck owner's email** and **change a deck's owner** directly from the tenant admin (with command-line equivalents), and admin **deletion of an inactive deck** now guards on a year of inactivity before dropping its schema. Some dead Tenant fields were removed (a no-op "max quests" and two deprecated owner fields), and the admin's per-deck **Quest count** now reflects the available quest pool (published, in-date, not archived) rather than counting drafts and expired quests [#2044](https://github.com/bytedeck/bytedeck/issues/2044) [#2314](https://github.com/bytedeck/bytedeck/issues/2314) [#2315](https://github.com/bytedeck/bytedeck/issues/2315)
  - The public **deck-request flow** (starting at `/decks/request/`) now walks a visitor through the whole process (verify email, emailed credentials, trial terms with a pricing link, and a demo-deck preview) instead of a bare email form. Its verification and welcome emails are sent as properly formatted, branded messages (they previously arrived as a single unformatted line), the welcome greeting falls back to the username when no name is set, platform emails carry the ByteDeck wordmark in their signature, and new deck names are capped at 30 characters [#2291](https://github.com/bytedeck/bytedeck/issues/2291) [#2292](https://github.com/bytedeck/bytedeck/issues/2292)
  - Changelog releases now **post to GitHub Discussions automatically** when a new version reaches production, replacing the manual announcement step [#2294](https://github.com/bytedeck/bytedeck/issues/2294)


### [1.30.0] 2026-08-01 Claude II
* New Features:
  - **Repeatable quests now show when they'll be available again.** Completing a repeatable quest that has a cooldown used to make it silently vanish from the Available tab; it now appears in an "Available again soon" section at the top of that tab with a live countdown of when it returns (each entry links to the quest), and trying to start a quest you already have in progress now tells you to finish that one first [#57](https://github.com/bytedeck/bytedeck/issues/57)
  - **TAs can copy a quest after starting it.** A "Copy" button now appears on a quest's submission preview (the In Progress / Completed / Past Courses accordion) and on its full submission page, next to Drop and Continue. Previously a TA could only copy from the Available list, so once you started a quest and it became a submission you lost the option; copying creates a new draft quest using this one as a template, with the original set as its prerequisite [#141](https://github.com/bytedeck/bytedeck/issues/141)
  - **Per-quest quick reply for grading.** Save canned feedback for a quest's common mistakes in a new "Quick Reply Text" field on the quest edit form; when approving or returning a submission of that quest, a quest-specific quick-reply button inserts it into your response, right beside the existing site-wide one [#161](https://github.com/bytedeck/bytedeck/issues/161)
* Tweaks:
  - The quest **Completion Statuses** page gains a status-filter dropdown, a scope toggle (blocks you teach / all enrolled this semester / all active), a Completed column that sorts by approval date, and a three-group status breakdown with counts and percentages [#1973](https://github.com/bytedeck/bytedeck/issues/1973)
  - Refined the badge **"grant to everyone who qualifies"** flow: a single clear info banner (instead of a grey box with duplicated text), only students currently enrolled in a course are scanned (staff and test accounts excluded), and the badge action buttons are tidied into "Manage" and "Grant" groups that wrap cleanly [#2061](https://github.com/bytedeck/bytedeck/issues/2061)
  - Pushing a quest or campaign to the **Shared Library** now emails Library staff that content is awaiting review (with a review link), and your confirmation message explains it won't appear in the Library until an admin publishes it [#1949](https://github.com/bytedeck/bytedeck/issues/1949)
* Bugfixes:
  - A campaign's **Map order** field had no effect on the quest map — setting it left campaigns in the same left-to-right position; campaigns now actually sort left-to-right by Map order (lowest first) [#1977](https://github.com/bytedeck/bytedeck/issues/1977)
  - With **no semester open**, a student could still "join a course" and get silently attached to a closed semester; the join page now tells them no semester is open and registers nothing, and teachers get a warning banner linking to the semesters page to open one [#2060](https://github.com/bytedeck/bytedeck/issues/2060)
  - Bulleted lists in submission/approval previews and the announcements list rendered as hollow sub-bullet circles instead of solid dots (a side effect of Bootstrap list-groups); they now show the correct markers [#811](https://github.com/bytedeck/bytedeck/issues/811)
  - Loading tables (quest and badge lists) no longer visibly jump when their spinner disappears — the spinner hides and the finished table reveals in the same step [#1981](https://github.com/bytedeck/bytedeck/issues/1981)
* Codebase:
  - Vendored the LMS's core **Bootstrap and jQuery locally** (served from static files instead of two third-party CDNs) and upgraded Bootstrap 3.3.7 → 3.4.1, patching several known XSS vulnerabilities [#2095](https://github.com/bytedeck/bytedeck/issues/2095)
  - Pushed test coverage toward "100% of the code we intend to test" across many modules, adopted an explicit coverage-exclusion policy so the number stays meaningful, and tidied earlier coverage-PR test files; along the way fixed a latent crash in the prerequisite `get_ids()` helper [#2065](https://github.com/bytedeck/bytedeck/issues/2065) [#2071](https://github.com/bytedeck/bytedeck/issues/2071) [#2072](https://github.com/bytedeck/bytedeck/issues/2072) [#2076](https://github.com/bytedeck/bytedeck/issues/2076) [#2078](https://github.com/bytedeck/bytedeck/issues/2078) [#2084](https://github.com/bytedeck/bytedeck/issues/2084) [#2088](https://github.com/bytedeck/bytedeck/issues/2088) [#2091](https://github.com/bytedeck/bytedeck/issues/2091) [#2093](https://github.com/bytedeck/bytedeck/issues/2093) [#2094](https://github.com/bytedeck/bytedeck/issues/2094) [#2096](https://github.com/bytedeck/bytedeck/issues/2096) [#2097](https://github.com/bytedeck/bytedeck/issues/2097) [#2100](https://github.com/bytedeck/bytedeck/issues/2100) [#2102](https://github.com/bytedeck/bytedeck/issues/2102) [#2104](https://github.com/bytedeck/bytedeck/issues/2104)
  - Groundwork for **per-quest submission questions**: a new, default-off `questions` app (models + staff CRUD) that isn't wired into the student submission or marking flow yet, so nothing changes for decks for now [#1304](https://github.com/bytedeck/bytedeck/issues/1304)
  - Finished Python 3.12 tooling loose ends (pyupgrade `--py312-plus`, a `.python-version` pin) and fixed `quest_manager`'s AppConfig discovery (`app.py` → `apps.py`) so its startup signal wiring is explicit [#2052](https://github.com/bytedeck/bytedeck/issues/2052) [#2063](https://github.com/bytedeck/bytedeck/issues/2063)
* Devops:
  - Rollout of automated deck **billing / trial / subscription** (mostly disabled by default while it's validated in report-only mode): derived per-deck trial/subscription/grace status with corrected active-user counts; a nightly cross-schema status refresh replacing an expensive per-page recompute; a subscription **status banner** (trial / expiring / over-limit / suspended) and enforcement of **active-student seat caps** at course registration; automated owner **expiry/limit/suspension reminders**; and a new staff **"Subscription details"** page with Stripe checkout and billing-portal management. Wording throughout now distinguishes "current" (registered this semester, counted toward the cap) from "active" students [#1729](https://github.com/bytedeck/bytedeck/issues/1729) [#1730](https://github.com/bytedeck/bytedeck/issues/1730) [#1731](https://github.com/bytedeck/bytedeck/issues/1731) [#1733](https://github.com/bytedeck/bytedeck/issues/1733)
  - Production and staging now emit leveled, timestamped logs to stdout, and each Docker service's log files are size-capped and rotated so a runaway process can't fill the host disk [#2027](https://github.com/bytedeck/bytedeck/issues/2027)


### [1.29.0] 2026-07-21 Claude I
* New Features:
  - **Grant a badge to everyone who qualifies, on demand.** When you change a badge's prerequisites, you're now asked whether to check for students who newly qualify. Say yes and a confirmation page shows how many students would receive it; confirm and it's granted to all of them at once (their teachers are notified). Because it only runs when you ask, a badge is never handed out while you're still setting up its prerequisites [#1925](https://github.com/bytedeck/bytedeck/issues/1925)
  - **New "Completion Statuses" button on a quest.** Opens a page listing every student's status on that quest — In Progress, Returned, Submitted, Approved, etc. — so you can see at a glance where each student is [#1934](https://github.com/bytedeck/bytedeck/issues/1934)
  - **Order campaigns left-to-right on quest maps.** Edit a campaign and set its "Map order" field; campaigns with a lower number sit further to the left on the map [#1977](https://github.com/bytedeck/bytedeck/issues/1977)
* Tweaks:
  - YouTube (and other) video embeds load again [#1896](https://github.com/bytedeck/bytedeck/issues/1896)
  - Data tables now show a loading spinner instead of a flash of unstyled/blank table while they load [#1981](https://github.com/bytedeck/bytedeck/issues/1981)
  - Campaign quests stay vertically stacked on quest maps, and long campaign names no longer wrap [#1787](https://github.com/bytedeck/bytedeck/issues/1787) [#1289](https://github.com/bytedeck/bytedeck/issues/1289)
  - Campaign publishing: clearer redirects, a publish button on the campaign list, and distinct icons [#1931](https://github.com/bytedeck/bytedeck/issues/1931)
  - A quest can no longer be set to both "unlimited repeats" and "repeat per semester" — pick one [#1531](https://github.com/bytedeck/bytedeck/issues/1531)
  - Removed the student-facing quick reply form [#1886](https://github.com/bytedeck/bytedeck/issues/1886)
* Bugfixes:
  - The sidebar "Quest Approvals" button opened the wrong approvals tab; it now opens Submitted [#1895](https://github.com/bytedeck/bytedeck/issues/1895)
  - HTML typed into a comment was rendered as-is, so a crafted comment could run script for anyone who viewed it (stored XSS); comment text is now fully escaped [#1343](https://github.com/bytedeck/bytedeck/issues/1343)
  - Racing/double-clicking "Start Quest" could create two submissions and award XP twice; starting the same quest twice at once no longer double-grants [#1964](https://github.com/bytedeck/bytedeck/issues/1964)
  - Editing your profile email could error out (500) when the network's DNS lookup of the email's domain failed; validation now tolerates those lookup failures [#1976](https://github.com/bytedeck/bytedeck/issues/1976)
  - A notification preview with more than one image spliced the images together and broke the notifications dropdown; multi-image previews now render correctly [#1761](https://github.com/bytedeck/bytedeck/issues/1761)
  - Unpublished campaigns showed a blank value after "Published:"; it now reads correctly [#1930](https://github.com/bytedeck/bytedeck/issues/1930)
  - Checkboxes on the prerequisites form were misaligned and overlapping; the layout is fixed [#1978](https://github.com/bytedeck/bytedeck/issues/1978)
  - The badge action-button row wrapped awkwardly and its status button pointed at the wrong place; both are fixed [#1988](https://github.com/bytedeck/bytedeck/issues/1988)
  - A semester with a missing start or end date crashed the pages that display it; those are now guarded [#912](https://github.com/bytedeck/bytedeck/issues/912)
* Codebase:
  - Upgraded to Django 5.2 LTS and Python 3.12, with a dependency-modernization pass [#2015](https://github.com/bytedeck/bytedeck/issues/2015) [#2017](https://github.com/bytedeck/bytedeck/issues/2017) [#1916](https://github.com/bytedeck/bytedeck/issues/1916)
  - Test suite ~6–8× faster, brought up to conventions, and broadly expanded; linting moved from flake8 to ruff [#1997](https://github.com/bytedeck/bytedeck/issues/1997) [#2026](https://github.com/bytedeck/bytedeck/issues/2026) [#1993](https://github.com/bytedeck/bytedeck/issues/1993)
  - Reduced N+1 queries across the campaign, tag, mark-chart, and notification pages [#1940](https://github.com/bytedeck/bytedeck/issues/1940) [#1941](https://github.com/bytedeck/bytedeck/issues/1941) [#1942](https://github.com/bytedeck/bytedeck/issues/1942) [#1943](https://github.com/bytedeck/bytedeck/issues/1943)
  - Internal correctness/perf: prerequisite-cache uniqueness and skip-on-user-delete, XP-cache overflow, GFK choice caching, no-op prereq saves, comments `full_clean()` [#520](https://github.com/bytedeck/bytedeck/issues/520) [#1754](https://github.com/bytedeck/bytedeck/issues/1754) [#2035](https://github.com/bytedeck/bytedeck/issues/2035) [#1967](https://github.com/bytedeck/bytedeck/issues/1967) [#1989](https://github.com/bytedeck/bytedeck/issues/1989) [#2006](https://github.com/bytedeck/bytedeck/issues/2006)
* Devops:
  - Automated production/staging deploys via self-hosted runners (gated on green CI), self-hosted Redis, persistent DB connections, a templated nginx config, and ops-reliability/CI improvements [#1962](https://github.com/bytedeck/bytedeck/issues/1962) [#1954](https://github.com/bytedeck/bytedeck/issues/1954) [#1965](https://github.com/bytedeck/bytedeck/issues/1965) [#1950](https://github.com/bytedeck/bytedeck/issues/1950) [#2003](https://github.com/bytedeck/bytedeck/issues/2003) [#2004](https://github.com/bytedeck/bytedeck/issues/2004)
  - Public-site deck requests (visitors start at `/decks/request/`): the flow now ends on a confirmation page explaining the next steps, and requesting a deck with a very long name no longer crashes deck creation [#1946](https://github.com/bytedeck/bytedeck/issues/1946) [#1948](https://github.com/bytedeck/bytedeck/issues/1948)


### [1.28.0] 2026-07-12 Marcus III
* Deck Requests:
  - [New Feature] New decks can now be requested directly from the public ByteDeck site instead of by contacting us. Visitors fill in a short reCAPTCHA-protected form (name and email), click the verification link emailed to them (valid for one hour, good for one deck), and are guided through creating their own deck. The new deck's owner then receives a welcome email with their initial login credentials [#1892](https://github.com/bytedeck/bytedeck/issues/1892) [#1903](https://github.com/bytedeck/bytedeck/issues/1903)
  - [Tweak] New deck owners now receive a secure random initial password (generated once and emailed) instead of a guessable one, and deck-request verification links are opaque single-use nonces that keep the requester's name and email out of the URL [#1903](https://github.com/bytedeck/bytedeck/issues/1903)
  - [Bugfix] Creating a new deck no longer silently fails to set up the deck owner's account (the setup ran in the wrong database schema, which made it a no-op in production), and verification / welcome emails are now sent in the background so the signup pages don't hang while mail goes out [#1903](https://github.com/bytedeck/bytedeck/issues/1903)
  - [Bugfix] Fixed two more errors when creating a deck through the request form: a deck name longer than 20 characters no longer aborts setup at the database, and completing the request no longer fails with a "SessionInterrupted" error after the deck has already been created [#1938](https://github.com/bytedeck/bytedeck/issues/1938)
  - [Bugfix] Links in deck-request verification, welcome, and account email-confirmation messages now use https:// instead of http:// [#1939](https://github.com/bytedeck/bytedeck/issues/1939)
* Library:
  - [New Feature] Campaigns can now be exported to the shared Library: a new export button on the campaign detail page (enabled once the campaign has published quests) leads to a confirmation page that lists all of the campaign's quests and flags any that already exist in the Library [#1849](https://github.com/bytedeck/bytedeck/issues/1849) [#1850](https://github.com/bytedeck/bytedeck/issues/1850)
  - [New Feature] Exporting a campaign whose quests already exist in the Library now copies those quests into the exported campaign instead of blocking the export, so a campaign can be exported even when every quest in it is already in the Library [#1884](https://github.com/bytedeck/bytedeck/issues/1884)
  - [Tweak] When importing a single quest that already exists on your deck, the confirmation page now shows a prominent red warning explaining that overwriting existing quests individually is not yet supported. (Previously the notice was easy to miss and contradicted the campaign-import message, which says existing quests get overwritten.) [#1876](https://github.com/bytedeck/bytedeck/issues/1876) [#1878](https://github.com/bytedeck/bytedeck/issues/1878)
  - [Bugfix] Importing from the Library now also checks your archived quests for duplicates, so you can no longer end up with a second copy of a quest you had archived [#1877](https://github.com/bytedeck/bytedeck/issues/1877)
  - [Bugfix] Export-to-Library options are no longer offered while browsing the shared Library deck itself [#1888](https://github.com/bytedeck/bytedeck/issues/1888)
* Campaigns:
  - [New Feature] Publish a campaign and all of the quests inside it in one click with the new publish button on the campaign detail page, instead of publishing each quest one at a time. (Handy before exporting to the Library, since only campaigns with published quests can be exported.) [#1843](https://github.com/bytedeck/bytedeck/issues/1843)
  - [Tweak] The campaign detail, campaign delete, and badge-type delete pages now show the reason something can't be deleted in a red alert well, instead of only in a tooltip on the disabled delete button [#1861](https://github.com/bytedeck/bytedeck/issues/1861)
* Quests:
  - [New Feature] New "Student Statuses" page for teachers: a new button among a quest's action buttons opens a table showing every student's status on that quest — including students who haven't started it — with links to their submissions [#918](https://github.com/bytedeck/bytedeck/issues/918)
  - [Bugfix] Archived quests can now be deleted directly — the delete page previously returned "Not Found" for them, forcing you to unarchive first [#1874](https://github.com/bytedeck/bytedeck/issues/1874)
* Tweaks:
  - Search on the Approvals tab now also matches the Group, User, and Status columns, so it behaves the same as search on the other submission tables [#1875](https://github.com/bytedeck/bytedeck/issues/1875)
* Refactor/Optimizations:
  - Django 5.2 preparation: removed APIs dropped between Django 4.2 and 5.2, and fixed two broken unpinned dependencies (namegenerator, redis-py) [#1897](https://github.com/bytedeck/bytedeck/issues/1897)
  - Eliminated the worst N+1 query patterns across approvals, badge lists, profile pages, the campaigns list, badge detail, ranks list, and popover counts [#1898](https://github.com/bytedeck/bytedeck/issues/1898)
  - Further N+1 reductions on the profile detail page and the notifications list [#1902](https://github.com/bytedeck/bytedeck/issues/1902)
  - Hardened rank and rarity caches against signal-less ORM writes [#1898](https://github.com/bytedeck/bytedeck/issues/1898)
* Bugfixes:
  - Maps no longer draw connections for inverted ("NOT") OR-prerequisites: the exclude-NOT option was silently ignored for the OR slot of a prerequisite, so a map could include quests whose only link was a NOT condition [#1900](https://github.com/bytedeck/bytedeck/issues/1900) [#1901](https://github.com/bytedeck/bytedeck/issues/1901)
* Devops:
  - Fixed the randomly-flaky CI failures in the prerequisites signal tests (`Rank.DoesNotExist` and missing-map errors):
    - Tests that create `Prereq` objects now use deterministic content types instead of random ones [#1899](https://github.com/bytedeck/bytedeck/issues/1899)
    - A custom test runner gives `baker.make(Prereq)` valid generic-foreign-key targets, so it can no longer fabricate dangling prereqs that crash the map-generation signal [#1903](https://github.com/bytedeck/bytedeck/issues/1903)
    - `PrerequisitesSignalsTest.test_on_quest_badge_save_with_rank_prereq__creation` now wraps its `baker.make` in `captureOnCommitCallbacks(execute=True)` so the map-generation signal can't fire before its Rank is committed (direct commit [7a070fd](https://github.com/bytedeck/bytedeck/commit/7a070fd), no PR)


### [1.27.0] 2025-08-15 Marcus II
* New Features:
  - New quest tab for Archived quests [#1800](https://github.com/bytedeck/bytedeck/issues/1800) and full rework of process for Archiving quests [#1846](https://github.com/bytedeck/bytedeck/issues/1846)
  - New Detail view for Campaigns [#1794](https://github.com/bytedeck/bytedeck/issues/1794)
  - "Returned" tab for teachers renamed to "In Progress" and includes all in-progress quests as well as returned, with returned quests sorted at the top by default [#1820](https://github.com/bytedeck/bytedeck/issues/1820)
  - Ability to import full Campaigns [#1842](https://github.com/bytedeck/bytedeck/issues/1842) [#1833](https://github.com/bytedeck/bytedeck/issues/1833)
  - Ability to export individual quests to the Library [#1860](https://github.com/bytedeck/bytedeck/issues/1860) and [#1848](https://github.com/bytedeck/bytedeck/issues/1848)
  - Option to Bulk Edit quests from the quest list (bulk editing options are context dependant to which tab you are on) [#1758](https://github.com/bytedeck/bytedeck/issues/1758)
* Tweaks:
  - Rearrange Library menu items [#1806](https://github.com/bytedeck/bytedeck/issues/1806)
  - Link to quests in Library import message [#1830](https://github.com/bytedeck/bytedeck/issues/1830)
  - Improve consistancy between Badge and Quest detail pages [#1821](https://github.com/bytedeck/bytedeck/issues/1821)
  - Trigger regeneration of a map when the Map form is updated.
  - Only allow deletion of a CCmapign if it has no quests [#1824](https://github.com/bytedeck/bytedeck/issues/1824)
  - Auto-increment date and copy label when adding new excluded dates to a Semester [#1419](https://github.com/bytedeck/bytedeck/issues/1419)
* Refactor/Optimizations:
  - Rename Quest's `visible_to_students` field and Badge and Category/Campaign `active` fields all to `published` consistancy accross models [#1818](https://github.com/bytedeck/bytedeck/issues/1818) and [#1839](https://github.com/bytedeck/bytedeck/issues/1839)
* Bugfixes:
  - Campaign import filter so only campaigns with published quests appear [#1812](https://github.com/bytedeck/bytedeck/issues/1812)
  - Fix campaign info displayed in the Library [#1801](https://github.com/bytedeck/bytedeck/issues/1801)
  - Fix number of quests/campaigns shown on Library tabs [#1829](https://github.com/bytedeck/bytedeck/issues/1829)
  - Check if quest already exists in Archived quests before importing it from Library [#1834](https://github.com/bytedeck/bytedeck/issues/1834)
  - Importing a single quest within a campaign no longer imports the campaign as well [#1810](https://github.com/bytedeck/bytedeck/issues/1810)
  - Another attempt to fix auto-linkification of urls within lists [#1826](https://github.com/bytedeck/bytedeck/issues/1826)
* Devops:
  - Library views converted to CBV [#1813](https://github.com/bytedeck/bytedeck/issues/1813)
  - Fiddle with build and tests automation [#1869](https://github.com/bytedeck/bytedeck/issues/1869), [#1868](https://github.com/bytedeck/bytedeck/issues/1868), [#1870](https://github.com/bytedeck/bytedeck/issues/1870)


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
  - Add rate limit 429 error page [#1766](https://github.com/bytedeck/bytedeck/issues/1766)
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
