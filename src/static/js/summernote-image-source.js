/*! summernote-image-source: changes the picture an image in the editor shows, and its description. */

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

    $.extend(true, $.summernote.lang, {
        'en-US': {
            imageSource: {
                tooltip: 'Edit image',
                title: 'Edit Image',
                upload: 'Upload a new image',
                url: 'Image URL',
                alt: 'Image description',
                altHelp: 'What the image shows, read out by screen readers and shown in its place if it can\'t load.',
                save: 'Save'
            }
        }
    });

    $.extend($.summernote.plugins, {

        /**
         * A button in the image's popover that changes the picture the image shows: a new upload,
         * or the URL it points at, which the dialog shows to be edited (bytedeck/bytedeck#2907).
         * The dialog also sets the image's description, its alt text (bytedeck/bytedeck#2911).
         * Left empty, the image has no alt at all, rather than alt="", which would tell a screen
         * reader to skip the image as decoration.
         *
         * Only the image's src and alt change, so its size, float, shapes and other attributes stay as
         * they were and nothing has to be set up again. The one exception is a height left by
         * dragging the image's corner: next to a width, it would stretch a new picture of a
         * different shape, so it goes and the picture keeps its own proportions at that width.
         *
         * The upload is the editor's own, which the widget hands over as the uploadImages option
         * (bytedeck_summernote/widget_common.html); without one, as with attachments turned off,
         * the dialog offers the URL alone.
         */
        'imageSource': function (context) {
            var self = this,
                ui = $.summernote.ui,
                $editable = context.layoutInfo.editable,
                options = context.options,
                lang = options.langInfo.imageSource,
                upload = options.uploadImages;

            context.memo('button.imageSource', function () {
                return ui.button({
                    contents: '<i class="fa fa-pencil" aria-hidden="true"></i>',
                    tooltip: lang.tooltip,
                    // The image is taken as the button is pressed, as Image Shapes does, since
                    // the editor forgets its selected image once the focus moves to the dialog.
                    click: function () {
                        self.show($($editable.data('target')));
                    }
                }).render();
            });

            /** Build the dialog, beside the editor's own dialogs. */
            this.initialize = function () {
                var $container = options.dialogsInBody ? $(document.body) : options.container;
                var body = [];
                if (upload) {
                    body.push(
                        '<div class="form-group note-form-group">',
                        '<label for="note-dialog-image-source-file-' + options.id + '" class="note-form-label">' + lang.upload + '</label>',
                        '<input id="note-dialog-image-source-file-' + options.id + '" class="note-image-source-file form-control-file note-form-control note-input"',
                        ' type="file" accept="' + options.acceptImageFileTypes + '"/>',
                        '</div>'
                    );
                }
                body.push(
                    '<div class="form-group note-form-group">',
                    '<label for="note-dialog-image-source-url-' + options.id + '" class="note-form-label">' + lang.url + '</label>',
                    '<input id="note-dialog-image-source-url-' + options.id + '" class="note-image-source-url form-control note-form-control note-input" type="text"/>',
                    '</div>',
                    '<div class="form-group note-form-group">',
                    '<label for="note-dialog-image-source-alt-' + options.id + '" class="note-form-label">' + lang.alt + '</label>',
                    '<input id="note-dialog-image-source-alt-' + options.id + '" class="note-image-source-alt form-control note-form-control note-input"',
                    ' type="text" aria-describedby="note-dialog-image-source-alt-help-' + options.id + '"/>',
                    '<p id="note-dialog-image-source-alt-help-' + options.id + '" class="help-block">' + lang.altHelp + '</p>',
                    '</div>'
                );
                var footer = '<input type="button" href="#" class="btn btn-primary note-btn note-btn-primary note-image-source-btn" value="' +
                    lang.save + '" disabled>';
                self.$dialog = ui.dialog({
                    title: lang.title,
                    fade: options.dialogsFade,
                    body: body.join(''),
                    footer: footer
                }).render().appendTo($container);
            };

            /** Take the dialog out with the editor. */
            this.destroy = function () {
                ui.hideDialog(self.$dialog);
                self.$dialog.remove();
            };

            /**
             * Open the dialog on the image's current URL and description, and change the image to
             * the picture chosen in it, with the description as it stands then: a file, which is
             * uploaded, or the URL as it stands when Save is pressed.
             *
             * @param {jQuery} $img - the image to change.
             */
            this.show = function ($img) {
                if (!$img.is('img')) {
                    return;
                }
                var $file = self.$dialog.find('.note-image-source-file'),
                    $url = self.$dialog.find('.note-image-source-url'),
                    $alt = self.$dialog.find('.note-image-source-alt'),
                    $button = self.$dialog.find('.note-image-source-btn'),
                    // An upload still going when the dialog closes was given up on, so what it
                    // brings back changes nothing, nor closes the dialog if it was opened again.
                    open = true;

                ui.onDialogShown(self.$dialog, function () {
                    context.triggerEvent('dialog.shown');
                    $file.on('change', function () {
                        var input = this;
                        if (!input.files || !input.files.length) {
                            return;
                        }
                        upload(input.files).done(function (urls) {
                            if (open && urls.length) {
                                self.change($img, urls[0], $alt.val());
                                ui.hideDialog(self.$dialog);
                            }
                        }).fail(function () {
                            // the same file chosen again would otherwise not count as a change,
                            // so trying it again would do nothing
                            input.value = '';
                        });
                    });
                    $url.on('input paste propertychange', function () {
                        ui.toggleBtn($button, $.trim($url.val()));
                    }).val($img.attr('src')).trigger('focus').trigger('select');
                    ui.toggleBtn($button, $.trim($url.val()));
                    $alt.val($img.attr('alt') || '');
                    $button.on('click', function (event) {
                        event.preventDefault();
                        // Enter reaches here even while the button is disabled, and an image
                        // with no picture is never what was meant
                        if (!$.trim($url.val())) {
                            return;
                        }
                        self.change($img, $url.val(), $alt.val());
                        ui.hideDialog(self.$dialog);
                    });
                    $url.add($alt).on('keypress', function (event) {
                        if (event.keyCode === 13) {
                            event.preventDefault();
                            $button.trigger('click');
                        }
                    });
                });
                // A file left chosen would count toward the size of the form it sits in when the
                // form is sent (js/upload-size-check.js), so the choice goes when the dialog does.
                ui.onDialogHidden(self.$dialog, function () {
                    open = false;
                    $file.off().val('');
                    $url.off();
                    $alt.off();
                    $button.off();
                });
                ui.showDialog(self.$dialog);
            };

            /**
             * Point an image at a picture and give it a description, as one step the editor can
             * undo. The picture's own attributes change only when the picture does, so a new
             * description alone leaves a dragged height in place.
             *
             * @param {jQuery} $img - the image to change.
             * @param {string} src - the picture's URL.
             * @param {string} alt - its description; empty for none.
             */
            this.change = function ($img, src, alt) {
                src = $.trim(src);
                alt = $.trim(alt || '');
                context.invoke('editor.beforeCommand');
                if (src !== $img.attr('src')) {
                    // data-filename names the file the image was inserted from, which it no longer shows
                    $img.attr('src', src).removeAttr('data-filename');
                    if ($img[0].style.width) {
                        $img.css('height', '');
                    }
                }
                if (alt) {
                    $img.attr('alt', alt);
                } else {
                    $img.removeAttr('alt');
                }
                context.invoke('editor.afterCommand');
            };
        }
    });
}));
