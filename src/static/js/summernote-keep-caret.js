/*! summernote-keep-caret: keeps the caret in place while the toolbar is used. */

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
         * Keep the caret where the writer left it when a toolbar control is pressed.
         *
         * Summernote rebuilds the range it works from out of the live document selection every
         * time the editing area takes focus, and every toolbar command focuses the editing area
         * on its way in. Pressing a control first moves the selection out of the editing area, so
         * the only selection left by the time the command runs is the one the browser creates on
         * focus: the very start of the content. The command lands there, and the editor scrolls
         * up to follow it. Inserting a table hit this on every attempt, because the size picker
         * is a plain div and pressing a div collapses the selection onto it.
         *
         * Suppressing the default action of a press inside the toolbar leaves the selection
         * alone, and putting the caret back covers the case where it had already moved elsewhere
         * before the press, such as a writer who typed in one field and then reached for this
         * editor's toolbar (bytedeck/bytedeck#2734).
         */
        'keepCaret': function (context) {
            var self = this,
                $toolbar = context.layoutInfo.toolbar,
                $editable = context.layoutInfo.editable,
                editable = $editable[0];

            /**
             * Where the writer last put the caret in this editor, or null while they never have.
             *
             * A DOM range follows the edits made around it, so this stays meaningful as the
             * content grows. It is deliberately not summernote's own saved range: that one falls
             * back to a range built from the whole editor before the writer has touched it, and a
             * list command handed that range turns the entire content into one list.
             */
            this.caret = null;

            /**
             * Whether a node is part of this editor's content.
             *
             * $.contains() is false for the element itself, which is where the selection sits
             * while the editor is empty, so that case is checked separately.
             */
            this.isInEditor = function (node) {
                return !!node && (node === editable || $.contains(editable, node));
            };

            /** Whether the document selection is currently inside this editor's content. */
            this.selectionIsInEditor = function () {
                var selection = window.getSelection();
                return !!(selection && selection.rangeCount &&
                          self.isInEditor(selection.getRangeAt(0).startContainer));
            };

            /** Remember the caret whenever the writer moves it with the mouse or the keyboard. */
            this.rememberCaret = function () {
                if (self.selectionIsInEditor()) {
                    self.caret = window.getSelection().getRangeAt(0).cloneRange();
                }
            };

            /** Put the remembered caret back, unless the content it pointed at is gone. */
            this.restoreCaret = function () {
                if (!self.caret ||
                    !self.isInEditor(self.caret.startContainer) ||
                    !self.isInEditor(self.caret.endContainer)) {
                    return;
                }
                var selection = window.getSelection();
                selection.removeAllRanges();
                selection.addRange(self.caret);
            };

            /** Watch the editing area and the toolbar once the editor has been built. */
            this.initialize = function () {
                $editable.on('mouseup.keepCaret keyup.keepCaret', self.rememberCaret);
                $toolbar.on('mousedown.keepCaret', function (event) {
                    // Text fields in the toolbar (the colour inputs, the icon search box) need
                    // the focus a press normally gives them.
                    if ($(event.target).closest('input, textarea, select, [contenteditable="true"]').length) {
                        return;
                    }
                    // Buttons, dropdown items and the table size picker all act on click or on
                    // mouseup, both of which still fire once the press itself does nothing.
                    event.preventDefault();
                    if (!self.selectionIsInEditor()) {
                        self.restoreCaret();
                    }
                });
            };

            /** Drop the handlers when the editor is torn down. */
            this.destroy = function () {
                $editable.off('.keepCaret');
                $toolbar.off('.keepCaret');
            };
        }
    });
}));
