/* Apply the student list's group filter as soon as one is picked, instead of making the
 * teacher press the search button afterwards.
 *
 * Progressive enhancement only: the <select> is a plain field inside the same GET form as
 * the search box, so with this script absent (or failed) choosing a group and submitting
 * the form still filters. All this does is save the second click.
 */
document.addEventListener('DOMContentLoaded', function () {
    var filter = document.getElementById('block-filter');
    if (!filter) { return; }  // the list being viewed does not offer the filter
    filter.addEventListener('change', function () {
        filter.form.submit();
    });
});
