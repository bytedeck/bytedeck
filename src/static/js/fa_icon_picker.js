/*!
 * Font Awesome icon picker for FontAwesomeIconPickerWidget
 * (utilities.widgets.FontAwesomeIconPickerWidget).
 *
 * Vanilla JS (no jQuery), so it is safe regardless of script order. For every
 * .fa-icon-picker on the page it builds a searchable grid from window.faIcons
 * (the shared FA 4.7.0 list in fa_icons_4.7.0.js), keeps a live preview beside
 * the input, and writes the chosen BARE icon name into the input. Typing a name
 * by hand still works: the input is the source of truth, the picker just fills it.
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
        var iconNames = Object.keys(window.faIcons || {});

        Array.prototype.forEach.call(document.querySelectorAll('.fa-icon-picker'), function (root) {
            var input = root.querySelector('.fa-icon-picker-input');
            var previewIcon = root.querySelector('.fa-icon-picker-preview i');
            var toggle = root.querySelector('.fa-icon-picker-toggle');
            var panel = root.querySelector('.fa-icon-picker-panel');
            var search = root.querySelector('.fa-icon-picker-search');
            var grid = root.querySelector('.fa-icon-picker-grid');
            if (!input || !grid || !panel) {
                return;
            }

            // A companion field (e.g. rank modifiers) whose classes the preview
            // should also reflect, so a rotation/flip shows up live.
            var modifiersField = null;
            var modifiersName = root.getAttribute('data-modifiers-field');
            if (modifiersName && input.form) {
                modifiersField = input.form.querySelector('[name="' + modifiersName + '"]');
            }

            // Reflect the current icon (and any modifier classes) in the preview addon.
            function updatePreview() {
                var name = (input.value || '').trim();
                var modifiers = modifiersField ? (modifiersField.value || '').trim() : '';
                var className = 'fa fa-fw';
                if (name) {
                    className += ' fa-' + name;
                }
                if (modifiers) {
                    className += ' ' + modifiers;
                }
                previewIcon.className = className;
            }

            // Build the icon grid lazily, the first time the panel opens.
            var built = false;
            function buildGrid() {
                if (built) {
                    return;
                }
                built = true;
                var frag = document.createDocumentFragment();
                iconNames.forEach(function (name) {
                    var btn = document.createElement('button');
                    btn.type = 'button';
                    btn.className = 'btn btn-default btn-sm fa-icon-picker-option';
                    btn.title = name;
                    btn.setAttribute('data-name', name);
                    btn.innerHTML = '<i class="fa fa-fw fa-' + name + '"></i>';
                    frag.appendChild(btn);
                });
                grid.appendChild(frag);
            }

            function applyFilter(query) {
                query = (query || '').toLowerCase();
                Array.prototype.forEach.call(grid.querySelectorAll('.fa-icon-picker-option'), function (btn) {
                    var match = !query || btn.getAttribute('data-name').indexOf(query) !== -1;
                    btn.style.display = match ? '' : 'none';
                });
            }

            function openPanel() {
                buildGrid();
                panel.hidden = false;
                if (search) {
                    search.value = '';
                    applyFilter('');
                    search.focus();
                }
            }
            function closePanel() {
                panel.hidden = true;
            }

            toggle.addEventListener('click', function () {
                if (panel.hidden) {
                    openPanel();
                } else {
                    closePanel();
                }
            });

            input.addEventListener('input', updatePreview);
            if (modifiersField) {
                modifiersField.addEventListener('input', updatePreview);
            }

            grid.addEventListener('click', function (event) {
                var btn = event.target.closest('.fa-icon-picker-option');
                if (!btn) {
                    return;
                }
                input.value = btn.getAttribute('data-name');
                updatePreview();
                closePanel();
                // Let any other listeners (validation, dirty-tracking) see the change.
                input.dispatchEvent(new Event('change', { bubbles: true }));
            });

            if (search) {
                search.addEventListener('input', function () {
                    applyFilter(search.value);
                });
            }

            // Clicking away from the widget closes the panel.
            document.addEventListener('click', function (event) {
                if (!root.contains(event.target)) {
                    closePanel();
                }
            });

            updatePreview();
        });
    });
})();
