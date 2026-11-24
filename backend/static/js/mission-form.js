// Размерът на отбора се показва само при отборна мисия (без JavaScript полетата просто са винаги видими).
(function () {
  var box = document.getElementById("id_is_group");
  if (!box) return;
  var fields = ["id_team_min", "id_team_max"].map(function (id) {
    return document.getElementById(id).closest(".field");
  });
  function update() {
    fields.forEach(function (field) { field.hidden = !box.checked; });
  }
  box.addEventListener("change", update);
  update();
})();
