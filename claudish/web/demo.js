"use strict";
// The demo is an input method, drawn: one editor, a composition at the caret, a candidate window,
// and the same rules as claudish/composition.py (continue types straight in; rewrite and instruct
// hold your words until you take something). Typed keys arrive through a hidden textarea, so phone
// keyboards and the browser's own input methods still work.
const $ = (id) => document.getElementById(id);
const sink = $("input");
// Rendered by moving these nodes around the text; held here so they are never lost from a render.
const PREEDIT = $("preedit"), CARET = $("caret"), GHOST = $("ghost"), PLACEHOLDER = $("placeholder");
const MAX = 512;
const MODES = ["continue", "instruct", "rewrite"];  // F7 order, as in every adapter
const HINTS = {
  continue: "Type as usual. Pause after a word: the rest of the sentence waits in grey. Tab takes it.",
  instruct: "Type what you want, then Enter. Pick a draft with 1–3.",
  rewrite: "Type something ordinary. Tab rewrites it in place; Tab again keeps it, Esc brings your words back.",
};
const SAMPLES = [
  ["rewrite", "This is very important."],
  ["continue", "Thanks for the quick review on "],
  ["instruct", "decline the meeting politely, propose Thursday"],
];
const IN_BROWSER = document.querySelector('meta[name="claudish-backend"]')?.content === "browser";
let browserBackend = null;
let hosted = false;
let backend = "";
let serviceTimeout = 3;  // seconds; the service reports its backend's timeout in /health

// The app's text box: its text, the caret, and the selection anchor (anchor == caret: no selection).
const doc = {text: "", caret: 0, anchor: 0};
const selection = () => [Math.min(doc.caret, doc.anchor), Math.max(doc.caret, doc.anchor)];
const selected = () => doc.caret !== doc.anchor;
function removeSelection() {
  const [start, end] = selection();
  doc.text = doc.text.slice(0, start) + doc.text.slice(end);
  doc.caret = doc.anchor = start;
}
function moveTo(index, extend) {
  doc.caret = Math.max(0, Math.min(index, doc.text.length));
  if (!extend) doc.anchor = doc.caret;
}

const state = {
  text: "",          // continue: the model's context (already in the text box); else the composition
  mode: "rewrite",   // the demo opens with the pitch; the installed input method starts in continue
  candidate: "",
  candidates: [],
  converted: false,  // rewrite: Tab showed the rewrite in place of your words
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
  state.converted = false;
  state.working = state.failed = false;
  state.revision++;
}
const live = () => state.mode === "continue";
const composing = () => !live() && Boolean(state.text);
const shown = () => state.converted ? state.candidate : state.text;
const ghost = () => live() && !selected() && state.candidate.length > state.text.length
  && state.candidate.startsWith(state.text) ? state.candidate.slice(state.text.length) : "";
const choosing = () => state.mode === "instruct" && state.candidates.length > 1;
function automatic() {
  if (state.mode === "instruct") return false;
  // Continue asks at a word boundary, not at the start of an empty line.
  if (live()) return Boolean(state.text) && !/[\p{L}\p{N}\n]$/u.test(state.text);
  return true;
}
// Continue's context is the text before the caret, as an input method reads the app's surrounding
// text: typed, pasted, or already there.
const context = () => doc.text.slice(Math.max(0, doc.caret - MAX), doc.caret);
// Committing inserts at the caret, replacing any selection, as typing into a text box does.
function commit(text) {
  if (selected()) removeSelection();
  doc.text = (doc.text.slice(0, doc.caret) + text + doc.text.slice(doc.caret)).slice(0, 20000);
  moveTo(doc.caret + text.length);
}
// Before the caret moves, a selection is edited, or a shortcut runs, the input method commits your
// words (navigation and shortcuts end a composition) and continue starts a fresh context.
function settle() {
  if (composing()) commit(state.text);
  change(live() ? context() : "");
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
    if (mode === "continue") return;  // continue stays quiet: no suggestion is a fine answer
    state.failed = true;
    setStatus(error.name === "AbortError" ? "The model took too long; your words are still here."
      : `${error.message} Your words are still here.`);
  } finally {
    clearTimeout(limit);
    render();
  }
}

// Keys, as an input method sees them. Returns true when the key was taken.
function key(name, shift = false) {
  flash(name);
  if (name === "F7") {
    if (state.mode === "rewrite" && state.text) commit(state.text);  // continue types into the box
    const leavingLive = live();
    state.mode = MODES[(MODES.indexOf(state.mode) + 1) % MODES.length];
    change(live() ? context() : leavingLive ? "" : state.text);
    showMode();
    changed();
    return true;
  }
  if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(name)) {
    settle();
    const lineStart = doc.text.lastIndexOf("\n", doc.caret - 1) + 1;
    const lineEnd = doc.text.indexOf("\n", doc.caret) < 0 ? doc.text.length : doc.text.indexOf("\n", doc.caret);
    const [start, end] = selection();
    const target = name === "Home" ? lineStart : name === "End" ? lineEnd
      : selected() && !shift ? (name === "ArrowLeft" ? start : end)
      : doc.caret + (name === "ArrowLeft" ? -1 : 1);
    moveTo(target, shift);
    changed();
    return true;
  }
  if (name === "Delete") {
    if (composing()) return true;
    if (selected()) removeSelection(); else doc.text = doc.text.slice(0, doc.caret) + doc.text.slice(doc.caret + 1);
    change(live() ? context() : ""); changed();
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
    commit(state.mode === "instruct" || state.converted ? state.candidate : state.text);
    change(""); changed();
    return true;
  }
  if (name === "Tab") {
    if (!state.text) return false;
    // Rewrite: the first Tab converts your words in place, the second keeps it. A pending
    // candidate is not stale text, so Tab waits for it.
    if (state.mode === "rewrite" && state.candidate && !state.converted) { state.converted = true; render(); }
    else if (state.candidate) { commit(state.candidate); change(""); changed(); }
    return true;
  }
  if (name === "Escape") {  // one step back
    if (!state.text) return false;
    if (state.converted) { state.converted = false; render(); return true; }  // your words again
    if (state.mode === "instruct") {
      // Drafts showing or an answer pending: back to the instruction, to refine and send again.
      // Otherwise the instruction is dropped: it is not text you meant to write.
      change(state.candidates.length || state.working || state.failed ? state.text : "");
      render();
      return true;
    }
    commit(state.text); change(""); changed();
    return true;
  }
  if (name === "Backspace") {
    if (state.converted) { state.converted = false; render(); return true; }  // your words again
    if (state.text) change(state.text.slice(0, -1));
    else if (selected()) removeSelection();
    else if (doc.caret) { doc.text = doc.text.slice(0, doc.caret - 1) + doc.text.slice(doc.caret); moveTo(doc.caret - 1); }
    changed();
    return true;
  }
  if (name.length === 1) {
    if (selected() && !state.text) removeSelection();  // typing replaces the selection
    if (!state.text && /\s/.test(name)) { commit(name); changed(); return true; }  // nothing composed: the app's
    if (state.converted) { commit(state.candidate); change(""); }  // typing on keeps the rewrite
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
    // Taking it is not a pause in your writing: nothing more until you type again (asking at once
    // made the model repeat its sentence ending).
    commit(rest); change(context()); render();
    return true;
  }
  if (name === "Escape") {
    if (!ghost()) return false;
    state.candidate = ""; state.candidates = []; render();
    return true;
  }
  if (name === "Backspace") {
    if (selected()) removeSelection();
    else if (doc.caret) { doc.text = doc.text.slice(0, doc.caret - 1) + doc.text.slice(doc.caret); moveTo(doc.caret - 1); }
    change(context()); changed();
    return true;
  }
  if (name === "Enter") { commit("\n"); change(context()); changed(); return true; }
  if (name.length === 1) {  // exactly the key: continue types like en_US
    commit(name); change(context()); changed();
    return true;
  }
  return false;
}

// Drawing: the text box's text (with the selection), and at the caret the composition (underlined),
// the caret, and the suggestion (grey); the candidate window sits under the composition.
function segment(text, start, className) {
  const span = document.createElement("span");
  span.className = "seg" + (className ? " " + className : "");
  span.dataset.start = start;
  span.textContent = text;
  return span;
}
function render() {
  const page = $("page");
  page.dataset.text = doc.text;
  const [start, end] = selection();
  const preedit = PREEDIT, caret = CARET, suggestion = GHOST;
  preedit.textContent = composing() ? shown() : "";
  preedit.classList.toggle("converted", state.converted);
  suggestion.textContent = ghost();
  const nodes = [];
  if (selected()) {
    const atCaret = [preedit, caret, suggestion];  // empty while a selection shows, but kept in the page
    nodes.push(segment(doc.text.slice(0, start), 0), ...(doc.caret === start ? atCaret : []),
               segment(doc.text.slice(start, end), start, "selected"), ...(doc.caret === end ? atCaret : []),
               segment(doc.text.slice(end), end));
  } else {
    nodes.push(segment(doc.text.slice(0, doc.caret), 0), preedit, caret, suggestion,
               segment(doc.text.slice(doc.caret), doc.caret));
  }
  page.replaceChildren(...nodes, PLACEHOLDER);
  PLACEHOLDER.hidden = Boolean(doc.text || state.text);
  const window = $("candidates");
  window.replaceChildren();
  const lines = [];
  if (composing() && state.mode === "instruct") {
    if (state.working) lines.push(["", "working…"]);
    else if (state.failed) lines.push(["", "the request failed · Enter retries · Esc goes back"]);
    else if (choosing()) state.candidates.forEach((c, i) => lines.push([String(i + 1), c]));
    else if (state.candidate) lines.push(["Enter", state.candidate]);
    else lines.push(["", "Enter sends"]);
  } else if (composing() && state.candidate) {
    // Rewrite has no list: a hint that it is ready, then the rewrite itself in place of your words.
    lines.push(["Tab", state.converted ? "keep the rewrite" : "rewrite it"]);
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
    foot.textContent = choosing() ? "1–3 picks · Enter takes the first · Esc: back to the instruction"
      : state.mode === "instruct" ? (state.working || state.failed ? "Esc: back to the instruction" : "Esc drops it")
      : state.converted ? "Enter keeps it too · Esc: your words" : "Enter or Esc keeps your words";
    window.append(foot);
  }
  placeCandidateWindow();
  $("copy").disabled = $("clear").disabled = !doc.text;
}

function placeCandidateWindow() {
  const window = $("candidates");
  const editor = $("editor").getBoundingClientRect();
  const caret = CARET.getBoundingClientRect();
  // As input methods do, the window sits under the start of the composition (or the caret).
  const start = PREEDIT.getClientRects()[0] || caret;
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
  if (event.isComposing) return;
  if (event.ctrlKey || event.metaKey) {
    if (event.altKey) return;
    settle();  // a shortcut ends a composition: your words go in first
    if (event.key.toLowerCase() === "a") { event.preventDefault(); doc.anchor = 0; doc.caret = doc.text.length; }
    changed();
    return;  // copy, cut, and paste arrive as events below
  }
  if (event.altKey) return;
  const named = ["F7", "Tab", "Enter", "Escape", "Backspace", "Delete", "ArrowLeft", "ArrowRight", "Home", "End"]
    .includes(event.key) || (choosing() && /^[1-9]$/.test(event.key));
  if (named) {
    if (event.key === "Enter" && event.shiftKey) return;
    stopTyping();
    if (key(event.key, event.shiftKey)) event.preventDefault();
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
  } else if (event.inputType === "deleteContentForward") {
    event.preventDefault(); key("Delete");
  } else if (event.inputType === "insertFromPaste" || event.inputType === "insertFromDrop") {
    // Some browsers deliver a paste only as an input event: same as the paste handler below.
    event.preventDefault();
    paste(event.dataTransfer?.getData("text/plain") || event.data || "");
  }
});
sink.addEventListener("compositionend", (event) => {
  for (const char of event.data || "") key(char);
  sink.value = "";
});
function clip(event, cut) {
  if (!selected()) return;
  const [start, end] = selection();
  event.clipboardData.setData("text/plain", doc.text.slice(start, end));
  event.preventDefault();
  if (cut) { removeSelection(); change(""); changed(); }
}
sink.addEventListener("copy", (event) => clip(event, false));
sink.addEventListener("cut", (event) => clip(event, true));
function paste(text) {
  stopTyping();
  if (!live() && text && (state.text + text).length <= MAX) {
    // Rewrite and instruct: pasted words join the composition, to be rewritten (Tab) or sent
    // (Enter) like typed ones. The installed input method's counterpart is a selection.
    if (selected() && !state.text) removeSelection();
    if (state.converted) { commit(state.candidate); change(""); }
    change(state.text + text);
    changed();
    return;
  }
  if (composing()) commit(state.text);
  commit(text.slice(0, 5000));
  change(live() ? context() : "");
  changed();
  if (!live() && text) setStatus(`Pasted as is: ${MAX} characters is the most ${state.mode} takes at once.`);
}
sink.addEventListener("paste", (event) => {
  event.preventDefault();
  paste(event.clipboardData.getData("text/plain") || "");
});

// The mouse: click places the caret, a drag selects, a double click selects a word, Shift extends.
function offsetAt(x, y) {
  let node, offset;
  if (document.caretPositionFromPoint) {
    const position = document.caretPositionFromPoint(x, y);
    if (position) { node = position.offsetNode; offset = position.offset; }
  } else if (document.caretRangeFromPoint) {
    const range = document.caretRangeFromPoint(x, y);
    if (range) { node = range.startContainer; offset = range.startOffset; }
  }
  const seg = node && (node.nodeType === 3 ? node.parentElement : node)?.closest?.(".seg");
  if (seg) return Number(seg.dataset.start) + Math.min(offset, seg.textContent.length);
  if (node && node.closest?.(".preedit, .caret, .ghost")) return doc.caret;
  return doc.text.length;  // below or beside the text: the end
}
let dragging = false;
$("editor").addEventListener("mousedown", (event) => {
  if (event.target.closest(".candidate-window")) return;
  event.preventDefault();  // any button keeps the keyboard here (a right click used to lose it)
  sink.focus();
  if (event.button !== 0) return;
  stopTyping();
  settle();
  const at = offsetAt(event.clientX, event.clientY);
  if (event.detail === 2) {  // a word
    const before = doc.text.slice(0, at).match(/[\p{L}\p{N}_'-]*$/u)[0].length;
    const after = doc.text.slice(at).match(/^[\p{L}\p{N}_'-]*/u)[0].length;
    doc.anchor = at - before;
    doc.caret = at + after;
  } else {
    moveTo(at, event.shiftKey);
    dragging = true;
  }
  changed();
});
document.addEventListener("mousemove", (event) => {
  if (!dragging) return;
  if (!(event.buttons & 1)) { dragging = false; return; }
  moveTo(offsetAt(event.clientX, event.clientY), true);
  render();
});
document.addEventListener("mouseup", () => { dragging = false; });
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
  settle();
  while (state.mode !== button.dataset.mode) key("F7");
  if (doc.text && !doc.text.endsWith("\n")) commit("\n");
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
  const [start, end] = selection();
  try {
    await navigator.clipboard.writeText(selected() ? doc.text.slice(start, end) : doc.text);
    setStatus(selected() ? "Copied the selection." : "Copied to the clipboard.");
  } catch {
    setStatus("The clipboard is not available here.");
  }
});
$("clear").addEventListener("click", () => {
  doc.text = "";
  moveTo(0);
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
    // Revalidated: Pages caches for 10 minutes, and stale templates after a deploy can drop every answer.
    const templates = await (await fetch("templates.json", { cache: "no-cache" })).json();
    const { createBrowserBackend } = await import("./browser.js");
    // ?model=URL overrides the default (tests serve a local copy); the default is pinned in the build.
    const modelUrl = new URLSearchParams(location.search).get("model") || templates.model_url;
    let note = "";
    browserBackend = await createBrowserBackend(templates, modelUrl, (loaded, total) => {
      const percent = Math.round(100 * loaded / (total || templates.model_bytes));
      $("model-progress").value = percent;
      $("model-progress-label").textContent = `${percent}%`;
    }, (text) => { note = text; });
    strip.classList.replace("loading", "ready");
    $("model-copy").textContent = note || "The model is running in this browser. Type below; nothing leaves this page.";
    $("remove-model").hidden = false;
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
    <div class="model-action"><button id="remove-model" type="button" hidden>Remove from this browser</button>
    <button id="load-model" class="accept-button" type="button">Run the model in this browser</button>
    <div class="model-progress"><progress id="model-progress" max="100" value="0" aria-label="Model download"></progress>
    <span id="model-progress-label">0%</span></div></div>`;
  document.querySelector(".workspace").before(strip);
  $("model-copy").textContent = `${model} runs in this page, and nothing you type leaves it.`;
  $("load-model").addEventListener("click", loadInBrowser);
  // Only once the model runs: it stops the model (whose files are open while it runs) and deletes them.
  $("remove-model").addEventListener("click", async () => {
    const { removeStored } = await import("./browser.js");
    try { await browserBackend.exit(); } catch {}
    browserBackend = null;
    await removeStored();
    $("remove-model").hidden = true;
    $("model-strip").classList.remove("ready");
    $("model-copy").textContent = `${model} runs in this page, and nothing you type leaves it.`;
    $("connection").className = "connection";
    $("connection").replaceChildren(document.createElement("i"), document.createTextNode("Runs in your browser"));
    setStatus("Removed the model from this browser.");
  });
  $("connection").className = "connection";
  $("connection").replaceChildren(document.createElement("i"), document.createTextNode("Runs in your browser"));
  $("backend").textContent = "cd_AI · IN-BROWSER LLM";
  $("inference-note").textContent = "The model runs in this page.";
} else {
  checkConnection();
  setInterval(checkConnection, 15000);
}
