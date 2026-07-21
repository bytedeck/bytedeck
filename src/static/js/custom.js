// https://github.com/wenzhixin/bootstrap-table-examples/blob/master/issues/337.html
// http://jsfiddle.net/djhvscf/e3nk137y/1619/
window.icons = {
    refresh: 'fa-refresh',
    toggle: 'fa-toggle-on',
    columns: 'fa-th-list'
};

$(document).ready(function() {

    /* off-canvas sidebar toggle */
    $('[data-toggle=offcanvas]').click(function() {
    $(this).toggleClass('visible-xs text-center');
    $(this).find('i').toggleClass('fa-chevron-right fa-chevron-left');
    $('.row-offcanvas').toggleClass('active');
    $('.sidebar-menu').toggleClass('hidden-xs').toggleClass('visible-xs');
    $('.xs-sidebar-menu').toggleClass('visible-xs').toggleClass('hidden-xs');

    // $('#lg-menu').toggleClass('hidden-xs').toggleClass('visible-xs');
    // $('#lg-menu-staff').toggleClass('hidden-xs').toggleClass('visible-xs');
    // $('#xs-menu').toggleClass('visible-xs').toggleClass('hidden-xs');
    // $('#xs-menu-staff').toggleClass('visible-xs').toggleClass('hidden-xs');
    // $('#btnShow').toggle();
    });


    // Accordion active elements
    $('[data-toggle=collapse]').click(function() {
      $('.accordian.active').not(this).not($(this).parent('.panel')).removeClass('active');
      $(this).toggleClass('active');
      $(this).parent('.panel').toggleClass('active');
    });

    //  If clicking an unread announcement, mark it read.
     $('.note-unread').find('.accordian-trigger').click(function() {
       window.location.href = $(this).attr("href");
     });

    // #1981: bootstrap-table reformats server-rendered tables on load. The head CSS
    // (custom_common.css) hides each data-toggle="table" until this code adds .bt-reveal, and a
    // "Loading content..." spinner (.bt-loading) is server-rendered right before the table so
    // something is on screen from the first paint. For each table we reveal it (add .bt-reveal)
    // and hide its spinner in ONE synchronous step, so the browser paints both together: the table
    // never appears while the spinner is still on screen (which made the table jump up when the
    // spinner then vanished). We iterate the tables themselves — not the spinners — so a table
    // without a spinner is still revealed. If bootstrap-table never initializes a table, a timeout
    // reveals it anyway so data is never left hidden.
    $('table[data-toggle="table"]').each(function() {
        var table = this;

        // The spinner, if present, sits right before the table — or before the .bootstrap-table
        // wrapper once bootstrap-table has moved the table inside it.
        function findSpinner() {
            var $wrap = $(table).closest('.bootstrap-table');
            var $prev = ($wrap.length ? $wrap : $(table)).prev();
            return $prev.hasClass('bt-loading') ? $prev : $();
        }

        // Reveal the table and hide its spinner atomically (same synchronous tick → same paint).
        function revealTable() {
            $(table).addClass('bt-reveal');
            findSpinner().hide();
        }

        var start = Date.now();
        var poll = setInterval(function() {
            var wrapped = $(table).closest('.bootstrap-table').length;
            if (wrapped || Date.now() - start > 6000) {
                clearInterval(poll);
                revealTable();
            }
        }, 50);
    });

});
