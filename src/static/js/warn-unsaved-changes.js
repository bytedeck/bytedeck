/*
  Unsaved-changes protection (issue #192).

  Opt a form in by adding the `data-warn-unsaved` attribute to its <form> tag.
  If the user edits any field and then tries to leave the page (close the tab,
  hit back, refresh, or follow a link) without submitting, the browser shows its
  native "Leave site? Changes you made may not be saved." confirmation.

  Submitting the form is a deliberate save, so it clears the guard and never warns.

  A form that is also saved without submitting (the submission page autosaves a
  draft over Ajax) reports those saves through the small API the guard hangs on the
  form element (#2572):

      var sent = form.warnUnsaved.edits();   // before the request leaves
      form.warnUnsaved.saved(sent);          // once the server confirms it

  Passing the count captured before the request is what makes it safe: an edit made
  while the request was in flight leaves the guard armed, because that edit was not
  part of what the server stored. Without the round trip, an autosaved form would
  warn on every exit and students would learn to click straight through it.
*/
(function () {
  "use strict";

  function guardForm(form) {
    // Edits are counted rather than flagged so a save can say which edits it covered.
    var edits = 0;
    var saved = 0;
    var submitting = false;

    function markDirty() {
      edits += 1;
    }

    form.warnUnsaved = {
      edits: function () {
        return edits;
      },
      saved: function (upTo) {
        // Math.max, because two saves can be in flight and land out of order.
        if (typeof upTo === "number") saved = Math.max(saved, upTo);
      }
    };

    // Native controls: text inputs, textareas, selects, checkboxes, radios, etc.
    form.addEventListener("input", markDirty);
    form.addEventListener("change", markDirty);

    // Summernote WYSIWYG editors (used for quest/announcement content) sync to a
    // hidden textarea and emit a bubbling `summernote.change` jQuery event, so catch
    // those edits too, since they don't fire a native input/change on the form.
    if (window.jQuery) {
      window.jQuery(form).on("summernote.change", markDirty);
    }

    // A submit is an intentional save, so don't warn about it.
    form.addEventListener("submit", function () {
      submitting = true;
    });

    window.addEventListener("beforeunload", function (e) {
      if (edits > saved && !submitting) {
        // Setting returnValue is what triggers the native confirmation dialog;
        // modern browsers ignore any custom message and show their own text.
        e.preventDefault();
        e.returnValue = "";
        return "";
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var forms = document.querySelectorAll("form[data-warn-unsaved]");
    Array.prototype.forEach.call(forms, guardForm);
  });
})();
