// Показва картата „Браво!“ при ново ниво или значка (templates/web/_celebrate.html).
// <dialog> с showModal() пази фокуса вътре и се затваря с Esc – достъпно и с клавиатура.
(function () {
  var dialog = document.getElementById("celebrate");
  if (dialog && typeof dialog.showModal === "function") {
    dialog.showModal();
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog) dialog.close(); // клик извън картата
    });
  }
})();
