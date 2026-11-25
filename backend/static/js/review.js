// Проверка на заявки: готови коментари и избор на няколко наведнъж. Без JavaScript работят полето и отметките.
(function () {
  "use strict";
  document.querySelectorAll(".quick-comments").forEach(function (box) {
    box.hidden = false;
    var input = box.closest("form").querySelector('input[name="comment"]');
    box.addEventListener("click", function (event) {
      var text = event.target.dataset.comment;
      if (!text) return;
      input.value = input.value === text ? "" : text;
      box.querySelectorAll("button").forEach(function (item) {
        item.setAttribute("aria-pressed", item.dataset.comment === input.value ? "true" : "false");
      });
    });
  });

  var all = document.querySelector("[data-bulk-all]");
  var submit = document.querySelector("[data-bulk-submit]");
  if (!submit) return;
  var picks = Array.from(document.querySelectorAll('input[name="claim"][form="bulk-form"]'));
  all.parentElement.hidden = false;
  function show() {
    var count = picks.filter(function (item) { return item.checked; }).length;
    submit.disabled = !count;
    submit.textContent = count ? "Потвърди избраните (" + count + ")" : "Потвърди избраните";
    all.checked = count === picks.length;
  }
  all.addEventListener("change", function () {
    picks.forEach(function (item) { item.checked = all.checked; });
    show();
  });
  picks.forEach(function (item) { item.addEventListener("change", show); });
  show();
})();
