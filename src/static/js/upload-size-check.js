/* Refuses a file that is too large to upload as soon as it is chosen, before anything is sent
 * (#783).
 *
 * The server can only turn a file away once all of it has arrived, and nginx turns away a whole
 * request over its cap (client_max_body_size) before the app sees it, with a bare "413 Request
 * Entity Too Large" page, or a generic failure where a page uploads in the background. Checking
 * in the browser says what is wrong straight away, next to the file, and sends nothing.
 *
 * Two limits are checked:
 *  - a file input's own, from its data-max-size in bytes, which the upload fields set
 *    (utilities.fields.RestrictedFileFormField) and the editor's image dialog is given;
 *  - what the files chosen in one form may add up to, since they go up together, from the
 *    data-max-request-size on this script's tag (settings.MAX_UPLOAD_REQUEST_SIZE).
 *
 * A file that breaks either is taken back out of its input and a note under the input says why.
 * The input is marked invalid and described by the note, for a screen reader to give the reason.
 * The check listens in the capture phase, ahead of the page's own handlers, so a page that saves
 * a file the moment it is chosen (a submission's draft) never sends it. A form is checked again
 * as it is submitted, for files chosen before this script could see them.
 *
 * The page can load this more than once (each editor on a page asks for it), so it sets itself
 * up only the first time.
 */
window.uploadSizeCheck = window.uploadSizeCheck || (function () {
  "use strict";

  var script = document.currentScript;
  var requestLimit = Number(script && script.dataset.maxRequestSize) || 0;

  /**
   * A size the way the app writes one (Django's filesizeformat): "512 bytes", "500.0 KB", "16.0 MB".
   * @param {number} bytes
   * @returns {string}
   */
  function formatSize(bytes) {
    if (bytes < 1024) {
      return bytes + (bytes === 1 ? " byte" : " bytes");
    }
    var units = ["KB", "MB", "GB", "TB"];
    var value = bytes / 1024;
    var unit = 0;
    while (value >= 1024 && unit < units.length - 1) {
      value /= 1024;
      unit++;
    }
    return value.toFixed(1) + " " + units[unit];
  }

  /**
   * How many bytes the given files come to.
   * @param {File[]} files
   * @returns {number}
   */
  function totalSize(files) {
    return files.reduce(function (total, file) {
      return total + file.size;
    }, 0);
  }

  /**
   * Why these files can't be uploaded, or "" when they can.
   * @param {File[]} files - the files just chosen.
   * @param {number} fileLimit - the most one of them may be, in bytes, or 0 for no limit of its own.
   * @param {number} otherBytes - what the files already chosen elsewhere in the same upload come to.
   * @returns {string}
   */
  function problemWith(files, fileLimit, otherBytes) {
    var tooBig = fileLimit ? files.filter(function (file) { return file.size > fileLimit; }) : [];
    if (tooBig.length === 1) {
      return "“" + tooBig[0].name + "” is " + formatSize(tooBig[0].size) + ", over the " +
        formatSize(fileLimit) + " limit for a file here. Choose a smaller file.";
    }
    if (tooBig.length > 1) {
      return tooBig.length + " of these files are over the " + formatSize(fileLimit) +
        " limit for a file here. Choose smaller files.";
    }
    var total = totalSize(files) + otherBytes;
    if (requestLimit && total > requestLimit) {
      return (otherBytes ? "With the other files chosen here, that comes" : "These files come") + " to " +
        formatSize(total) + ", over the " + formatSize(requestLimit) +
        " that can be uploaded at once. Choose fewer or smaller files.";
    }
    return "";
  }

  /**
   * The files chosen in a file input.
   * @param {HTMLInputElement} input
   * @returns {File[]}
   */
  function filesIn(input) {
    return Array.prototype.slice.call(input.files || []);
  }

  /**
   * What the files chosen in the other file inputs of an input's form come to.
   * @param {HTMLInputElement} input
   * @returns {number}
   */
  function otherBytesInForm(input) {
    if (!input.form) {
      return 0;
    }
    return Array.prototype.reduce.call(input.form.querySelectorAll("input[type=file]"), function (total, other) {
      return other === input ? total : total + totalSize(filesIn(other));
    }, 0);
  }

  /**
   * Where a file input's note goes: in the control the input belongs to. The submission's
   * attachments keep their input in .bt-attachments-add, and any other field sits in its form group.
   * @param {HTMLInputElement} input
   * @returns {HTMLElement}
   */
  function noteHolder(input) {
    return input.closest(".bt-attachments-add, .form-group") || input.parentNode;
  }

  // gives each note an id of its own, for its input to point to
  var notesMade = 0;

  /**
   * A note under a file input saying why its file was refused, red the way the page's own file
   * errors are.
   * @param {HTMLInputElement} input
   * @returns {HTMLElement} the note, already in the page.
   */
  function makeNote(input) {
    var note = document.createElement("p");
    note.id = "upload-size-note-" + (++notesMade);
    note.className = "help-block upload-size-note";
    note.setAttribute("role", "alert");
    // in a span: a help block's own colour wins over text-danger on the same element
    note.appendChild(document.createElement("span")).className = "text-danger";
    noteHolder(input).appendChild(note);
    return note;
  }

  /**
   * Mark a file input as refused, with the note saying why among the things that describe it,
   * so a screen reader gives the reason whenever the input is focused; or take that back off.
   * Descriptions the input already had stay, and an aria-invalid this script didn't set (the
   * server's, for an error on the last submit) is left alone.
   * @param {HTMLInputElement} input
   * @param {string} noteId - the id of the input's note.
   * @param {boolean} refused - whether the input's files were just refused.
   */
  function describe(input, noteId, refused) {
    var ids = (input.getAttribute("aria-describedby") || "").split(/\s+/).filter(function (id) {
      return id && id !== noteId;
    });
    if (refused) {
      ids.push(noteId);
      input.setAttribute("aria-invalid", "true");
      input.dataset.uploadSizeRefused = "true";
    } else if (input.dataset.uploadSizeRefused) {
      input.removeAttribute("aria-invalid");
      delete input.dataset.uploadSizeRefused;
    }
    if (ids.length) {
      input.setAttribute("aria-describedby", ids.join(" "));
    } else {
      input.removeAttribute("aria-describedby");
    }
  }

  /**
   * Take the input's files back out if they can't be uploaded, and say why; clear the note if
   * they can.
   * @param {HTMLInputElement} input
   * @returns {boolean} whether the files were refused.
   */
  function check(input) {
    var problem = problemWith(filesIn(input), Number(input.dataset.maxSize) || 0, otherBytesInForm(input));
    var note = noteHolder(input).querySelector(".upload-size-note");
    if (problem) {
      input.value = "";
      note = note || makeNote(input);
      note.firstChild.textContent = problem;
      describe(input, note.id, true);
      return true;
    }
    if (note) {
      describe(input, note.id, false);
      note.remove();
    }
    return false;
  }

  document.addEventListener("change", function (event) {
    var input = event.target;
    if (!(input instanceof HTMLInputElement) || input.type !== "file") {
      return;
    }
    if (check(input)) {
      // the page's own handlers would upload what was just taken out, or report an empty choice
      event.stopImmediatePropagation();
    }
  }, true);

  document.addEventListener("submit", function (event) {
    var refused = false;
    Array.prototype.forEach.call(event.target.querySelectorAll("input[type=file]"), function (input) {
      refused = check(input) || refused;
    });
    if (refused) {
      // nothing goes up, and handlers such as the double-submission guard don't run either
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);

  return {formatSize: formatSize, problemWith: problemWith, requestLimit: requestLimit};
})();
