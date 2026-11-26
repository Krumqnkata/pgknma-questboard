/*
 * Бутонът за светла и тъмна тема. Изборът се пази в браузъра (localStorage),
 * а първоначалната тема се задава в <head> на base.html.
 */
(function () {
  "use strict";

  // Комплектът за интерфейса: „Изчистен“ (clean.css), „Ретро“ (само style.css) или „Геймърски“ (gamer.css).
  const buttons = document.querySelectorAll("[data-kit-set]");
  function showKit() {
    const kit = document.documentElement.dataset.kit;
    buttons.forEach(function (item) {
      item.setAttribute("aria-pressed", item.dataset.kitSet === kit ? "true" : "false");
    });
  }
  buttons.forEach(function (item) {
    item.addEventListener("click", function () {
      document.documentElement.dataset.kit = item.dataset.kitSet;
      try { localStorage.setItem("qb-kit", item.dataset.kitSet); } catch (error) { /* напр. частен режим */ }
      showKit();
    });
  });
  showKit();

  // Менюто „Още“ се затваря при натискане встрани или с Escape.
  const more = document.querySelectorAll(".nav-more");
  document.addEventListener("click", function (event) {
    more.forEach(function (item) { if (!item.contains(event.target)) item.open = false; });
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") more.forEach(function (item) { item.open = false; });
  });

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
