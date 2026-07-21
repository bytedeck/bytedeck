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

    // #1981: bootstrap-table reformats server-rendered tables on load. A "Loading content..."
    // spinner (.bt-loading) is server-rendered right before each data-toggle="table", so it's
    // visible from the first paint; the head CSS (custom_common.css) hides the raw table until
    // bootstrap-table formats it. Here we hide each spinner once its table is wrapped in
    // .bootstrap-table — and, if bootstrap-table never initializes a table, reveal the raw
    // table after a timeout so its data is never left hidden behind the spinner.
    $('.bt-loading').each(function() {
        var $spinner = $(this);

        // The table this spinner covers is the next sibling — still the raw <table>, or, if
        // bootstrap-table already ran, the .bootstrap-table wrapper it was replaced with.
        function findTable() {
            var $next = $spinner.next();
            return $next.is('table[data-toggle="table"]') ? $next : $next.find('table[data-toggle="table"]').first();
        }

        var start = Date.now();
        var poll = setInterval(function() {
            var $table = findTable();
            var wrapped = $table.length && $table.closest('.bootstrap-table').length;
            if (wrapped || Date.now() - start > 6000) {
                clearInterval(poll);
                if (!wrapped && $table.length) {
                    $table.addClass('bt-reveal');
                }
                $spinner.hide();
            }
        }, 50);
    });

});
