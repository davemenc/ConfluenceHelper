// static/js/main.js

// Select all functionality for suggestions (we'll use this later)
function selectAllHighConfidence() {
    const checkboxes = document.querySelectorAll('input[type="checkbox"][data-confidence]');
    checkboxes.forEach(cb => {
        if (parseFloat(cb.dataset.confidence) >= 0.7) {
            cb.checked = true;
        }
    });
}

// Add confirmation before applying suggestions
function confirmApply() {
    const checkedBoxes = document.querySelectorAll('input[type="checkbox"]:checked');
    if (checkedBoxes.length === 0) {
        alert('Please select at least one suggestion to apply.');
        return false;
    }
    return confirm(`Apply ${checkedBoxes.length} suggestion(s)?`);
}