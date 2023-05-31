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
$(document).ready(function () {
  // Changed from id selector to class selector to target all tables with the class '.accordian-table'
  var $tables = $('.accordian-table');

  $tables.each(function() {
    var $table = $(this);

    // Initialize the Bootstrap Table
    $table.bootstrapTable();

    $table.on('expand-row.bs.table', function (e, index, row, $detail) {
      var row_html_id = row._id;
      var quest_id = parseInt(row_html_id.match(/\d+$/)[0], 10);

      $detail.html('<div class="detail-container" style="display:none;"></div>');
      var $detailContainer = $detail.find('div');

      // Create a function to update the row's content
      var updateContent = function () {
        var detailContent = $("#collapse-quest-" + quest_id).html();
        $detailContainer.html(detailContent);
      };

      // Update the row's content initially
      updateContent();

      // Create an observer that updates the row's content when the span's content changes
      var observer = new MutationObserver(updateContent);
      observer.observe($("#collapse-quest-" + quest_id)[0], { childList: true, subtree: true });

      // When the row is expanded, slide down the detail container
      $detailContainer.slideDown();
    });

    $table.on("click-row.bs.table", function (e, row, $tr) {
      // If the row is already expanded, collapse it
      if ($tr.next().is('tr.detail-view')) {
        $tr.removeClass('active');
        // send slideUp callback to collapseRow. This causes the currently expanded row to collapse
        $tr.next().find('div.detail-container').slideUp(function () {
          $table.bootstrapTable('collapseRow', $tr.data('index'));
        });
        // If the row is collapsed, expand it
      } else {
        // Collapse all other expanded rows
        $table.find('tr.active').each(function () {
          var $expandedRow = $(this);
          $expandedRow.removeClass('active');
          $expandedRow.next().find('div.detail-container').slideUp(function () {
            $table.bootstrapTable('collapseRow', $expandedRow.data('index'));
          });
        });

        // Expand the row
        $table.bootstrapTable('expandRow', $tr.data('index'));
        // And mark it as expanded
        $tr.addClass('active');
      }
    });
  });
});
