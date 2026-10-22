"use strict";
// Runs before the stylesheet so the initial paint matches the system theme.
(() => {
  const system = window.matchMedia("(prefers-color-scheme: dark)");
  let preference = "system";
  function apply() {
    document.documentElement.dataset.theme = preference === "system"
      ? (system.matches ? "dark" : "light") : preference;
  }
  apply();
  system.addEventListener("change", apply);
  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("theme-picker").addEventListener("change", (event) => {
      preference = event.target.value;
      apply();
    });
  });
})();
