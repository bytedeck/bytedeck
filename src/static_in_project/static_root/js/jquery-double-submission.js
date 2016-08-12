// http://stackoverflow.com/questions/2830542/prevent-double-submission-of-forms-in-jquery/2830812#2830812

// jQuery plugin to prevent double submission of forms
jQuery.fn.preventDoubleSubmission = function() {
  $(this).on('submit',function(e){
    var $form = $(this);

    if ($form.data('submitted') === true) {
      // Previously submitted - don't submit again
      e.preventDefault();
    } else {
      // Mark it so that the next submit can be ignored
      $form.data('submitted', true);
    }
  });

  // Keep chainability
  return this;
};

$(document).ready(function() {
  $('form').preventDoubleSubmission();
});
