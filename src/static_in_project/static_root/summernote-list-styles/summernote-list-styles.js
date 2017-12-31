/* https://github.com/tylerecouture/summernote-lists  */

(function (factory) {
    /* global define */
    if (typeof define === 'function' && define.amd) {
        // AMD. Register as an anonymous module.
        define(['jquery'], factory);
    } else if (typeof module === 'object' && module.exports) {
        // Node/CommonJS
        module.exports = factory(require('jquery'));
    } else {
        // Browser globals
        factory(window.jQuery);
    }
}(function ($) {

    $.extend(true,$.summernote.lang, {
      'en-US': {
        listStyleTypes: {
          tooltip: 'List Styles',
          labelsListStyleTypes: ['Numbered', 'Lower Alpha', 'Upper Alpha', 'Lower Roman', 'Upper Roman', 'Disc', 'Circle', 'Square']
        }
      }
    });
    $.extend($.summernote.options, {
      listStyleTypes: {
        /* Must keep the same order as in lang.imageAttributes.tooltipShapeOptions */
        styles: ['decimal','lower-alpha','upper-alpha','lower-roman','upper-roman', 'disc', 'circle', 'square']
      }
    });

    // Extends plugins for emoji plugin.
    $.extend($.summernote.plugins, {

        'listStyles': function (context) {
            var self = this;
            var ui = $.summernote.ui;
            var options = context.options;
            var lang = options.langInfo;
            var listStyleTypes = options.listStyleTypes.styles;
            var listStyleLabels = lang.listStyleTypes.labelsListStyleTypes;

            var list = '';
            var index = 0;
            for (const listStyleType of listStyleTypes) {
                list += '<li><a href="#">';
                list += '<ol><li style="list-style-type: ' + listStyleType + ';">';
                list += listStyleLabels[index] + '</li></ol></a></li>';
                index++;
            }

            list += '<li><a href="#" data-class="list-spaced">Spaced List</a></li>';

            context.memo('button.listStyles', function () {
                return ui.buttonGroup([
                    ui.button({
                        className: 'dropdown-toggle list-styles',
                        contents: ui.icon(options.icons.caret, 'span'),
                        tooltip:  lang.listStyleTypes.tooltip,
                        data: {
                            toggle: 'dropdown'
                        }
                    }),
                    ui.dropdown({
                        className: 'dropdown-list-styles',
                        contents: list,
                        callback: function ($dropdown) {
                            $dropdown.find('a').each(function () {
                                let $this = $(this);
                                $this.click(function () {
                                    if( $this.attr('data-class')) {
                                        self.updateListClass( $this.data('class') );
                                    }
                                    else
                                        self.updateStyleType( $this.find("li").css('list-style-type') );
                                });
                            });
                        }
                    })
                ]).render();
            });

            self.updateStyleType = function (style) {
                self.getParentList().css('list-style-type', style);
            };

            self.updateListClass = function (CSSClass) {
                self.getParentList().toggleClass(CSSClass);
            };

            self.getParentList = function() {
                if (window.getSelection) {
                    var $focusNode = $(window.getSelection().focusNode);
                    return $focusNode.closest('div.note-editable ol, div.note-editable ul');
                }
                else
                    return null;
            }

        }
    });
}));
