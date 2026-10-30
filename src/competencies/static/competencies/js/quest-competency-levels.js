// Quest form, decks with competencies enabled: show a default-level picker only for the
// competencies selected in the chips field. Every offered competency has a server-rendered row
// in #quest-competency-levels (see quest_competency_levels.html); this shows the selected rows,
// hides the rest, and hides the whole table while nothing is selected.
$(function () {
  var $select = $('#id_competencies');
  var $levels = $('#quest-competency-levels');
  if (!$select.length || !$levels.length) {
    return;
  }

  function showSelectedLevels() {
    var selected = ($select.val() || []).map(String);
    $levels.find('tr[data-competency-id]').each(function () {
      $(this).toggleClass('hidden', selected.indexOf(String($(this).data('competency-id'))) === -1);
    });
    $levels.toggleClass('hidden', selected.length === 0);
  }

  // select2 triggers "change" on the underlying <select> as chips are added and removed
  $select.on('change', showSelectedLevels);
  showSelectedLevels();
});
