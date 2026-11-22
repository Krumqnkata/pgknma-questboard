// Показва имената на избраните файлове до бутона „Избери файлове“ (templates/web/_form_fields.html).
document.querySelectorAll(".file-picker input[type=file]").forEach(function (input) {
  var names = input.closest(".file-picker").querySelector("[data-file-names]");
  input.addEventListener("change", function () {
    var files = Array.prototype.map.call(input.files, function (file) { return file.name; });
    names.textContent = files.length ? files.join(", ") : "Няма избрани файлове";
  });
});
