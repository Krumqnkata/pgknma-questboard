/*
 * Бутонът за светла и тъмна тема. Изборът се пази в браузъра (localStorage),
 * а първоначалната тема се задава в <head> на base.html.
 */
(function () {
  "use strict";

  // Комплектът за интерфейса: „Училищен“ или „Геймърски“ (static/css/gamer.css).
  const buttons = document.querySelectorAll("[data-kit-set]");
  function showKit() {
    const kit = document.documentElement.dataset.kit || "school";
    buttons.forEach(function (item) {
      item.setAttribute("aria-pressed", item.dataset.kitSet === kit ? "true" : "false");
    });
  }
  buttons.forEach(function (item) {
    item.addEventListener("click", function () {
      if (item.dataset.kitSet === "gamer") document.documentElement.dataset.kit = "gamer";
      else delete document.documentElement.dataset.kit;
      try { localStorage.setItem("qb-kit", item.dataset.kitSet); } catch (error) { /* напр. частен режим */ }
      showKit();
    });
  });
  showKit();

  const root = document.documentElement;
  const button = document.querySelector("[data-theme-toggle]");
  if (!button) return;

  function show(theme) {
    button.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
  }

  show(root.dataset.theme);

  button.addEventListener("click", function () {
    const next = root.dataset.theme === "dark" ? "light" : "dark";
    root.dataset.theme = next;
    try { localStorage.setItem("qb-theme", next); } catch (error) { /* напр. частен режим */ }
    show(next);
  });
})();
