/*
 * Картите реагират на мишката: картата на играча ([data-holo]) и картите на
 * мисиите ([data-tilt]) леко се накланят, а холографският отблясък следва
 * показалеца. Само външен вид – без мишка (телефон) или при „намалено
 * движение“ в настройките на устройството картите стоят неподвижни.
 */
(function () {
  "use strict";

  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  if (!window.matchMedia("(hover: hover)").matches) return;

  function follow(card, strength) {
    card.addEventListener("pointermove", function (event) {
      const box = card.getBoundingClientRect();
      const x = (event.clientX - box.left) / box.width;   // 0 … 1
      const y = (event.clientY - box.top) / box.height;
      card.style.setProperty("--mx", (x * 100).toFixed(1) + "%");
      card.style.setProperty("--my", (y * 100).toFixed(1) + "%");
      card.style.setProperty("--rx", ((0.5 - y) * strength).toFixed(2) + "deg");
      card.style.setProperty("--ry", ((x - 0.5) * strength).toFixed(2) + "deg");
    });
    card.addEventListener("pointerleave", function () {
      ["--mx", "--my", "--rx", "--ry"].forEach(function (name) { card.style.removeProperty(name); });
    });
  }

  document.querySelectorAll("[data-holo]").forEach(function (card) { follow(card, 12); });
  document.querySelectorAll("[data-tilt]").forEach(function (card) { follow(card, 8); });
})();
