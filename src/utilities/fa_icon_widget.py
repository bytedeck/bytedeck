from django import forms


class FontAwesomeIconPickerWidget(forms.TextInput):
    """A text input for a Font Awesome 4.7.0 icon, with a searchable icon picker
    and a live preview.

    The value stored and returned is the **bare icon name** (e.g. ``star``,
    ``forward``): the same unit the picker grid is keyed on, and what callers
    render as ``<i class="fa fa-{{ value }}"></i>``. The field stays an ordinary
    text input, so a user can still type or paste a name; the picker and the
    preview just make the icon set discoverable instead of something you have to
    know by heart.

    The icon list is loaded once from ``static/js/fa_icons_4.7.0.js``
    (``window.faIcons``), the same list the summernote editor plugin uses, so
    there is a single source of truth pinned to Font Awesome 4.7.0.
    """

    template_name = "utilities/widgets/fa_icon_picker.html"

    #: Marker class the picker JS (``static/js/fa_icon_picker.js``) hooks onto,
    #: plus ``form-control`` so the input is styled even when it is not rendered
    #: through crispy (crispy adds ``form-control`` too; a duplicate is harmless).
    input_css_class = "form-control fa-icon-picker-input"

    def __init__(self, attrs=None, modifiers_field_name=None):
        """Merge the picker's marker classes into any caller-supplied ``class``.

        :param modifiers_field_name: the form-field name of a companion field
            holding extra Font Awesome classes (rotations, flips, ...). When given,
            the live preview includes that field's value and updates as it changes.
        """
        self.modifiers_field_name = modifiers_field_name
        attrs = dict(attrs or {})
        attrs["class"] = (attrs.get("class", "") + " " + self.input_css_class).strip()
        super().__init__(attrs)

    def get_context(self, name, value, attrs):
        """Expose the companion modifiers field name to the widget template."""
        context = super().get_context(name, value, attrs)
        context["widget"]["modifiers_field_name"] = self.modifiers_field_name
        return context

    class Media:
        """The shared icon list then the picker that reads it.

        Vanilla JS (no jQuery), so include order relative to jQuery does not matter;
        the icon list only has to load before the picker, which this ordering
        guarantees.
        """

        js = ("js/fa_icons_4.7.0.js", "js/fa_icon_picker.js")


class FontAwesomeModifierPickerWidget(forms.TextInput):
    """Toggle buttons for the common Font Awesome transforms (rotate, flip, spin,
    pulse), driving a hidden field.

    The value stays a space-separated class string (e.g. ``fa-rotate-90 fa-spin``),
    so it still pairs with :class:`FontAwesomeIconPickerWidget` and its live preview.
    The buttons are the whole UI; the field itself is hidden (its raw class string
    means nothing to a user, see ``static/css/custom_common.css``) and just carries
    the value the form submits. Any class the buttons don't manage (a stack class in
    stored data, say) is preserved.
    """

    template_name = "utilities/widgets/fa_modifier_picker.html"

    input_css_class = "form-control fa-modifier-picker-input"

    def __init__(self, attrs=None):
        """Merge the picker's marker class into any caller-supplied ``class``."""
        attrs = dict(attrs or {})
        attrs["class"] = (attrs.get("class", "") + " " + self.input_css_class).strip()
        super().__init__(attrs)

    class Media:
        """The vanilla-JS behaviour that turns the toggle buttons into the class string."""

        js = ("js/fa_modifier_picker.js",)
