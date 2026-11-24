// Регистрира service worker-а, за да може сайтът да се инсталира като приложение
// и да показва „Няма връзка“, когато интернетът липсва (web/views/app.py).
if ("serviceWorker" in navigator) {
  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/sw.js").catch(function () { /* без него сайтът пак работи */ });
  });
}

(function () {
  // Съобщението за бисквитките се показва, докато не се натисне „Разбрах“.
  var note = document.querySelector("[data-cookie-note]");
  var seen = null;
  try { seen = localStorage.getItem("qb-cookies"); } catch (error) { /* напр. частен режим */ }
  if (note && !seen) {
    note.hidden = false;
    note.querySelector("[data-cookie-ok]").addEventListener("click", function () {
      note.hidden = true;
      try { localStorage.setItem("qb-cookies", "1"); } catch (error) { /* ще се покаже пак */ }
    });
  }
  // След изход разговорът с асистента се изчиства – на общ компютър следващият не го вижда.
  if (!document.querySelector("[data-chat]")) {
    try { sessionStorage.removeItem("qb-chat"); } catch (error) { /* няма какво да се чисти */ }
  }
})();
