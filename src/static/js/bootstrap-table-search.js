/* Let a list table's search find text holding an apostrophe or a double quote (#3007).
 *
 * bootstrap-table reads a table built from the page's markup as each cell's HTML, and searches
 * that HTML for the query after escaping the query with its escapeHTML, which writes ' and " as
 * &#39; and &quot;. In a cell's HTML, though, the browser leaves a text's ' and " as they are:
 * turning text into HTML it escapes only &, < and >. So a query holding either character never
 * matched, and searching for O'Brien found nothing with O'Brien in the list.
 *
 * While such a table searches, this has bootstrap-table escape the query the way the browser
 * escapes a cell's text, so ' and " are compared as they are and &, < and > as before. The rest
 * of the search (which columns are searched, their formatters, the < and > comparisons on
 * numbers, which read the query unescaped) is still bootstrap-table's own.
 *
 * Load it right after bootstrap-table's script, as snippets/bootstrap_table.html does.
 */
(function ($) {
    'use strict';

    var utils = $.fn.bootstrapTable.utils;
    var initSearch = $.BootstrapTable.prototype.initSearch;

    /* Escape text as the browser does when it writes a text node out as HTML.
     *
     * text: the query. Returns it escaped; an empty or missing query comes back as it was, as
     * from bootstrap-table's own escapeHTML.
     */
    function escapeAsText(text) {
        return text ? text.toString().replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') : text;
    }

    /* Filter the table's rows by the search box, as bootstrap-table's initSearch does, with the
     * query escaped as cell text is (see the top of this file).
     */
    $.BootstrapTable.prototype.initSearch = function () {
        if (!this.fromHtml) {
            // A table given its data rather than read from markup holds plain values, which
            // bootstrap-table searches with the query unescaped.
            return initSearch.apply(this, arguments);
        }
        // initSearch reads escapeHTML off the shared utils when it escapes the query. It only
        // filters and sorts the rows, drawing nothing, so the swap can't reach anything put on
        // the page, and it's undone before initSearch returns or throws.
        var escapeHTML = utils.escapeHTML;
        utils.escapeHTML = escapeAsText;
        try {
            return initSearch.apply(this, arguments);
        } finally {
            utils.escapeHTML = escapeHTML;
        }
    };
}(jQuery));
