$(document).ready(function() {

  //Formatting datePicker inputs
  // $('.datePicker')
  //     //this rwap
  //     .wrap("<div class='input-group'>")
  //     .datepicker({
  //       showButtonPanel: true,
  //       showOn: "both",
  //       changeMonth: true,
  //       changeYear: true,
  //     });
  //
  // $('.ui-datepicker-trigger')
  //   // http://getbootstrap.com/components/#input-groups-buttons
  //   //.empty().append("<i class='fa fa-calendar'></i>") //font-awesome icons looks nicer
  //   .empty().append('<span class="glyphicon glyphicon-calendar" aria-hidden="true"></span>')
  //   .addClass("btn btn-default")
  //   .wrap("<span class='input-group-btn'></span");

  /* off-canvas sidebar toggle */
  $('[data-toggle=offcanvas]').click(function() {
    $(this).toggleClass('visible-xs text-center');
    $(this).find('i').toggleClass('fa-chevron-right fa-chevron-left');
    $('.row-offcanvas').toggleClass('active');
    $('#lg-menu').toggleClass('hidden-xs').toggleClass('visible-xs');
    $('#lg-menu-staff').toggleClass('hidden-xs').toggleClass('visible-xs');
    $('#xs-menu').toggleClass('visible-xs').toggleClass('hidden-xs');
    $('#xs-menu-staff').toggleClass('visible-xs').toggleClass('hidden-xs');
    $('#btnShow').toggle();
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
