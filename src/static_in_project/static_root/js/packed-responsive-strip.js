// https://learn.jquery.com/plugins/basic-plugin-creation/

(function( $ ) {

    //noinspection JSAnnotator
    $.fn.pack = function( options ) {

        // This is the easiest way to have default options.
        var settings = $.extend({
            // These are the defaults.
            //color: "#556b2f",
            // backgroundColor: "white"
        }, options );

        console.log(this);

        // return this.each(function() {
        //     // this should be a container div with a series of child elements within.
        $(this).css({"display": "flex"})
               .children().each( function() {

                  if($(this).is('img')) {
                    var $img = $(this);
                    var aspect = this.naturalWidth/this.naturalHeight;
                  }
                  else { // <figure>
                    $(this).css('width','100%');
                    var $img = $(this).find('img');
                    var aspect = $img[0].naturalWidth/$img[0].naturalHeight;
                  }
                  $(this).wrap('<div class="pack-wrap" style="display:flex; flex: 0% ' + aspect + ' 1"  />')
                  $img.css({"width": "100%", "height": "auto"})
                      .addClass("pack-item");
              });

        return this;
        // });

    };

}( jQuery ));


