// task-panel.js
(() => {
  function reflowPreviewBadges() {
    document.querySelectorAll('.demo-badge-group').forEach((group) => {
      if (!group.children.length) {
        group.remove();
      }
    });
  }

  window.scanChecked = function () {
    var selectedValues = [];
    // 2.2 clip的带章节checkbox
    if (window.selectedObjectsMap) {
      window.selectedObjectsMap.forEach((selectedObjects) => {
        selectedObjects.forEach(selected => {
          const checkbox = document.getElementById(selected.uniqueId);
          if (checkbox && checkbox.checked && !checkbox.disabled) {
            selectedValues.push(selected.uniqueId);
          }
        });
      });
    } else {
      // 1.普通preview的checkbox  
      // 2.clip的无章节checkbox
      const checkedBoxes = document.querySelectorAll('input[type="checkbox"]:checked:not(:disabled)');
      checkedBoxes.forEach(checkbox => {
        if (checkbox.id) {
          selectedValues.push(checkbox.id);
        }
      });
    }

    return selectedValues;
  }
  window.get_curr_hml = function () {
    return document.documentElement.outerHTML;
  }
  window.reflowPreviewBadges = reflowPreviewBadges;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', reflowPreviewBadges, { once: true });
  } else {
    reflowPreviewBadges();
  }
})();
