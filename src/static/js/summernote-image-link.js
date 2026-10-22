/*! summernote-image-link: links an image in the editor, the link wrapping the image itself. */

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

    $.extend($.summernote.plugins, {

        /**
         * Link an image: the <a> wraps the <img> (bytedeck/bytedeck#2909).
         *
         * Summernote's Insert Link dialog builds its link from the selected text, and a selected
         * image is no text: the link came out as new text beside the image. So while an image is
         * selected (the editor's target, set as the image is clicked), the toolbar's Link button
         * and the Link button in the image's menu open the same dialog on the image's own link:
         * its URL and "Open in new window", to edit, without "Text to display". The image's menu
         * shows its link's URL and has an Unlink button, and stands in for Summernote's link
         * popover, which otherwise opens over it for a linked image.
         */
        'imageLink': function (context) {
            var self = this,
                ui = $.summernote.ui,
                $editable = context.layoutInfo.editable,
                options = context.options,
                lang = options.langInfo.link;

            context.memo('button.imageLink', function () {
                return ui.button({
                    contents: ui.icon(options.icons.link),
                    tooltip: lang.link,
                    click: function () {
                        self.show();
                    }
                }).render();
            });

            context.memo('button.imageUnlink', function () {
                self.$unlinkButton = ui.button({
                    contents: ui.icon(options.icons.unlink),
                    tooltip: lang.unlink,
                    click: function () {
                        self.unlink();
                    }
                }).render();
                return self.$unlinkButton;
            });

            /**
             * The image the editor has selected, if any.
             *
             * @returns {jQuery} the image, or an empty set.
             */
            this.image = function () {
                return $(context.invoke('editor.restoreTarget')).filter('img');
            };

            /**
             * The link an image is in, within the editor's content.
             *
             * @param {jQuery} $img - the image.
             * @returns {jQuery} the <a>, or an empty set.
             */
            this.anchorOf = function ($img) {
                return $img.closest('a', $editable[0]);
            };

            /** Hook into the link dialog and the popovers once the editor has been built. */
            this.initialize = function () {
                var linkDialog = context.modules.linkDialog,
                    linkPopover = context.modules.linkPopover,
                    imagePopover = context.modules.imagePopover,
                    showLinkDialog = linkDialog.show,
                    updateLinkPopover = linkPopover.update,
                    updateImagePopover = imagePopover.update;

                // the toolbar's Link button, and the link popover's Edit, link the selected image
                linkDialog.show = function () {
                    if (self.image().length) {
                        self.show();
                    } else {
                        showLinkDialog.apply(linkDialog, arguments);
                    }
                };

                // the image's menu shows a linked image's link, so the link popover stays away
                // while an image is selected
                linkPopover.update = function () {
                    if (self.image().length) {
                        linkPopover.hide();
                    } else {
                        updateLinkPopover.apply(linkPopover, arguments);
                    }
                };

                // the same row Summernote's link popover shows a link in, above the image's buttons
                self.$link = $('<span class="note-image-link"><a target="_blank" rel="noopener"></a>&nbsp;</span>')
                    .prependTo(imagePopover.$popover.find('.popover-content, .note-popover-content'));
                imagePopover.update = function (target) {
                    updateImagePopover.apply(imagePopover, arguments);
                    var $img = $(target).filter('img');
                    // The image's menu opens under the pointer as the button goes down, so the click
                    // that selects an image ends on the menu, outside the content, and the editor
                    // doesn't update the link popover for it: a popover open for a text link the
                    // caret was in would stay, over the image's menu.
                    if ($img.length) {
                        linkPopover.hide();
                    }
                    self.showLink($img);
                };
            };

            /**
             * Show an image's link in its menu, and offer Unlink only for a linked image.
             *
             * @param {jQuery} $img - the image the menu is open over.
             */
            this.showLink = function ($img) {
                var href = $img.length ? self.anchorOf($img).attr('href') : undefined;
                self.$link.toggle(href !== undefined).find('a').attr('href', href || '#').text(href || '');
                if (self.$unlinkButton) {
                    ui.toggleBtn(self.$unlinkButton, href !== undefined);
                }
            };

            /**
             * Open the Insert Link dialog on the selected image's link, without "Text to display",
             * and link the image to the URL given.
             */
            this.show = function () {
                var $img = self.image(),
                    linkDialog = context.modules.linkDialog;
                if (!$img.length) {
                    return;
                }
                var $a = self.anchorOf($img),
                    $textGroup = linkDialog.$dialog.find('.note-link-text').closest('.form-group');
                // The dialog enables its button once both fields have something in them, and the
                // text field is hidden here, so it holds a stand-in that nothing reads. It is never
                // the image's src or alt: the dialog takes a text that looks like a web address
                // ("banner.png") as the URL of a new link.
                var linkInfo = {
                    text: 'image',
                    url: $a.attr('href') || ''
                };
                if ($a.length) {
                    linkInfo.isNewWindow = $a.attr('target') === '_blank';
                }
                $textGroup.hide();
                ui.onDialogHidden(linkDialog.$dialog, function () {
                    $textGroup.show();
                });
                linkDialog.showLinkDialog(linkInfo).then(function (info) {
                    self.link($img, info);
                });
            };

            /**
             * Link an image as the Insert Link dialog says, as one step the editor can undo: the
             * link it is in, or a new one wrapped around it.
             *
             * @param {jQuery} $img - the image.
             * @param {Object} info - the dialog's url, isNewWindow and checkProtocol.
             */
            this.link = function ($img, info) {
                var url = $.trim(info.url);
                // as Summernote's own createLink treats the URL typed
                if (options.onCreateLink) {
                    url = options.onCreateLink(url);
                } else if (info.checkProtocol && !/^([A-Za-z][A-Za-z0-9+-.]*:|#|\/)/.test(url)) {
                    url = options.defaultProtocol + url;
                }
                // A link that runs script or opens a document written into it isn't made. Browsers
                // ignore spaces and control characters in a scheme, so they don't count here either.
                if (/^(javascript|data|vbscript):/i.test(url.replace(/[\u0000-\u0020]/g, ''))) {
                    return;
                }
                context.invoke('editor.beforeCommand');
                var $a = self.anchorOf($img);
                if (!$a.length) {
                    $a = $img.wrap('<a></a>').parent();
                }
                $a.attr('href', url);
                if (info.isNewWindow) {
                    $a.attr('target', '_blank');
                } else {
                    $a.removeAttr('target');
                }
                context.invoke('editor.afterCommand');
                self.showLink($img);
            };

            /** Take the selected image out of its link, as one step the editor can undo. */
            this.unlink = function () {
                var $img = self.image(),
                    $a = self.anchorOf($img);
                if (!$a.length) {
                    return;
                }
                context.invoke('editor.beforeCommand');
                $a.replaceWith($a.contents());
                context.invoke('editor.afterCommand');
                self.showLink($img);
            };
        }
    });
}));
