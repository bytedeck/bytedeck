# The editor's Summernote plugins

Every plugin the rich text editor loads is here, one folder each. The editor is Summernote 0.8.20
with Bootstrap 3 (`django-summernote` 0.8.20). `bytedeck_summernote/config.py` lists the plugins in
the order both kinds of editor load them, and puts their buttons in the toolbar and in the menus
over a clicked image, link or table.

Gathered here in #2913, so the plugins live with the editor and could be split out into a repo of
their own one day without a rewrite.

## Rules for a plugin

* **It doesn't reach into ByteDeck.** What a plugin needs from the app comes in as a Summernote
  option, as `uploadImages` does for image-source (handed over in
  `bytedeck_summernote/templates/bytedeck_summernote/widget_common.html`).
* **What it saves is a contract.** A plugin's classes and tags are stored in quests, comments and
  submissions. Its section below lists them. They have to get through the HTML sanitizer
  (`bytedeck_summernote/settings.py`), and a class that isn't Bootstrap's needs styling on every
  page that shows content (`css/custom_common.css`), not only in the editor. Renaming one would
  change how content already saved looks.
* **A new plugin** goes in a folder of its own here, in `PLUGINS` in `config.py`, and in this
  README, with where it came from. `bytedeck_summernote/tests/test_config.py` checks that every
  folder here is loaded and described.

## The plugins

Each section says what the plugin adds, what it saves into content, what it needs from the app,
and where it came from. "Origin not recorded" means the file doesn't name its source; the commit
it was added in is the earliest record.

### add-text-tags

The **Additional text styles** dropdown in the toolbar's font group (`add-text-tags`): wraps the
selection in `code`, `kbd`, `var`, `mark`, `small`, `ins` or `del`.

* Saves: those tags, which the sanitizer allows (#1340).
* Origin not recorded. Added in a87d43afd (2017).

### faicon

The **Icon** toolbar button (`faicon`): inserts a Font Awesome 4.7 icon,
`<i class="fa fa-...">`.

* Saves: Font Awesome 4.7's `fa` classes, styled by Font Awesome's stylesheet on every page.
* Needs: the icon list `window.faIcons` from `js/fa_icons_4.7.0.js`, shared with the icon picker on
  other forms (`utilities/fa_icon_widget.py`).
* Origin not recorded. Added in 5de4b2c6a (2017). Changed in a2fd981ab (where the icon is
  inserted) and 1f8375534 (#2468, reads the shared icon list instead of its own copy).

### image-align

**Align left**, **Align center** and **Align right** in the image's menu (`imageAlignLeft`,
`imageAlignCenter`, `imageAlignRight`): put an image on a line of its own. It also takes over
Summernote's float buttons, so an image is either aligned or floated, never both.

* Saves: Bootstrap 3's `center-block`, and `img-align-right`, styled in `css/custom_common.css`.
* ByteDeck's own (#2910).

### image-link

**Link** and **Unlink** in the image's menu (`imageLink`, `imageUnlink`): the `<a>` wraps the
`<img>`. While an image is selected it also takes over the toolbar's Link button, and the image's
menu shows the link's URL.

* Saves: an `<a>` around the image.
* ByteDeck's own (#2909).

### image-shapes

**Image Shapes** in the image's menu (`imageShapes`): Bootstrap 3's image classes (Responsive,
Rounded, Circle and Thumbnail). An image is inserted Responsive.

* Saves: Bootstrap 3's `img-*` classes.
* Origin: https://github.com/DiemenDesign/summernote-image-shapes. Added in 4ae6b8f08 (2017).
  Changed in 1f4d72f59 (#268, #2800), 244c6f4ac (the menu ticks and changes the image's shapes)
  and b78244706 (#2906, a new image starts out Responsive).

### image-source

**Edit image** in the image's menu (`imageSource`): changes the picture an image shows, by upload
or URL, and its description (alt text), keeping the rest of the image.

* Saves: the image's `src` and `alt`.
* Needs: the `uploadImages` option, the editor's own image upload; without it the dialog offers
  the URL alone.
* ByteDeck's own (#2907, #2911).

### keep-caret

No button: keeps the caret where it was while the toolbar is used, so the editor doesn't jump
(#2734).

* ByteDeck's own (#2734).

### list-styles

The **List Styles** dropdown in the toolbar's paragraph group (`listStyles`): a list's numbering
or bullets (decimal, letters, Roman numerals, disc, circle, square), and spaced lists.

* Saves: an inline `list-style-type` on the list, and the `list-spaced` class, styled in
  `css/custom_common.css`.
* Origin: https://github.com/tylerecouture/summernote-lists. Added in 33b868819 (2017). Changed in
  b255b079e, cac9f8a67 and 54d39431a (spaced lists).

### math

The **Insert Math** toolbar button (`math`): a formula typed in LaTeX, drawn by KaTeX.

* Saves: KaTeX's HTML in a `span.note-math`, with the LaTeX in a `span.note-latex` inside it, which
  `css/custom_common.css` hides on every page (#2874).
* Needs: KaTeX (`katex/`), and `js/note-math.js`, which draws stored formulas again on every page.
  The iframe editor loads both itself.
* Origin not recorded. Added in 628050cbe (2018).

### table-headers

**Toggle table header** in the table's menu (`tableHeaders`): turns the table's first row into a
header row, or back.

* Saves: a `thead` with `th` cells.
* Origin: https://github.com/tylerecouture/summernote-lists. Added in cac9f8a67 (2018).

### table-styles

**Table style** in the table's menu (`tableStyles`): Bootstrap 3's table classes.

* Saves: `table-striped`, `table-bordered`, `table-condensed` and `table-hover`.
* Origin: https://github.com/tylerecouture/summernote-lists. Added in cac9f8a67 (2018).

### video-attributes

The **Embed Video** toolbar button (`videoAttributes`): embeds a video from its link, with its size,
autoplay, loop, controls, and start and end times (#1556).

* Saves: an `iframe` or `video`, which the sanitizer allows.
* Origin not recorded. Added in 132cdad87 (2017). Changed in 7b2b40fae (where the video is
  inserted) and 2fc38c1d0 (#1556, start and end times).
