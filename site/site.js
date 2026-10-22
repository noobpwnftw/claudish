"use strict";
// Copy the install prompt. The clipboard API needs a secure context (claudish.io is HTTPS).
document.getElementById("copy-prompt").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  try {
    await navigator.clipboard.writeText(document.getElementById("prompt-text").textContent);
    button.textContent = "Copied";
  } catch {
    button.textContent = "Select and copy";
  }
  setTimeout(() => { button.textContent = "Copy"; }, 2000);
});
