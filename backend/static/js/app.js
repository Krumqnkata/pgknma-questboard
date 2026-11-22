// Регистрира service worker-а, за да може сайтът да се инсталира като приложение
// и да показва „Няма връзка“, когато интернетът липсва (web/views/app.py).
if ("serviceWorker" in navigator) {
  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/sw.js").catch(function () { /* без него сайтът пак работи */ });
  });
}
