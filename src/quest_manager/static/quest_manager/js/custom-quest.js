$(document).ready(function() {
    // Bulk edit helpers

    // Submit the bulk action form with a given action type
    window.submitBulkAction = function(actionType) {
        const form = document.getElementById("bulk-edit-form");
        const actionInput = document.getElementById("bulk-action-type");
        if (form && actionInput) {
            actionInput.value = actionType;
            form.submit();
        }
    };

    // Toggle all checkboxes for bulk edit
    window.toggleAllCheckboxes = function(source) {
        const checkboxes = document.querySelectorAll('input[name="selected_quests[]"]');
        checkboxes.forEach(cb => cb.checked = source.checked);
    };

});
