/*
  Unsaved-changes protection (issue #192).

  Opt a form in by adding the `data-warn-unsaved` attribute to its <form> tag.
  If the user edits any field and then tries to leave the page (close the tab,
  hit back, refresh, or follow a link) without submitting, the browser shows its
  native "Leave site? Changes you made may not be saved." confirmation.

  Submitting the form is a deliberate save, so it clears the guard and never warns.
*/
(function () {
  "use strict";

  function guardForm(form) {
    var dirty = false;
    var submitting = false;

    function markDirty() {
      dirty = true;
    }

    // Native controls: text inputs, textareas, selects, checkboxes, radios, etc.
    form.addEventListener("input", markDirty);
    form.addEventListener("change", markDirty);

    // Summernote WYSIWYG editors (used for quest/announcement content) sync to a
    // hidden textarea and emit a bubbling `summernote.change` jQuery event — catch
    // those edits too, since they don't fire a native input/change on the form.
    if (window.jQuery) {
      window.jQuery(form).on("summernote.change", markDirty);
    }

    // A submit is an intentional save — don't warn about it.
    form.addEventListener("submit", function () {
      submitting = true;
    });

    window.addEventListener("beforeunload", function (e) {
      if (dirty && !submitting) {
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
