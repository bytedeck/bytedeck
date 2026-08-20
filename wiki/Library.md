The **Shared Library** is a cross-deck collection of quests and campaigns. Staff on any deck can browse it, import content into their own deck, and share their own content back so other decks can use it.

It is an experimental feature and is turned off on new decks. Everything below is staff-only: students never see the Library, and nothing you import is visible to them until you publish it yourself.

***

## The idea behind it

Reading this first explains most of the behaviour further down.

> **The Library shares complete, ready-to-use packages. Connecting them into your deck is your job.**

A package is a campaign, or a single quest, that stands on its own. What a package cannot carry is the wiring that ties content into one particular deck: badges, ranks, and prerequisites pointing at content that was not part of the package. That wiring is different on every deck, so the deck receiving the package builds it.

This is why imported content always arrives unpublished, why an imported campaign has no prerequisite in front of it, and why the last two steps of every import belong to you. The deck that shared the package could not have done them for you, because their ranks, badges and quests are not yours.

***

## Turning on the Shared Library

The Shared Library is off until someone turns it on, and only the deck **Owner** can turn it on.

1. Open **Admin > Site Configuration**.
2. Scroll to the bottom of the page and click **Advanced** to expand it.
3. Tick **Enable Shared Library**.
4. Click **Update**.

[[/images/library/14-settings-library.png]]

There are two settings here:

* **Enable Shared Library** is the master switch. With it off, the Library does not exist for your deck at all: no sidebar link, no importing, no sharing.
* **Allow staff to export quests to the library** decides who may share *out* of your deck. With it off, only the Owner can share. With it on, any teacher can. It has no effect unless **Enable Shared Library** is also on.

> **Note:** Only the deck Owner can change either setting. Other teachers can read them on this page, but the fields are greyed out.

Once it is on, a **Library** entry appears in the sidebar for staff:

[[/images/library/00-sidebar-library.png]]

***

## Browsing the Library

The Library page has two tabs, **Quests** and **Campaigns**, each showing how many items it holds. The search box searches the whole Library (not just the page you are looking at) and covers quest names, campaign names and tags.

[[/images/library/01-library-quests-tab.png]]

Click any row to expand a preview of that quest, with an **Import Quest** button:

[[/images/library/02-quest-preview.png]]

The **Campaigns** tab lists each campaign with its quest count and total XP. The **Action** column has two buttons: an information button that opens the campaign and every quest in it for reading, and a download button that starts the import.

[[/images/library/05-library-campaigns-tab.png]]

The information button opens the campaign's contents. Expanding a quest there gives you an **Import Quest** button, so you can take a single quest out of a campaign instead of the whole thing.

[[/images/library/18-campaign-detail.png]]

***

## Importing from the Library

Importing **copies** content into your deck. Your copy is yours: editing it never affects the Library's version, and the Library's version never changes underneath you.

### Importing a single quest

1. Open **Library** from the sidebar. The **Quests** tab opens by default.
2. Browse or search, then click a quest to expand its preview.
3. Click **Import Quest**.
4. A confirmation page shows the quest exactly as it will arrive, including its XP, tags and prerequisites. Click the green **Import**.

   [[/images/library/03-import-quest-confirm.png]]

5. You land on your **Drafts** tab, where the quest is waiting.

   [[/images/library/04-import-quest-result.png]]

A quest imported on its own arrives **with no campaign**, even if it belonged to one in the Library. Importing the campaign is what brings the campaign.

### Importing a campaign

Importing a campaign brings every published quest in it, along with the gating between those quests.

1. Open **Library** and go to the **Campaigns** tab.
2. Click the download button in the **Action** column.
3. Confirm on the next page.

   [[/images/library/06-import-campaign-confirm.png]]

4. You land on your **Inactive** campaigns tab, where the campaign is waiting.

   [[/images/library/07-import-campaign-result.png]]

### After you import: the two steps that are yours

Imported content arrives **unpublished** and with **nothing gating it**, on purpose. The message after an import says both of these and links straight to the pages that do them:

1. **Publish it.** A quest arrives in **Drafts**; a campaign arrives under **Inactive**. Students see nothing until you publish.

   > **Note:** For a campaign, use the green publish button on the Campaigns list or the campaign's own page (**Publish Campaign and all its Quests**). Ticking *Published* on the campaign's edit form publishes the campaign only, and leaves its quests as drafts.

2. **Give it a prerequisite.** Nothing arrives gated, so nothing is reachable on your [[quest map|Maps]] yet. Put it behind whatever fits your course: one of your own quests, a badge, a [[rank|Ranks]], or a [[course|Semesters, Groups, and Courses]]. For a campaign, gate its **first** quest; the rest of the campaign unlocks in order behind it, because a campaign's internal gating does travel.

### When your deck already has it

The Library matches content by its **Import ID**, so it always knows which of your quests came from which Library item.

* **A quest you already imported cannot be imported again.** The confirmation page tells you so and links to your copy, and the Import button is disabled. If you want the Library's version back, delete your copy first. If you want a *second* copy, use the **Copy** button on your own quest.

  [[/images/library/16-import-already-have.png]]

* **A campaign you already imported cannot be imported again** either. The page shows your existing campaign and nothing else.
* **Importing a campaign containing quests you already imported individually will overwrite those quests** with the Library's versions. You lose local edits to their text, name, tags and questions. Your own prerequisites on them, and whether you had published them, are kept.

  [[/images/library/15-import-campaign-overwrite-warning.png]]

* **A name clash is handled by renaming, not refusing.** If a different quest on your deck already uses an arriving quest's name, the arriving copy gets today's date added, for example `Photoshop Basics (Imported on 2026-08-19)`. You are told what it was renamed to. Rename it to whatever suits your deck.

***

## What travels, and what does not

### What comes with a quest

* Its name, Quest Details, Submission Instructions and Instructor Notes.
* Its XP, including whether students enter their own XP and the maximum.
* Its icon, and its availability settings: dates and times, repeat settings, hideable, available outside a course, blocking, and map transition.
* Whether it needs teacher verification.
* Its **submission questions**.
* Its **tags**.
* Its **campaign**, when you import a campaign.
* **Prerequisites pointing at other content in the same import.** A campaign's internal gating survives, so its quests still unlock each other in order.

> **Note:** **Instructor Notes travel.** Anything you put there, including answer keys, is readable by staff on every deck that imports the quest. Check that field before you share.

### What stays behind

* **Badges.** Badges never travel. A quest gated behind a badge you created arrives without that gate.
* **Prerequisites pointing outside the package:** a rank, a grade, a block, a course, or a quest that was not part of what was imported.
* **Shared General Info blocks.** A quest that draws its General Info panel from a shared block loses that panel. The sharer is warned about this, so they can paste the text into the quest itself and share again.
* **Who wrote it.** The editor and the "specific teacher to notify" are people on the other deck, so those fields arrive empty.
* **A campaign's left-to-right position on the quest map.** The copy arrives at the default position.
* **Everything about students.** No submissions, marks, comments, XP or badge awards are ever copied. The Library holds content only.

> **Note:** A badge is not part of a quest. "Complete this quest to earn this badge" is a prerequisite that belongs to the **badge**, which is why importing a quest never brings one, and why granting badges for imported work is something you set up on your own deck.

***

## Sharing to the Library

Content you share goes to **every other deck** under the [Creative Commons Attribution-ShareAlike 4.0 licence](https://creativecommons.org/licenses/by-sa/4.0/), and you are asked to agree to that before it is sent.

### Who can share

The deck **Owner** can always share. Other teachers can share only if the Owner has ticked **Allow staff to export quests to the library** in Site Configuration. Students can never share.

### Sharing a quest

1. Open the quest on your deck. In its row of action buttons, click the upload button (**Export this quest to the Library**).

   [[/images/library/08-share-button.png]]

2. The **Export Quest to Library** page shows the licence and the quest as it will be shared.

   [[/images/library/09-share-quest-confirm.png]]

3. Tick the licence agreement and click **Share Quest to Library**.

   [[/images/library/10-share-quest-result.png]]

A quest shared on its own does **not** take its campaign with it. Share the campaign if you want the campaign.

> **Note:** Archived quests cannot be shared. A draft can be shared, and arrives in the Library as a draft.

### Sharing a campaign

1. Open the campaign, or find it in your Campaigns list, and click the upload button (**Export this Campaign to the Library**).

   [[/images/library/11-share-campaign-button.png]]

2. Tick the licence agreement and click **Share Campaign to Library**.

   [[/images/library/12-share-campaign-confirm.png]]

   [[/images/library/13-share-campaign-result.png]]

Sharing a campaign shares its **published, unarchived** quests. Drafts and archived quests stay behind, and you are told by name which archived quests were left out, so you can unarchive them and share again if they should be part of what other decks receive.

The button is disabled on a campaign with no published quests, since there would be nothing to send.

### What happens next

Your content does **not** appear in the Library straight away. It arrives there unpublished, and the people who look after the Library are notified to review it. Once they publish it, other decks can find and import it. That is what the message after a share is telling you.

Your deck's name, your username and the date are recorded alongside it, so other decks can see where the content came from.

### What you will be told

After a share, messages name anything that could not travel, so you hear it from the app rather than from whoever imports it later:

* gating that did not travel, because it pointed at a badge, a rank, a grade, a block, a course, or a quest outside what you shared;
* shared General Info blocks that did not travel;
* archived quests left out of a shared campaign.

None of these stop the share. They are told to you because you are the only person who can still see what is missing and decide whether to widen what you share.

### Sharing something again

A quest or campaign already in the Library **cannot be shared again**. The page tells you it is already there. Sharing an updated version of something already in the Library is not supported yet.

[[/images/library/17-share-already.png]]

Sharing a **new** campaign that happens to contain quests already in the Library is allowed. Those quests are added as separate copies with a name of their own, for example `Photoshop Basics (Exported on 2026-08-19)`, leaving the Library's existing versions untouched.

***

## Known limitations

The Shared Library is marked EXPERIMENTAL for a reason. Things worth knowing before you rely on it:

* **Updates do not flow.** Nothing is shared or imported twice, in either direction, so a fix made on one deck does not reach decks that already imported the quest.
* **Badges are local.** They never travel in either direction. Building badges on top of imported content is deck work.
* **Sharing something whose name is already taken in the Library fails with a server error** rather than a helpful message ([#2531](https://github.com/bytedeck/bytedeck/issues/2531)). Renaming your quest and sharing again works around it.

If you hit something that is not covered here, please say so in the [discussion forum](https://github.com/bytedeck/bytedeck/discussions) (a free GitHub account is needed to post) or [open an issue](https://github.com/bytedeck/bytedeck/issues).
