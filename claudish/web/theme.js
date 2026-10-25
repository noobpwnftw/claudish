"use strict";
// Runs before the stylesheet so the initial paint matches the system theme. One button flips
// light and dark for this visit.
(() => {
  const system = window.matchMedia("(prefers-color-scheme: dark)");
  let preference = null;  // null: follow the system
  const current = () => preference || (system.matches ? "dark" : "light");
  function apply() {
    document.documentElement.dataset.theme = current();
    const button = document.getElementById("theme-toggle");
    if (button) {
      const next = current() === "dark" ? "light" : "dark";
      button.textContent = next === "dark" ? "☾" : "☀";
      button.setAttribute("aria-label", `Switch to the ${next} theme`);
      button.title = `Switch to the ${next} theme`;
    }
  }
  apply();
  system.addEventListener("change", apply);
  document.addEventListener("DOMContentLoaded", () => {
    apply();
    document.getElementById("theme-toggle").addEventListener("click", () => {
      preference = current() === "dark" ? "light" : "dark";
      apply();
    });
  });
})();
