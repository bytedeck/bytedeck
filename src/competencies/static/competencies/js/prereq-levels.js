/*
  The advanced prerequisites form, on decks with competencies enabled: where a row's element is a
  competency, its count is the minimum level, so the number box is swapped for a picker of the deck's
  levels. The picker writes the chosen level back into the hidden number box, which is what's posted.
  The levels and the competency content type come from the competency_prereq_levels template tag.
*/
(function () {
  var data = JSON.parse(document.getElementById('competency-prereq-levels').textContent);
  var competencyType = String(data.content_type_id);

  // the row's count box for an element select: "...-0-prereq_object" -> "...-0-prereq_count"
  function countBoxFor(select) {
    return document.querySelector('input[name="' + select.name.replace(/prereq_object$/, 'prereq_count') + '"]');
  }

  function isLevel(value) {
    return data.levels.some(function (level) { return String(level[0]) === String(value); });
  }

  // chosen: the teacher has just picked this row's element, rather than the page loading a saved row
  function sync(select, chosen) {
    var box = countBoxFor(select);
    if (!box) {
      return;
    }
    var picker = box.parentNode.querySelector('select.competency-prereq-level');
    if ((select.value || '').split('-')[0] !== competencyType) {
      if (picker) {
        picker.remove();
        box.classList.remove('hidden');
      }
      return;
    }
    if (!picker) {
      picker = document.createElement('select');
      picker.className = 'form-control competency-prereq-level';
      picker.title = 'The minimum level: met once the student is at this level or higher';
      data.levels.forEach(function (level) {
        var option = document.createElement('option');
        option.value = level[0];
        option.textContent = level[1];
        picker.appendChild(option);
      });
      picker.addEventListener('change', function () { box.value = picker.value; });
      box.parentNode.insertBefore(picker, box.nextSibling);
      // a row just switched to a competency starts on the usual target level, not on the count of 1
      // the form starts every row with
      if (chosen) {
        box.value = data.default_level;
      }
    }
    if (!isLevel(box.value)) {
      box.value = data.default_level;
    }
    picker.value = box.value;
    box.classList.add('hidden');
  }

  // select2 fires the original select's change event, for rows added later too
  $(document).on('change', 'select[name$="prereq_object"]', function () { sync(this, true); });
  $('select[name$="prereq_object"]').each(function () { sync(this); });
})();
