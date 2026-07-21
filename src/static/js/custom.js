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
    // (custom_common.css) replaces each raw table with a "Loading content…" spinner from the
    // first paint and reveals the real table once bootstrap-table wraps it in .bootstrap-table.
    // This is only a fallback: if bootstrap-table never initializes a table (e.g. one its
    // script doesn't auto-handle), reveal the raw table after a timeout so its data is never
    // left hidden behind the spinner.
    $('table[data-toggle="table"]').each(function() {
        var $table = $(this);

        // Already wrapped/formatted (bootstrap-table's script ran first) — CSS revealed it.
        if ($table.closest('.bootstrap-table').length) {
            return;
        }

        // Give bootstrap-table time to wrap the table; if it never does, reveal the raw table.
        setTimeout(function() {
            if (!$table.closest('.bootstrap-table').length) {
                $table.addClass('bt-reveal');
            }
        }, 6000);
    });

});
