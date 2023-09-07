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

$(document).ready(function () {
  // class selector to target all tables with the class '.accordian-table'
  const $tables = $('.accordian-table');

  // For each table, initialize the Bootstrap Table and add event listeners for expanding/collapsing rows
  $tables.each(function() {
    const $table = $(this);

    // Initialize the Bootstrap Table
    $table.bootstrapTable();

    $table.on('expand-row.bs.table', function (e, index, row, $detail) {
      // Get the row's html id, then extract the last digit (quest or submission id) from it
      const row_html_id = row._id;
      const object_id = parseInt(row_html_id.match(/\d+$/)[0], 10);
      let $hiddenDIV;
      // find elements matching "collapse-quest-<id>" or "collapse-submission-<id>"
      if (row_html_id.includes("quest")) {
        $hiddenDIV = $(`#collapse-quest-${object_id}`);
      } else {
        $hiddenDIV = $(`#collapse-submission-${object_id}`);
      }

      // Save the original parent of the hidden div for later use
      $hiddenDIV.data('originalParent', $hiddenDIV.parent());

      // The primary change is here: instead of copying the content, we're moving it
      $hiddenDIV.appendTo($detail);

      // Add all classes from the hidden div to the detail element
      $detail.addClass($hiddenDIV.attr('class'));

      // Start animation for expanding
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
