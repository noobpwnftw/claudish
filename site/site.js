"use strict";
// Copy an install line. The clipboard API needs a secure context (claudish.io is HTTPS).
document.querySelectorAll("[data-copy]").forEach((copy) => copy.addEventListener("click", async (event) => {
  const button = event.currentTarget;
  try {
    await navigator.clipboard.writeText(document.getElementById(button.dataset.copy).textContent);
    button.textContent = "Copied";
  } catch {
    button.textContent = "Select and copy";
  }
  setTimeout(() => { button.textContent = "Copy"; }, 2000);
}));
