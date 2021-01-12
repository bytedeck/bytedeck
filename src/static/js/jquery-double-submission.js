// http://stackoverflow.com/questions/2830542/prevent-double-submission-of-forms-in-jquery/2830812#2830812

// jQuery plugin to prevent double submission of forms
jQuery.fn.preventDoubleSubmission = function () {
    $(this).on('submit', function (e) {
        var $form = $(this);

        if ($form.data('submitted') === true) {
            // Previously submitted - don't submit again
            alert('Ok Clickyhappy McClickface, how about you have a little patience and give me some time to process your request?  Thanks!');
            e.preventDefault();
        } else {
            // Mark it so that the next submit can be ignored
            // ADDED requirement that form be valid **** We're not using this but might in the future)
            //if($form.valid()) {
            $form.data('submitted', true);
            // change to laoding fa icon?
            //$form.find(':submit').val
            //}
        }
    });

    // Keep chainability
    return this;
};

// $(document).ready(function() { // doesn't recognize the function inside $().ready? This is at the end anyway so
// DOM will be loaded.
  $('form').preventDoubleSubmission();
// });
