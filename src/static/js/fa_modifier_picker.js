/*!
 * Font Awesome modifier picker for FontAwesomeModifierPickerWidget
 * (utilities.fa_icon_widget.FontAwesomeModifierPickerWidget).
 *
 * Vanilla JS. Turns the toggle buttons into a space-separated "fa-" class string
 * in the text input, and reflects the input's current value back onto the buttons
 * on load. The text input stays the source of truth (and editable), so any class
 * the buttons don't manage is preserved; dispatching its "input" event lets the
 * paired icon picker update its live preview.
 *
 * Button groups carry data-select:
 *   radio        - exactly one active (includes a "no rotation" option, value "")
 *   toggle-radio - at most one active (click the active one to clear it)
 *   multi        - each toggles independently
 */
(function () {
    function ready(fn) {
        if (document.readyState !== 'loading') {
            fn();
        } else {
            document.addEventListener('DOMContentLoaded', fn);
        }
    }

    ready(function () {
        Array.prototype.forEach.call(document.querySelectorAll('.fa-modifier-picker'), function (root) {
            var field = root.querySelector('.fa-modifier-picker-input');
            var groups = root.querySelectorAll('[data-modifier-group]');
            if (!field || !groups.length) {
                return;
            }

            // Every class the buttons manage, so tokens outside this set can be
            // kept as-is (an advanced/stack class the user typed).
            var managed = {};
            Array.prototype.forEach.call(root.querySelectorAll('.btn[data-modifier]'), function (btn) {
                var cls = btn.getAttribute('data-modifier');
                if (cls) {
                    managed[cls] = true;
                }
            });

            // Classes the buttons don't cover, preserved across recomputes.
            var passthrough = [];

            function tokensOf(value) {
                return (value || '').trim().split(/\s+/).filter(Boolean);
            }

            // Recompute the field value from the active buttons plus passthrough.
            function recompute() {
                var classes = [];
                Array.prototype.forEach.call(root.querySelectorAll('.btn.active[data-modifier]'), function (btn) {
                    var cls = btn.getAttribute('data-modifier');
                    if (cls) {
                        classes.push(cls);
                    }
                });
                field.value = classes.concat(passthrough).join(' ').trim();
                field.dispatchEvent(new Event('input', { bubbles: true }));
            }

            // Set the buttons from the field's current value.
            function syncButtonsFromField() {
                var tokens = tokensOf(field.value);
                passthrough = tokens.filter(function (token) { return !managed[token]; });
                Array.prototype.forEach.call(groups, function (group) {
                    var anyActive = false;
                    Array.prototype.forEach.call(group.querySelectorAll('.btn[data-modifier]'), function (btn) {
                        var cls = btn.getAttribute('data-modifier');
                        var on = !!cls && tokens.indexOf(cls) !== -1;
                        btn.classList.toggle('active', on);
                        if (on) {
                            anyActive = true;
                        }
                    });
                    // A radio group with none of its classes present falls back to
                    // its empty-value option (e.g. "no rotation").
                    if (group.getAttribute('data-select') === 'radio' && !anyActive) {
                        var none = group.querySelector('.btn[data-modifier=""]');
                        if (none) {
                            none.classList.add('active');
                        }
                    }
                });
            }

            Array.prototype.forEach.call(groups, function (group) {
                group.addEventListener('click', function (event) {
                    var btn = event.target.closest('.btn[data-modifier]');
                    if (!btn) {
                        return;
                    }
                    var mode = group.getAttribute('data-select');
                    if (mode === 'multi') {
                        btn.classList.toggle('active');
                    } else if (mode === 'radio') {
                        Array.prototype.forEach.call(group.querySelectorAll('.btn'), function (b) { b.classList.remove('active'); });
                        btn.classList.add('active');
                    } else {  // toggle-radio: 0 or 1 active
                        var wasActive = btn.classList.contains('active');
                        Array.prototype.forEach.call(group.querySelectorAll('.btn'), function (b) { b.classList.remove('active'); });
                        if (!wasActive) {
                            btn.classList.add('active');
                        }
                    }
                    recompute();
                });
            });

            // Keep the buttons honest if the text field is edited by hand.
            field.addEventListener('input', function () {
                if (field !== document.activeElement) {
                    return;  // our own recompute() dispatches input; don't loop
                }
                syncButtonsFromField();
            });

            syncButtonsFromField();
        });
    });
})();
