/*! summernote-image-align: places an image on a line of its own, at the left, center or right. */

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

    /** Each alignment's class: Bootstrap 3's center-block, and its counterpart on the right in css/custom_common.css. */
    var ALIGNMENTS = {
        left: '',
        center: 'center-block',
        right: 'img-align-right'
    };
    var ALIGNMENT_CLASSES = 'center-block img-align-right';

    $.extend($.summernote.plugins, {

        /**
         * Align left, Align center and Align right buttons for the image's menu (bytedeck/bytedeck#2910).
         *
         * They place the image on a line of its own, where the float buttons beside them let text
         * wrap around it. A Responsive image is a block (Bootstrap's img-responsive), which the
         * paragraph's own alignment can't move, so the alignment is a class on the image, and it
         * works for an inline image too. Classes rather than an inline style, since comments keep
         * an image's class but drop display from its style.
         *
         * An image is either aligned or floated: choosing an alignment takes its float off, and
         * the float buttons take its alignment off (Remove float leaves it as it is).
         */
        'imageAlign': function (context) {
            var self = this,
                ui = $.summernote.ui,
                options = context.options,
                lang = options.langInfo.paragraph;

            /**
             * The function that renders the button for one alignment.
             *
             * @param {string} alignment - 'left', 'center' or 'right'.
             * @param {string} icon - the name of its icon in Summernote's icons option.
             * @returns {Function} the button's renderer, for context.memo.
             */
            function alignButton(alignment, icon) {
                return function () {
                    return ui.button({
                        contents: ui.icon(options.icons[icon]),
                        tooltip: lang[alignment],
                        click: function () {
                            self.align(alignment);
                        }
                    }).render();
                };
            }

            context.memo('button.imageAlignLeft', alignButton('left', 'alignLeft'));
            context.memo('button.imageAlignCenter', alignButton('center', 'alignCenter'));
            context.memo('button.imageAlignRight', alignButton('right', 'alignRight'));

            /**
             * Align the selected image, as one step the editor can undo.
             *
             * @param {string} alignment - 'left', 'center' or 'right'.
             */
            this.align = function (alignment) {
                var $img = $(context.invoke('editor.restoreTarget')).filter('img');
                if (!$img.length) {
                    return;
                }
                context.invoke('editor.beforeCommand');
                $img.removeClass(ALIGNMENT_CLASSES + ' note-float-left note-float-right')
                    .addClass(ALIGNMENTS[alignment])
                    .css('float', '');
                context.invoke('editor.afterCommand');
            };

            /**
             * Float the selected image as Summernote's floatMe does, taking off its alignment when
             * it floats it, since a floated image is no longer on a line of its own.
             */
            this.initialize = function () {
                var editor = context.modules.editor;
                editor.floatMe = function (value) {
                    var $img = $(editor.restoreTarget());
                    editor.beforeCommand();
                    $img.toggleClass('note-float-left', value === 'left');
                    $img.toggleClass('note-float-right', value === 'right');
                    $img.css('float', value === 'none' ? '' : value);
                    if (value !== 'none') {
                        $img.removeClass(ALIGNMENT_CLASSES);
                    }
                    editor.afterCommand();
                };
            };
        }
    });
}));
