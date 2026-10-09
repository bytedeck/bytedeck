/* https://github.com/DiemenDesign/summernote-image-shapes */
(function (factory) {
  if (typeof define === 'function' && define.amd) {
    define(['jquery'],factory)
  } else if (typeof module === 'object' && module.exports) {
    module.exports = factory(require('jquery'));
  } else {
    factory(window.jQuery)
  }
}
(function ($) {
  $.extend(true,$.summernote.lang, {
    'en-US': {
      imageShapes: {
        tooltip: 'Image Shapes',
        tooltipShapeOptions: ['Responsive', 'Rounded', 'Circle', 'Thumbnail', 'None']
      }
    }
  });
  $.extend($.summernote.options, {
    imageShapes: {
      icon: '<i class="note-icon-picture"/>',
      /* Must keep the same order as in lang.imageAttributes.tooltipShapeOptions */
      shapes: ['img-responsive', 'img-rounded', 'img-circle', 'img-thumbnail', '']
    }
  });
  $.extend($.summernote.plugins, {
    'imageShapes': function(context) {
      var self      = this,
          ui        = $.summernote.ui,
          $editable = context.layoutInfo.editable,
          options   = context.options,
          lang      = options.langInfo,
          shapes    = options.imageShapes.shapes,
          labels    = lang.imageShapes.tooltipShapeOptions;

      /* Ticks each shape the image has, like the toolbar's own menus, or None when it has none.
         Run as the menu opens, since the image's classes can change between openings. */
      self.updateChecks = function($menu, $img) {
        var hasShape = false;
        $menu.find('a').each(function() {
          var shape = shapes[$.inArray($(this).data('value'), labels)];
          var applied = shape !== '' && $img.hasClass(shape);
          hasShape = hasShape || applied;
          $(this).toggleClass('checked', applied);
        });
        $menu.find('a').filter(function() {
          return shapes[$.inArray($(this).data('value'), labels)] === '';
        }).toggleClass('checked', !hasShape);
      };

      context.memo('button.imageShapes', function() {
        var button = ui.buttonGroup([
          ui.button({
            className: 'dropdown-toggle',
            contents: options.imageShapes.icon + '&nbsp;&nbsp;<span class="caret"></span>',
            tooltip: lang.imageShapes.tooltip,
            data: {
              toggle: 'dropdown'
            },
            /* Remember the image as the menu opens. Bootstrap then moves the focus to this
               button, and Summernote forgets its selected image when the editor loses the
               focus, so by the time a shape is chosen the editor no longer knows the image. */
            click: function(e) {
              self.$img = $($editable.data('target'));
              self.updateChecks($(e.currentTarget).siblings('.dropdown-shape'), self.$img);
            }
          }),
          ui.dropdownCheck({
            className: 'dropdown-shape',
            checkClassName: options.icons.menuCheck,
            items: labels,
            /* The click lands on the whole menu: the item is the link it came from, if any.
               A shape turns on or off, so an image can have several (a circle thumbnail);
               None takes them all off. */
            click: function (e) {
              e.preventDefault();
              var $item = $(e.target).closest('a');
              if (!$item.length || !self.$img) {
                return;
              }
              var shape = shapes[$.inArray($item.data('value'), labels)];
              var $img  = self.$img;
              context.invoke('editor.beforeCommand');
              if (shape === '') {
                $img.removeClass(shapes.join(' '));
              } else {
                $img.toggleClass(shape);
              }
              context.invoke('editor.afterCommand');
            }
          })
        ]);
        return button.render();
      });
    }
  });
}));
