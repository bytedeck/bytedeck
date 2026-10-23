/* Apply a list's filter as soon as one is picked, instead of leaving the reader to press the
 * search button afterwards (issue #2721 follow-up).
 *
 * Covers the filters that are plain fields in a list's own GET form: the student list drops
 * its {group} filter into the bootstrap-table toolbar (.bt-toolbar-filter), and the quest
 * approvals put theirs beside the search box (.list-search-form). Both submit with the
 * search, so this only saves the second click, and choosing a group still filters with this
 * script absent. A filter that is not in a form narrows the page in the browser instead (the
 * quest status list), and is left to its own script.
 */
document.addEventListener('DOMContentLoaded', function () {
    var filters = document.querySelectorAll('.bt-toolbar-filter select, .list-search-form select');
    Array.prototype.forEach.call(filters, function (filter) {
        if (!filter.form) { return; }
        filter.addEventListener('change', function () {
            filter.form.submit();
        });
    });
});
