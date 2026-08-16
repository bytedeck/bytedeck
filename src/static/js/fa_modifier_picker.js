/*!
 * Font Awesome modifier picker for FontAwesomeModifierPickerWidget
 * (utilities.fa_icon_widget.FontAwesomeModifierPickerWidget).
 *
 * Vanilla JS. Turns the toggle buttons into a space-separated "fa-" class string
 * in a hidden field, and reflects that field's current value back onto the buttons
 * on load. The hidden field carries the value the form submits; dispatching its
 * "input" event lets the paired icon picker update its live preview. Any class the
 * buttons don't manage (an advanced/stack class from stored data) is preserved.
 *
 * Button groups carry data-select:
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
            // kept as-is (an advanced/stack class in stored data).
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

            // Set the buttons from the field's current value (on load).
            function syncButtonsFromField() {
                var tokens = tokensOf(field.value);
                passthrough = tokens.filter(function (token) { return !managed[token]; });
                Array.prototype.forEach.call(root.querySelectorAll('.btn[data-modifier]'), function (btn) {
                    var cls = btn.getAttribute('data-modifier');
                    btn.classList.toggle('active', !!cls && tokens.indexOf(cls) !== -1);
                });
            }

            Array.prototype.forEach.call(groups, function (group) {
                group.addEventListener('click', function (event) {
                    var btn = event.target.closest('.btn[data-modifier]');
                    if (!btn) {
                        return;
                    }
                    if (group.getAttribute('data-select') === 'multi') {
                        btn.classList.toggle('active');
                    } else {  // toggle-radio: 0 or 1 active (click the active one to clear it)
                        var wasActive = btn.classList.contains('active');
                        Array.prototype.forEach.call(group.querySelectorAll('.btn'), function (b) { b.classList.remove('active'); });
                        if (!wasActive) {
                            btn.classList.add('active');
                        }
                    }
                    recompute();
                });
            });

            syncButtonsFromField();
        });
    });
})();
