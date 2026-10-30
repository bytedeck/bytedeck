// Approval forms, decks with competencies enabled: while any competency is set to the lowest level
// (Emerging), suggest returning the submission instead (see approval_levels.html). It is only a
// suggestion, and approving still works. Delegated from the document, so it reaches every approval
// form on the approvals page, including those the accordion moves into place as rows are expanded.
// Bootstrap's buttons plugin triggers "change" on the radio inside each level button it toggles.
$(document).on('change', '.competency-approval-levels input[type="radio"]', function () {
  var $levels = $(this).closest('.competency-approval-levels');
  var anyLowest = $levels.find('input[type="radio"][value="1"]:checked').length > 0;
  $levels.find('.competency-lowest-nudge').toggleClass('hidden', !anyLowest);
});
