// task-panel.js
(() => {
  window.scanChecked = function () {
    var selectedValues = [];
    // 2.2 clip的带章节checkbox
    if (window.selectedObjectsMap) {
      window.selectedObjectsMap.forEach((selectedObjects) => {
        selectedObjects.forEach(selected => {
          const checkbox = document.getElementById(selected.uniqueId);
          if (checkbox && checkbox.checked) {
            selectedValues.push(selected.uniqueId);
          }
        });
      });
    } else {
      // 1.普通preview的checkbox  
      // 2.clip的无章节checkbox
      const checkedBoxes = document.querySelectorAll('input[type="checkbox"]:checked');
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
  document.addEventListener('DOMContentLoaded', function() {
    const containers = document.querySelectorAll('div[style*="position: relative"]');
    containers.forEach(container => {
        const badges = container.querySelectorAll('.badge-right-top');
        let verticalOffset = 0;
        badges.forEach(badge => {
            badge.style.removeProperty('top');
            badge.style.top = `${verticalOffset}px`;
            verticalOffset += badge.offsetHeight + 2;
        });
    });
  });
})();
