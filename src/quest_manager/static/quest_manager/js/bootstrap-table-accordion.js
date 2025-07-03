/*
  ### COLLAPSABLE QUEST ROWS USING bootstrap-tables (see https://jsfiddle.net/enprogames/cv8f2Lgh/11/) ###

  This block of javascript is responsible for:
    - Initializing the Bootstrap Table
    - Adding the content to the hidden divs
    - Expanding the row when it is clicked
    - Collapsing the row when it is clicked again

    Somewhere else (where?), there is a block of javascript that is responsible for:
    - Adding "active" and "collapse" classes to rows when they are expanded or collapsed

*/


/**
 * ### function loadQuestOrSubmissionContent(id) ###
 * Loads quest or submission content via AJAX and updates the corresponding accordion content container.
 *
 * This function dynamically determines the appropriate AJAX URL based on the current page URL,
 * fetches the corresponding content, and inserts it into the appropriate (accordion) container. It prevents
 * redundant requests by checking if the content has already been loaded.
 *
 * Prerequisites:
 * - `window.contextData` must be defined in the global scope with the following properties:
 *   - `csrfToken`: The CSRF token for secure AJAX requests.
 *   - `ajax_submission_root`: The base URL for fetching submission-related content.
 *   - `ajax_approval_root`: The base URL for fetching approval-related content.
 *   - `ajax_quest_root`: The base URL for fetching quest-related content.
 *
 * @param {number} id - The unique identifier for the quest or submission.
 *
 * Behavior:
 * - Determines the appropriate AJAX URL based on the current page context:
 *   - `/inprogress/` → Fetches an in-progress submission.
 *   - `/completed/` → Fetches a completed submission.
 *   - `/past/` → Fetches a past submission.
 *   - `/approvals/` → Fetches an approval-related submission.
 *   - Otherwise → Fetches quest-related content (available or drafts).
 * - Prevents duplicate AJAX requests by checking if the content has already been loaded.
 * - Updates the corresponding content container (`#preview-quest-{id}` or `#preview-submission-{id}`).
 * - Calls `$('div.pack').pack()` after successful content loading (in case a packing layout needs updating).
 * - Handles errors gracefully by displaying a user-friendly message and logging details to the console.
 */
function loadQuestOrSubmissionContent(id) {
  var $contentContainer = $(`#preview-quest-${id}, #preview-submission-${id}`);

  // If content is already loaded, do nothing
  if ($contentContainer.hasClass("ajax-content-loaded")) return;

  // Determine the correct AJAX URL based on the current page
  var currentURL = window.location.href;
  var ajax_url;

  if (currentURL.includes("/inprogress/")) {
      ajax_url = `${window.contextData.ajax_submission_root}${id}/`;
  } else if (currentURL.includes("/completed/")) {
      ajax_url = `${window.contextData.ajax_submission_root}${id}/completed/`;
  } else if (currentURL.includes("/past/")) {
      ajax_url = `${window.contextData.ajax_submission_root}${id}/past/`;
  } else if (currentURL.includes("/approvals/")) {
      ajax_url = `${window.contextData.ajax_approval_root}${id}/`;
  } else if (currentURL.includes("/library/")) {
      ajax_url = `${window.contextData.ajax_library_root}${id}/`;
  } else {
      ajax_url = `${window.contextData.ajax_quest_root}${id}/`; // Default for available quests or drafts
  }

  // Fetch content via AJAX
  $.ajax({
      type: "POST",
      url: ajax_url,
      data: { csrfmiddlewaretoken: window.contextData.csrfToken },
      success: function (data) {
          $contentContainer.html(data.quest_info_html).addClass("ajax-content-loaded");
          $('div.pack').pack();
      },
      error: function (xhr) {
          $contentContainer.html("<p>Error loading content. Please try again.</p>");
          console.error(xhr.responseText);
      }
  });
}

/**
     * Collapses the provided row, animates the collapse, moves the content back to its original location,
     * and updates the Bootstrap table to reflect the row's collapsed state.
     *
     * @param {JQuery} $expandedRow - The row to collapse. Should be a JQuery object.
     * @param {JQuery} $table - The Bootstrap table in which the row is located. Should be a JQuery object.
     */
function collapseRow($expandedRow, $table) {
  $expandedRow.removeClass('active');
  $expandedRow.next().find('td').addClass('collapsing');
  const $detailViewRow = $expandedRow.next();
  const expanded_row_html_id = $expandedRow.attr("id");
  const expanded_object_id = parseInt(expanded_row_html_id.match(/\d+$/)[0], 10);
  let $expanded_hiddenDIV;
  // find rows matching "collapse-quest-<id>" or "collapse-submission-<id>"
  if (expanded_row_html_id.includes("quest")) {
    $expanded_hiddenDIV = $detailViewRow.find(`#collapse-quest-${expanded_object_id}`);
  } else {
    $expanded_hiddenDIV = $detailViewRow.find(`#collapse-submission-${expanded_object_id}`);
  }

  $expanded_hiddenDIV.slideUp(function() {
    // After animation complete, hide the div and append it back to its original parent
    $expanded_hiddenDIV.hide().appendTo($expanded_hiddenDIV.data('originalParent'));
    $table.bootstrapTable('collapseRow', $expandedRow.data('index'));
  });
}

/**
 * ### function multiKeywordSearch(data, text) ###
 * Custom search handler for Bootstrap Table that supports multiple keywords (in any order).
 *
 * @param {Array} data - Array of row data objects.
 * @param {string} text - The current search query string.
 *
 * @returns {Array} - Filtered row data objects that match all search terms.
 */
function multiKeywordSearch(data, text) {
  const terms = (text || "").toLowerCase().split(/\s+/).filter(Boolean);

  return data.filter(row => {
    // Customize this to search across desired fields
    const searchableText = [
      row.name || "",
      row.campaign || "",
      row.tags || "",
      row.xp || "",
      row.status_icons || "",
    ].join(" ").toLowerCase();

    return terms.every(term => searchableText.includes(term));
  });
}

$(document).ready(function () {
  // class selector to target all tables with the class '.accordian-table'
  const $tables = $('.accordian-table');

  // For each table, initialize the Bootstrap Table and add event listeners for expanding/collapsing rows
  $tables.each(function() {
    const $table = $(this);

    $table.on('expand-row.bs.table', function (e, index, row, $detail) {
      // Get the row's html id, then extract the last digit (quest or submission id) from it
      const row_html_id = row._id;
      const object_id = parseInt(row_html_id.match(/\d+$/)[0], 10);

      // Load the accordion container content via AJAX
      loadQuestOrSubmissionContent(object_id);

      let $hiddenDIV;
      // find elements matching "collapse-quest-<id>" or "collapse-submission-<id>"
      if (row_html_id.includes("quest")) {
        $hiddenDIV = $(`#collapse-quest-${object_id}`);
      } else {
        $hiddenDIV = $(`#collapse-submission-${object_id}`);
      }

      // Save the original parent of the hidden div for later use
      $hiddenDIV.data('originalParent', $hiddenDIV.parent());

      // Move the hidden div into the detail area
      $hiddenDIV.appendTo($detail);

      // Add all classes from the hidden div to the detail element
      $detail.addClass($hiddenDIV.attr('class'));

      // .hide() sets display to none, and slideDown() does animation before setting display to block
      $hiddenDIV.hide().slideDown();
    });

    $table.on('click-row.bs.table', function (e, row, $tr) {
      // If the clicked row is already expanded, collapse it
      if ($tr.next().is('tr.detail-view')) {
        collapseRow($tr, $table);
      // If the clicked row is collapsed, expand it
      } else {
        // Collapse all other expanded rows
        $table.find('tr.active').each(function () {
          const $expandedRow = $(this);
          collapseRow($expandedRow, $table);
        });

        $table.bootstrapTable('expandRow', $tr.data('index'));
        $tr.addClass('active');
      }
    });
  });
});
