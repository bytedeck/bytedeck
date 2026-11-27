/*! summernote-paste-colors: drops the text and highlight colors pasted content brings with it. */

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
         * Drop the text and highlight colors that pasted content brings with it.
         *
         * Copying text off a page carries the colors it was shown in: the browser writes the
         * computed color and background-color into the copied HTML as inline styles. Text copied
         * from a comment in the dark theme pastes as dark text on dark blocks, which the light
         * theme can barely show, and text from a document comes in black, which the dark theme
         * can't show at all. Those colors belong to where the text was copied from rather than to
         * what the writer meant, so this takes them off what a paste adds and leaves the rest of
         * its formatting: bold, lists, links and so on (bytedeck/bytedeck#3008).
         *
         * The browser does the paste itself, which keeps its own clean-up of pasted markup
         * (scripts and event handlers dropped). This notes the elements the content holds when a
         * paste starts and, once the browser has put the pasted content in, takes the colors off
         * the elements that weren't there before. Colors already in the content, and ones chosen
         * afterwards with the toolbar's color button, are left alone.
         */
        'pasteColors': function (context) {
            var self = this,
                editable = context.layoutInfo.editable[0];

            /**
             * Take the text and background colors off one element.
             *
             * Colors come as inline styles, and in older markup (pasted from Word, or an older
             * page) as a font's color attribute or a table cell's bgcolor. A style attribute left
             * empty goes too, so the saved HTML carries no empty style="".
             *
             * Returns whether the element changed.
             */
            this.dropColors = function (element) {
                var changed = false;
                if (element.style && (element.style.color || element.style.backgroundColor)) {
                    element.style.removeProperty('color');
                    element.style.removeProperty('background-color');
                    if (!element.style.cssText) {
                        element.removeAttribute('style');
                    }
                    changed = true;
                }
                if (element.tagName === 'FONT' && element.hasAttribute('color')) {
                    element.removeAttribute('color');
                    changed = true;
                }
                if (element.hasAttribute('bgcolor')) {
                    element.removeAttribute('bgcolor');
                    changed = true;
                }
                return changed;
            };

            this.events = {
                /**
                 * Note the content's elements as a paste starts, and clean up what it adds.
                 *
                 * Summernote reports the paste before the browser acts on it, so the clean-up
                 * waits a turn, by which time the pasted content is in. An image pasted as a file
                 * is Summernote's to insert, once it has uploaded, so it doesn't come through
                 * here, and a pasted picture has no colors to lose anyway.
                 */
                'summernote.paste': function () {
                    var before = new Set(editable.querySelectorAll('*'));
                    setTimeout(function () {
                        var changed = false;
                        Array.prototype.forEach.call(editable.querySelectorAll('*'), function (element) {
                            if (!before.has(element) && self.dropColors(element)) {
                                changed = true;
                            }
                        });
                        if (changed) {
                            // Saves the cleaned content as an undo step and reports the change,
                            // as a toolbar command does, so the form and autosave get it.
                            context.invoke('editor.afterCommand');
                        }
                    });
                }
            };
        }
    });
}));
