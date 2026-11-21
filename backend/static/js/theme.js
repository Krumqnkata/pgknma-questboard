/*
 * Бутонът за светла и тъмна тема. Изборът се пази в браузъра (localStorage),
 * а първоначалната тема се задава в <head> на base.html.
 */
(function () {
  "use strict";

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
