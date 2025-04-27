// task-panel.js
(() => {
  window.scanChecked = function () {
    var checkboxGroup = document.getElementsByName('img');
    var selectedValues = [];
    for (let i = 0; i < checkboxGroup.length; i++) {
      if (checkboxGroup[i].checked) {
        selectedValues.push(checkboxGroup[i].id);
      }
    }
    return selectedValues
  }
  window.get_curr_hml = function () {
    return document.documentElement.outerHTML;
  }
  document.addEventListener('DOMContentLoaded', function() {
    const containers = document.querySelectorAll('div[style*="position: relative"]');
    containers.forEach(container => {
        const badges = container.querySelectorAll('.badge-on-img');
        let verticalOffset = 0;
        badges.forEach(badge => {
            badge.style.removeProperty('top');
            badge.style.top = `${verticalOffset}px`;
            verticalOffset += badge.offsetHeight + 2;
        });
    });
  });
})();
