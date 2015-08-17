$(document).ready(function() {

  // notifications dropdown
  $(".notification-toggle").click(function(e){
    e.preventDefault();
    $.ajax({
      type: "POST",
      url: "{% url 'notifications:ajax' %}",
      data: {
        csrfmiddlewaretoken: "{{ csrf_token }}",
      },
      success: function(data){
        $("#notification_dropdown").html("");
        var count = data.count;
        // console.log(count);
        if(count!=0) {
          // $("#notification_badge").html(count);
          $("#notification_dropdown").append("<li class='dropdown-header'>New Notifications</li>")
          $(data.notifications).each(function(){
            var link = this;
            $("#notification_dropdown").append("<li>"+link + "</li>")
          })
          // console.log(data.notifications);
          $("#notification_dropdown").append("<li role='separator' class='divider'></li>")
        }

        var url = "{% url 'notifications:list' %}"
        $("#notification_dropdown").append("<li><a href='"+url+"'>View All Notifications</a></li>")

      },
      error: function(rs, e) {
        console.log(rs);
        console.log(e);
      }
    });
  });

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
    $('#xs-menu').toggleClass('visible-xs').toggleClass('hidden-xs');
    $('#btnShow').toggle();
  });


  // Accordion active elements
  $('[data-toggle=collapse]').click(function() {
      $('.active').not(this).not($(this).parent('.panel')).removeClass('active');
      $(this).toggleClass('active');
      $(this).parent('.panel').toggleClass('active');
   });
});
