"use strict";
// The demo is an input method, drawn: one editor, a composition at the caret, a candidate window,
// and the same rules as claudish/composition.py (continue types straight in; rewrite and instruct
// hold your words until you take something). Typed keys arrive through a hidden textarea, so phone
// keyboards and the browser's own input methods still work.
const $ = (id) => document.getElementById(id);
const sink = $("input");
const MAX = 512;
const MODES = ["continue", "instruct", "rewrite"];  // F7 order, as in every adapter
const HINTS = {
  continue: "Type as usual. Pause after a word: the rest of the sentence waits in grey. Tab takes it.",
  instruct: "Type what you want, then Enter. Pick a draft with 1–3.",
  rewrite: "Type something ordinary. Tab takes the rewrite; Enter keeps your words.",
};
const SAMPLES = [
  ["continue", "Thanks for the quick review on "],
  ["instruct", "decline the meeting politely, propose Thursday"],
  ["rewrite", "This is very important."],
];
const IN_BROWSER = document.querySelector('meta[name="claudish-backend"]')?.content === "browser";
let browserBackend = null;
let hosted = false;
let backend = "";
let serviceTimeout = 3;  // seconds; the service reports its backend's timeout in /health

const state = {
  committed: "",     // the app's text: what the input method has committed
  text: "",          // continue: the model's context (already in the app); else the composition
  mode: "continue",
  candidate: "",
  candidates: [],
  working: false,
  failed: false,
  revision: 0,
};
let timer = null;
let typing = null;  // a sample typing itself

function change(text) {
  state.text = text;
  state.candidate = "";
  state.candidates = [];
  state.working = state.failed = false;
  state.revision++;
}
const live = () => state.mode === "continue";
const ghost = () => live() && state.candidate.length > state.text.length && state.candidate.startsWith(state.text)
  ? state.candidate.slice(state.text.length) : "";
const choosing = () => state.mode === "instruct" && state.candidates.length > 1;
function automatic() {
  if (state.mode === "instruct") return false;
  if (live()) return Boolean(state.text) && !/[\p{L}\p{N}]$/u.test(state.text);  // a word boundary
  return true;
}
function commit(text) {
  state.committed = (state.committed + text).slice(-20000);
}

// What happens after every change: ask the model after a pause, then draw.
function changed() {
  clearTimeout(timer);
  if (automatic() && state.text.trim().length >= 3 && (!IN_BROWSER || browserBackend)) {
    const revision = state.revision;
    timer = setTimeout(() => ask(revision), 180);
  }
  render();
}

async function ask(revision) {
  if (revision !== state.revision) return;
  const text = state.text, mode = state.mode, started = performance.now();
  const controller = new AbortController();
  const limit = setTimeout(() => controller.abort(), Math.max(hosted ? 15000 : 5000, serviceTimeout * 1000 + 2000));
  setStatus(mode === "instruct" ? (hosted ? "working remotely…" : "working…") : "");
  try {
    let data;
    if (IN_BROWSER) {
      if (!browserBackend) throw new Error("Run the model above first.");
      data = await browserBackend.suggest(text, mode);
    } else {
      const response = await fetch("/suggest", {method: "POST", headers: {"Content-Type": "application/json"},
                                                body: JSON.stringify({text, mode}), signal: controller.signal});
      data = await response.json();
      if (!response.ok) throw new Error(data.error || "The model could not answer.");
    }
    if (revision !== state.revision) return;  // you typed since: a stale answer never lands
    state.candidate = data.text;
    state.candidates = (data.candidates || [data.text]).slice(0, 9);
    state.working = false;
    const elapsed = Math.round(performance.now() - started);
    $("timing").textContent = data.backend === "browser" ? `${elapsed} ms in this browser`
      : `${elapsed} ms · ${data.backend === "rules" ? "rules, no model" : hosted ? "hosted model" : "local model"}`;
    setStatus("");
  } catch (error) {
    if (revision !== state.revision) return;
    state.working = false;
    state.failed = true;
    setStatus(error.name === "AbortError" ? "The model took too long; your words are still here."
      : `${error.message} Your words are still here.`);
  } finally {
    clearTimeout(limit);
    render();
  }
}

// Keys, as an input method sees them. Returns true when the key was taken.
function key(name) {
  flash(name);
  if (name === "F7") {
    const enteringLive = state.mode === "rewrite" && state.text;
    if (enteringLive) commit(state.text);  // continue types into the app: the held words go in
    const leavingLive = live();
    state.mode = MODES[(MODES.indexOf(state.mode) + 1) % MODES.length];
    change(leavingLive ? "" : state.text);
    showMode();
    changed();
    return true;
  }
  if (live()) return liveKey(name);
  if (choosing() && /^[1-9]$/.test(name)) {
    const picked = state.candidates[Number(name) - 1];
    if (picked !== undefined) { commit(picked); change(""); changed(); }
    return true;
  }
  if (name === "Enter") {
    if (!state.text) { commit("\n"); render(); return true; }
    if (state.mode === "instruct" && !state.candidate) {
      if (!state.working) { state.working = true; state.failed = false; render(); ask(state.revision); }
      return true;  // the first Enter sends; the next inserts the result
    }
    commit(state.mode === "instruct" ? state.candidate : state.text);
    change(""); changed();
    return true;
  }
  if (name === "Tab") {
    if (!state.text) return false;
    if (state.candidate) { commit(state.candidate); change(""); changed(); }
    return true;  // rewrite: a pending candidate is not stale text, so Tab waits for it
  }
  if (name === "Escape") {
    if (!state.text) return false;
    commit(state.text); change(""); changed();
    return true;
  }
  if (name === "Backspace") {
    if (state.text) { change(state.text.slice(0, -1)); changed(); }
    else { state.committed = state.committed.slice(0, -1); render(); }
    return true;
  }
  if (name.length === 1) {
    if (state.text.length >= MAX) { commit(state.text); change(""); }
    change(state.text + (name === "-" && state.mode === "rewrite" ? "—" : name));
    changed();
    return true;
  }
  return false;
}

function liveKey(name) {
  if (name === "Tab") {
    const rest = ghost();
    if (!rest) return false;  // nothing offered: Tab is the app's
    commit(rest); change((state.text + rest).slice(-MAX)); changed();
    return true;
  }
  if (name === "Escape") {
    if (!ghost()) return false;
    state.candidate = ""; state.candidates = []; render();
    return true;
  }
  if (name === "Backspace") {
    state.committed = state.committed.slice(0, -1);
    if (state.text) change(state.text.slice(0, -1));
    changed();
    return true;
  }
  if (name === "Enter") { commit("\n"); change(""); changed(); return true; }
  if (name.length === 1) {  // exactly the key: continue types like en_US
    commit(name); change((state.text + name).slice(-MAX)); changed();
    return true;
  }
  return false;
}

// Drawing: committed text, the composition (underlined), the suggestion (grey), the caret, and the
// candidate window under the caret.
function render() {
  const composing = !live() && state.text;
  $("committed").textContent = state.committed;
  $("preedit").textContent = composing ? state.text : "";
  $("ghost").textContent = ghost();
  $("placeholder").hidden = Boolean(state.committed || state.text);
  const window = $("candidates");
  window.replaceChildren();
  const lines = [];
  if (composing && state.mode === "instruct") {
    if (state.working) lines.push(["", "working…"]);
    else if (state.failed) lines.push(["", "the request failed · Enter retries · Esc keeps your words"]);
    else if (choosing()) state.candidates.forEach((c, i) => lines.push([String(i + 1), c]));
    else if (state.candidate) lines.push(["Enter", state.candidate]);
    else lines.push(["", "Enter sends"]);
  } else if (composing && state.candidate) {
    lines.push(["Tab", state.candidate]);
  }
  window.hidden = !lines.length;
  for (const [label, text] of lines) {  // nodes, not HTML: the text comes from a model
    const row = document.createElement(label && label !== "Enter" && label !== "Tab" ? "button" : "div");
    row.className = "candidate-row";
    if (row.tagName === "BUTTON") {
      row.type = "button";
      row.addEventListener("mousedown", (event) => { event.preventDefault(); key(label); });
    }
    if (label) { const k = document.createElement("kbd"); k.textContent = label; row.append(k); }
    const span = document.createElement("span");
    span.textContent = text;
    row.append(span);
    window.append(row);
  }
  if (lines.length) {
    const foot = document.createElement("div");
    foot.className = "candidate-foot";
    foot.textContent = choosing() ? "1–3 picks · Enter takes the first · Esc keeps your words"
      : state.mode === "instruct" ? "Esc keeps your words" : "Tab takes it · Enter keeps your words";
    window.append(foot);
  }
  placeCandidateWindow();
  $("copy").disabled = $("clear").disabled = !state.committed;
}

function placeCandidateWindow() {
  const window = $("candidates");
  const editor = $("editor").getBoundingClientRect();
  const caret = $("caret").getBoundingClientRect();
  // As input methods do, the window sits under the start of the composition (or the caret).
  const start = $("preedit").getClientRects()[0] || caret;
  const left = Math.max(12, Math.min(start.left - editor.left - 8, editor.width - window.offsetWidth - 12));
  window.style.left = `${left}px`;
  window.style.top = `${caret.bottom - editor.top + 8}px`;
  sink.style.left = `${caret.left - editor.left}px`;  // the browser's own IME window follows the caret too
  sink.style.top = `${caret.top - editor.top}px`;
}

function showMode() {
  $("source-mode").textContent = state.mode;
  $("source").setAttribute("aria-label", `Input source: cd_AI, ${state.mode}. Press F7 or click to switch.`);
  $("hint").textContent = HINTS[state.mode];
}
function setStatus(text) { $("status").textContent = text; }
function flash(name) {
  const strip = document.querySelector(`[data-key="${/^[1-9]$/.test(name) ? "1" : name}"]`);
  if (!strip) return;
  strip.classList.add("pressed");
  setTimeout(() => strip.classList.remove("pressed"), 220);
}

// Input from the hidden textarea.
sink.addEventListener("keydown", (event) => {
  if (event.isComposing || event.ctrlKey || event.metaKey || event.altKey) return;
  const named = ["F7", "Tab", "Enter", "Escape", "Backspace"].includes(event.key)
    || (choosing() && /^[1-9]$/.test(event.key));
  if (named) {
    if (event.key === "Enter" && event.shiftKey) return;
    stopTyping();
    if (key(event.key)) event.preventDefault();
  }
});
sink.addEventListener("beforeinput", (event) => {
  if (event.isComposing) return;  // the browser's own IME composes; we take the result
  if (event.inputType === "insertText" && event.data) {
    event.preventDefault();
    stopTyping();
    for (const char of event.data) key(char);
  } else if (event.inputType === "insertLineBreak" || event.inputType === "insertParagraph") {
    event.preventDefault(); key("Enter");
  } else if (event.inputType === "deleteContentBackward") {
    event.preventDefault(); key("Backspace");
  }
});
sink.addEventListener("compositionend", (event) => {
  for (const char of event.data || "") key(char);
  sink.value = "";
});
$("editor").addEventListener("mousedown", (event) => {
  if (event.target.closest(".candidate-window")) return;
  event.preventDefault();
  sink.focus();
});
sink.addEventListener("focus", () => $("editor").classList.add("focused"));
sink.addEventListener("blur", () => $("editor").classList.remove("focused"));
$("source").addEventListener("click", () => { key("F7"); sink.focus(); });

// Samples type themselves, key by key, through the same path as your keys.
function stopTyping() { if (typing) { clearInterval(typing); typing = null; } }
$("samples").addEventListener("click", (event) => {
  const button = event.target.closest("[data-sample]");
  if (!button) return;
  stopTyping();
  sink.focus();
  while (state.mode !== button.dataset.mode) key("F7");
  if (state.text && !live()) { commit(state.text); change(""); }
  const chars = [...button.dataset.sample];
  typing = setInterval(() => {
    if (!chars.length) {
      stopTyping();
      if (button.dataset.mode === "instruct") key("Enter");
      return;
    }
    key(chars.shift());
  }, 45);
});
function renderSamples() {
  const buttons = SAMPLES.map(([mode, sample]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.mode = mode;
    button.dataset.sample = sample;
    const tag = document.createElement("span");
    tag.className = "sample-mode";
    tag.textContent = mode;
    button.append(tag, " " + sample.trim() + " ↗");
    return button;
  });
  $("samples").replaceChildren($("samples-label"), ...buttons);
}
$("copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(state.committed);
    setStatus("Copied to the clipboard.");
  } catch {
    setStatus("The clipboard is not available here.");
  }
});
$("clear").addEventListener("click", () => {
  state.committed = "";
  change("");
  changed();
  setStatus("Cleared.");
  sink.focus();
});
window.addEventListener("resize", placeCandidateWindow);

async function checkConnection() {
  try {
    const response = await fetch("/health", { signal: AbortSignal.timeout(3000) });
    if (!response.ok) throw new Error("unavailable");
    const data = await response.json();
    serviceTimeout = Number(data.timeout) || 3;
    hosted = Boolean(data.hosted);
    backend = data.backend;
    $("inference-note").textContent = hosted ? "Hosted inference, as configured." : "Actual local inference.";
    $("connection").className = "connection online";
    $("connection").replaceChildren(document.createElement("i"),
      document.createTextNode(data.backend === "rules" ? "Rules demo connected"
        : data.backend === "claude" ? "Claude API connected" : data.backend === "command" ? "Agent command connected"
        : hosted ? "Remote model connected" : "Local service connected"));
    $("backend").textContent = data.backend === "rules" ? "RULES MODE · NO MODEL"
      : data.backend === "claude" ? "cd_AI · CLAUDE API" : hosted ? "cd_AI · REMOTE MODEL" : "cd_AI · LOCAL LLM";
  } catch {
    $("connection").className = "connection offline";
    $("connection").replaceChildren(document.createElement("i"), document.createTextNode("Service unavailable"));
  }
}
async function loadInBrowser() {
  const strip = $("model-strip");
  strip.classList.add("loading");
  try {
    const templates = await (await fetch("templates.json")).json();
    const { createBrowserBackend } = await import("./browser.js");
    // ?model=URL overrides the default (tests serve a local copy); the default is pinned in the build.
    const modelUrl = new URLSearchParams(location.search).get("model") || templates.model_url;
    browserBackend = await createBrowserBackend(templates, modelUrl, (loaded, total) => {
      const percent = Math.round(100 * loaded / (total || templates.model_bytes));
      $("model-progress").value = percent;
      $("model-progress-label").textContent = `${percent}%`;
    });
    strip.classList.replace("loading", "ready");
    $("model-copy").textContent = "The model is running in this browser. Type below; nothing leaves this page.";
    $("connection").replaceChildren(document.createElement("i"), document.createTextNode("Model ready in browser"));
    $("connection").className = "connection online";
    changed();
    sink.focus();
  } catch (error) {
    strip.classList.remove("loading");
    $("load-model").textContent = "Try loading the model again";
    setStatus(`The model could not start here: ${error.message}`);
  }
}

if (IN_BROWSER && !self.crossOriginIsolated && "serviceWorker" in navigator) {
  // Threads need cross-origin isolation; coi-sw.js supplies the headers a static host cannot. One reload,
  // once: the flag in sessionStorage stops a loop if isolation still fails (then it runs single-threaded).
  let tried = false;
  try { tried = sessionStorage.getItem("claudish-coi") === "1"; sessionStorage.setItem("claudish-coi", "1"); } catch {}
  navigator.serviceWorker.register("coi-sw.js").then((registration) => {
    if (!tried && (registration.active || registration.installing)) {
      navigator.serviceWorker.ready.then(() => location.reload());
    }
  }).catch(() => {});
}

renderSamples();
showMode();
render();
if (IN_BROWSER) {
  // Nothing is downloaded until the visitor asks; the model is then cached by the browser.
  const model = document.querySelector('meta[name="claudish-model"]')?.content || "A small model";
  const strip = document.createElement("section");
  strip.id = "model-strip";
  strip.className = "model-strip";
  strip.setAttribute("aria-label", "In-browser model");
  strip.innerHTML = `<div><div class="strip-label">IN-BROWSER MODEL</div><p id="model-copy"></p></div>
    <div class="model-action"><button id="load-model" class="accept-button" type="button">Run the model in this browser</button>
    <div class="model-progress"><progress id="model-progress" max="100" value="0" aria-label="Model download"></progress>
    <span id="model-progress-label">0%</span></div></div>`;
  document.querySelector(".workspace").before(strip);
  $("model-copy").textContent = `${model} runs right here: downloaded once, then cached. Nothing you type leaves this page.`;
  $("load-model").addEventListener("click", loadInBrowser);
  $("connection").className = "connection";
  $("connection").replaceChildren(document.createElement("i"), document.createTextNode("Runs in your browser"));
  $("backend").textContent = "cd_AI · IN-BROWSER LLM";
  $("inference-note").textContent = "The model runs in this page.";
} else {
  checkConnection();
  setInterval(checkConnection, 15000);
}
