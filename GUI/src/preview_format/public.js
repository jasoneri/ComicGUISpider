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
})();
