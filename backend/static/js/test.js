/*
 * Екранът на тест: таймер, подреждане на стъпки и отбелязване, че страницата е напусната.
 * Времето тук е само за показване – решава го сървърът (quizzes/services.py).
 */
(function () {
  "use strict";

  const panel = document.querySelector("[data-test]");
  if (!panel) return;
  const form = panel.querySelector("[data-test-form]");
  const limit = parseFloat(panel.dataset.limit);
  const end = performance.now() + parseFloat(panel.dataset.left) * 1000;
  const time = panel.querySelector("[data-time]");
  const bar = panel.querySelector("[data-bar]");
  let sent = false;

  function send() {
    if (sent) return;
    sent = true;
    form.submit();
  }

  form.addEventListener("submit", function (event) {
    if (sent) { event.preventDefault(); return; }
    sent = true;
  });

  (function tick() {
    const left = Math.max(0, (end - performance.now()) / 1000);
    time.textContent = Math.ceil(left) + " s";
    bar.style.width = Math.min(100, left * 100 / limit) + "%";
    panel.classList.toggle("is-last", left <= 3);
    if (left <= 0) { send(); return; }
    setTimeout(tick, 100);
  })();

  // Подреждане: натиснатите стъпки получават номера.
  const box = panel.querySelector("[data-order]");
  if (box) {
    const value = panel.querySelector("[data-order-value]");
    const done = panel.querySelector("[data-order-send]");
    let picked = [];
    const show = function () {
      box.querySelectorAll("button").forEach(function (button) {
        const place = picked.indexOf(button.dataset.number);
        button.classList.toggle("is-picked", place >= 0);
        button.querySelector(".order-no").textContent = place >= 0 ? place + 1 : "";
      });
      value.value = picked.join(",");
      done.disabled = picked.length !== box.children.length;
    };
    box.addEventListener("click", function (event) {
      const button = event.target.closest("button");
      if (!button) return;
      const place = picked.indexOf(button.dataset.number);
      if (place >= 0) picked.splice(place, 1); else picked.push(button.dataset.number);
      show();
    });
    panel.querySelector("[data-order-reset]").addEventListener("click", function () { picked = []; show(); });
  }

  // Друг прозорец или раздел: учителят вижда колко пъти. Не се наказва автоматично.
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState !== "hidden" || sent) return;
    const data = new FormData();
    data.append("csrfmiddlewaretoken", form.querySelector("[name=csrfmiddlewaretoken]").value);
    navigator.sendBeacon(panel.dataset.leftUrl, data);
  });
})();
