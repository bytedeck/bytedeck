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

    // #1981: bootstrap-table reformats server-rendered tables on load, briefly showing the raw
    // table before it "jumps" into the styled/paginated version. The head CSS (custom_common.css)
    // hides those tables until they're formatted; here we show a spinner in the gap and make sure
    // the table is revealed even if bootstrap-table's script never runs.
    $('table[data-toggle="table"]').each(function() {
        var $table = $(this);

        // If bootstrap-table already initialized this table (its script ran before this one),
        // it is wrapped and the CSS has already revealed it — nothing to do.
        if ($table.closest('.bootstrap-table').length) {
            return;
        }

        var $spinner = $(
            '<div class="bt-loading" role="status" aria-label="Loading table">' +
            '<i class="fa fa-spinner fa-spin fa-2x" aria-hidden="true"></i></div>'
        );
        $table.before($spinner);

        // Poll for bootstrap-table to wrap the table (robust to script load order and to the
        // different bootstrap-table versions loaded across the site). Drop the spinner once
        // wrapped — or after a timeout, so a failed/late bootstrap-table can never leave the
        // data hidden (the fallback class reveals the raw table).
        var start = Date.now();
        var poll = setInterval(function() {
            var wrapped = $table.closest('.bootstrap-table').length;
            if (wrapped || Date.now() - start > 6000) {
                clearInterval(poll);
                $spinner.remove();
                if (!wrapped) {
                    $table.addClass('bt-reveal');
                }
            }
        }, 50);
    });

});
