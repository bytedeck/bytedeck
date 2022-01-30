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
    
});
