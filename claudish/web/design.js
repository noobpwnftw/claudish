"use strict";
// The design lab: every state cd_AI shows at the caret (STATES), drawn with kit.css in a mock of
// each platform (SKINS). The words are the shared ones from claudish/composition.py (hint) and the
// service (questions and their choices). ?platform=windows&state=drafts&solo shows one mock alone,
// at its native size, for comparing with a screenshot of the real input method.

const SKINS = {
  reference: {name: "Reference", note: "The demo's look."},
  windows: {name: "Windows 11", note: "Claudish's PIME draws the panel and the suggestion.", app: "Notepad"},
  macos: {name: "macOS", note: "cd_AI's own panel and suggestion overlay (platforms/macos/panel.py).", app: "TextEdit"},
  gnome: {name: "GNOME", note: "A GNOME Shell extension draws the panel and the suggestion, on X11 and Wayland alike.", app: "Text Editor"},
};

// Each state: the text box around the caret (before it, your composition, the gray suggestion)
// and a note. What cd_AI draws there is generated: lab-states.js holds the panel of every state,
// made by driving claudish/composition.py into it (scripts/lab_states.py), so the lab draws what
// the input method draws.
const STATES = [
  {id: "continue", title: "Continue: a suggestion", note: "The rest of the sentence after the caret, in gray. Tab takes it; typing ignores it.", before: "Thanks for the review — I'll", ghost: " send the revised draft by Friday."},
  {id: "compose", title: "Compose: typing", note: "Your words, composed. The keys show from the first key.", before: "Team: ", comp: "running late, start without me"},
  {id: "rewriting", title: "Compose: rewriting", note: "The model works on the rewrite.", before: "Team: ", comp: "running late, start without me"},
  {id: "converted", title: "Compose: a rewrite", note: "The rewrite shows in the panel; Tab puts it in.", before: "Team: ", comp: "running late, start without me"},
  {id: "sent", title: "An instruction, sent", note: "Shift+Enter sent it. The instruction stays underlined at the caret; the panel says what is happening.", before: "Hi Sam, ", comp: "decline the offsite politely"},
  {id: "drafts", title: "An instruction's drafts", note: "Three readings, your instruction still underlined at the caret. The first is highlighted; ↓ moves; Tab inserts it.", before: "Hi Sam, ", comp: "decline the offsite politely"},
  {id: "nudged", title: "Enter on a draft", note: "Enter does nothing once the model is asked; on a draft it lights the row's Tab until your next key.", before: "Hi Sam, ", comp: "decline the offsite politely"},
  {id: "ask", title: "The model asks", note: "Its question, your instruction still at the caret. Tab takes the highlighted choice, ↓ moves it; or just type.", before: "", comp: "summarize this thread"},
  {id: "reply", title: "Typing a reply", note: "What you type takes your instruction's place at the caret: your reply. The panel now says what you asked; the choices fade.", before: "", comp: "only the last two days", anchor: "comp"},
  {id: "answered", title: "Answered", note: "Your instruction is the composition again, so the panel says only what you answered while the model works on.", before: "", comp: "summarize this thread"},
  {id: "permission", title: "An approval", note: "The call, in full. Nothing is highlighted; the first ↓ lands on Deny; Allow is ↓↓ Tab.", before: "", comp: "push my branch"},
  {id: "handoff", title: "A handoff", note: "Sending a task to a helper is asked the same way: the first ↓ keeps it here.", before: "", comp: "have claude fix the failing parser test"},
  {id: "answer", title: "An answer to read", note: "Several sentences, wrapped to a readable width. Tab puts it in your text.", before: "", comp: "what does this error mean"},
  {id: "progress", title: "An agent at work", note: "One line: what it is doing, and how to stop it.", before: "", comp: "fix the failing parser test"},
  {id: "failed", title: "A failed request", note: "The panel says why; Shift+Enter sends it again, Esc brings your instruction back to the caret.", before: "Hi Sam, ", comp: "decline the offsite politely"},
  {id: "terminal", title: "In a terminal", note: "Continue is quiet on a command line; an instruction offers commands.", before: "~/claudish $ ", comp: "undo my last commit but keep the changes", terminal: true},
  {id: "dropped", title: "Esc dropped something", note: "A drop or a clear says so briefly, with the key that brings it back.", before: "Hi Sam, ", toast: true},
  {id: "returned", title: "Back in the text box", note: "You switched windows mid-exchange: your instruction went in as you typed it (as a CJK preedit does) and the exchange was held. A pill says what waits; it takes no keys until Shift+Esc opens it.", before: "Hi Sam, decline the offsite politely", toast: true},
  {id: "mode-compose", title: "A mode switch: compose", note: "A Shift tap: the mode, and where Shift goes next, briefly at the caret. The taskbar or menu bar shows it all along.", before: "Thanks for the review — I'll", toast: true},
  {id: "mode-continue", title: "A mode switch: continue", note: "And back: a neutral tile, so only compose wears the accent.", before: "Thanks for the review — I'll", toast: true},
];

// Key names: the platform's own (a skin token). macOS menus show glyphs, without boxes.
const KEYS = {macos: {Enter: "↩", Esc: "esc", Tab: "⇥", Shift: "⇧", "Shift+Enter": "⇧↩", "Shift+Esc": "⇧esc"}};

const $ = (id) => document.getElementById(id);
const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

// The host: a window of the platform's own kind with a text box, the caret in it.
function frame(skin, state) {
  const host = el("div", `host ${skin}` + (state.terminal ? " terminal" : ""));
  if (state.anchor) host.dataset.anchor = state.anchor;
  const bar = el("div", "host-bar");
  const app = state.terminal ? {windows: "Terminal", macos: "Terminal", gnome: "Console", reference: "TERMINAL"}[skin]
    : SKINS[skin].app || "NOTES";
  if (skin === "macos") bar.append(el("span", "lights"));
  bar.append(el("span", "host-title", app));
  if (skin === "windows") bar.append(el("span", "caption"));
  if (skin === "gnome") bar.append(el("span", "close"));
  const text = el("div", "host-text kit");
  const line = el("div", "host-line");
  line.append(state.before);
  const anchor = el("span", "anchor");
  if (state.comp) anchor.append(el("span", "k-comp", state.comp));
  line.append(anchor, el("span", "host-caret"));
  if (state.ghost) {  // a space typed before the suggestion is the app's text, in its font
    const lead = /^\s*/.exec(state.ghost)[0];
    line.append(lead, el("span", "k-ghost", state.ghost.slice(lead.length)));
  }
  text.append(line);
  // What cd_AI draws: the panel (or, for a toast, a panel with only a footer) composition.py made.
  const spec = (window.LAB_STATES || {})[state.id];
  if (spec) text.append(state.toast ? Kit.toast(spec, KEYS[skin] || {}) : Kit.panel(spec, KEYS[skin] || {}));
  host.append(bar, text);
  return host;
}

// Under the line, the panel's content starting at the composition's start, or at the caret.
function place(host) {
  const text = host.querySelector(".host-text");
  const anchor = host.querySelector(".anchor");
  const caret = host.querySelector(".host-caret");
  const box = text.getBoundingClientRect();
  const line = caret.getBoundingClientRect();
  // A panel's content starts where the composition starts (what IMK, TSF and IBus report while
  // something is composed), else at the caret; it stays where it opened while it is open.
  const opened = anchor.firstChild ? anchor.firstChild.getClientRects()[0] : null;
  const start = opened ? {left: opened.left, right: opened.left} : {left: line.right, right: line.right};
  const lineBottom = line.bottom;
  for (const floating of host.querySelectorAll(".k-panel, .k-toast")) {
    const style = getComputedStyle(floating);
    const inset = parseFloat(style.paddingLeft) + parseFloat(style.borderLeftWidth)
      + (floating.classList.contains("k-panel") ? parseFloat(getComputedStyle(floating).getPropertyValue("--k-row-x")) || 0 : 0);
    // Kept inside the card (a narrow screen's card is narrower than the panel's own width).
    const edge = Math.min(host.getBoundingClientRect().right, document.documentElement.clientWidth);
    floating.style.maxWidth = `${edge - Math.max(box.left, 0) - 16}px`;
    const left = Math.max(8 - box.left, Math.min(start.left - box.left - inset,
                                                 edge - box.left - floating.offsetWidth - 8));
    floating.style.left = `${left}px`;
    floating.style.top = `${lineBottom - box.top + 6}px`;
    // The window is as tall as what it shows, with the same margin below as above.
    text.style.height = `${Math.max(190, lineBottom - box.top + 6 + floating.offsetHeight + 28)}px`;
  }
}

function render() {
  const params = new URLSearchParams(location.search);
  const skin = SKINS[location.hash.slice(1)] ? location.hash.slice(1) : params.get("platform") || "reference";
  document.body.dataset.skin = skin;
  const nav = $("platforms");
  nav.replaceChildren(...Object.entries(SKINS).map(([id, info]) => {
    const link = el("a", id === skin ? "on" : "", info.name);
    link.href = `#${id}`;
    if (id === skin) link.setAttribute("aria-current", "page");
    return link;
  }), el("span", "platform-note", SKINS[skin].note));
  const only = params.get("state");
  const sheet = $("sheet");
  sheet.replaceChildren();
  const solo = params.has("solo");
  document.body.classList.toggle("solo", solo);
  for (const state of STATES.filter((s) => !only || s.id === only)) {
    const card = el("article", "card");
    card.id = state.id;
    if (!solo) {
      const head = el("header", "card-head");
      head.append(el("h2", "", state.title), el("p", "", state.note));
      card.append(head);
    }
    const host = frame(skin, state);
    card.append(host);
    sheet.append(card);
  }
  if (!solo && !only) sheet.after(feasibility());
  document.querySelectorAll(".drawn").forEach((node, index) => index && node.remove());
  requestAnimationFrame(() => document.querySelectorAll(".host").forEach(place));
}

const DRAWN = [
  ["The suggestion after the caret", "a layered overlay window in Claudish's PIME, at the TSF caret rect", "cd_AI's overlay panel (panel.py), at IMK's caret rect", "the extension's label at the IBus cursor location"],
  ["The composition (plain underline)", "TSF composition", "IMK marked text", "IBus preedit (Wayland text-input)"],
  ["The panel: header, rows, footer, keycaps", "Claudish's PIME candidate window, drawn with Direct2D and DirectWrite", "cd_AI's panel (panel.py): NSVisualEffectView, menu material", "the extension's popup, fed by the engine over D\u2011Bus"],
  ["The mode switch", "the same overlay window", "the same overlay panel", "the extension's label"],
  ["Light and dark", "the apps' theme setting", "the effective appearance", "the shell's color scheme"],
];

function feasibility() {
  const section = el("section", "drawn");
  section.append(el("h2", "", "How each platform draws it"),
                 el("p", "", "Every element has to be drawable on every platform. Where one cannot be, the design changes for all of them."));
  const table = el("table");
  const head = el("tr");
  ["", "Windows\u00a011", "macOS", "GNOME (X11 and Wayland)"].forEach((h) => head.append(el("th", "", h)));
  table.append(head);
  for (const [what, ...ways] of DRAWN) {
    const row = el("tr");
    row.append(el("th", "", what), ...ways.map((w) => el("td", "", w)));
    table.append(row);
  }
  section.append(table);
  return section;
}

window.addEventListener("hashchange", render);
window.addEventListener("resize", () => document.querySelectorAll(".host").forEach(place));
document.fonts.ready.then(() => document.querySelectorAll(".host").forEach(place));
render();
