"use strict";
// The design lab: every state cd_AI shows at the caret (STATES), drawn with kit.css in a mock of
// each platform (SKINS). The words are the shared ones from claudish/composition.py (hint) and the
// service (questions and their choices). ?platform=windows&state=drafts&solo shows one mock alone,
// at its native size, for comparing with a screenshot of the real input method.

const SKINS = {
  reference: {name: "Reference", note: "The demo's own look: the one every platform follows."},
  windows: {name: "Windows 11", note: "Claudish's PIME draws the panel and the suggestion.", app: "Notepad"},
  macos: {name: "macOS", note: "cd_AI's own panel and suggestion overlay (platforms/macos/panel.py).", app: "TextEdit"},
  gnome: {name: "GNOME", note: "A GNOME Shell extension draws the panel and the suggestion, on X11 and Wayland alike.", app: "Text Editor"},
};

// Each state: the text box around the caret, what cd_AI draws there, and the panel. The footer's
// grammar is one everywhere: each key with its verb, in the order Enter, numbers, Tab, Esc, then
// "or type a reply". The highlighted row carries its own Enter. In an approval or a handoff the
// safe choice is 1 (a pinyin hand presses 1 by reflex) and nothing is highlighted (Enter never
// approves); what is approved is the body, in full contrast.
const STATES = [
  {id: "continue", title: "Continue: a suggestion", note: "The rest of the sentence after the caret, in grey. Tab takes it; typing ignores it.",
   before: "Thanks for the review — I'll", ghost: " send the revised draft by Friday."},
  {id: "compose", title: "Compose: typing", note: "Your words, as any input method's. When you pause, the keys show; while you type, only the AI tile.",
   before: "Team: ", comp: "running late, start without me",
   panel: {foot: ["Tab: rewrite", "Enter: ask"]}},
  {id: "rewriting", title: "Compose: rewriting", note: "Your words stay as they are while the model works.",
   before: "Team: ", comp: "running late, start without me",
   panel: {status: "Rewriting", busy: true, foot: ["Esc: stop"]}},
  {id: "converted", title: "Compose: the rewrite in place", note: "It takes your words' place; the panel shows yours, as large, until you keep it.",
   before: "Team: ", comp: "I'm running a little late — please start without me.",
   panel: {label: "Your words", body: "running late, start without me", foot: ["Tab: keep", "Esc: undo"]}},
  {id: "drafts", title: "An instruction's drafts", note: "Enter asked; three readings come back. The first is highlighted, and Enter takes it.",
   before: "Hi Sam, ", comp: "decline the offsite politely",
   panel: {rows: [["1", "Thank you for the invitation — I'm afraid I can't make the offsite this time."],
                  ["2", "I'd love to join, but I won't be able to attend the offsite."],
                  ["3", "Unfortunately the offsite clashes with a deadline, so I'll have to sit this one out."]],
           on: 0, foot: ["1–3: pick", "Esc: back"]}},
  {id: "hosted", title: "A hosted model answered", note: "The same drafts, saying in words where they came from.",
   before: "Hi Sam, ", comp: "decline the offsite politely",
   panel: {rows: [["1", "Thank you for the invitation — I'm afraid I can't make the offsite this time."],
                  ["2", "I'd love to join, but I won't be able to attend the offsite."],
                  ["3", "Unfortunately the offsite clashes with a deadline, so I'll have to sit this one out."]],
           on: 0, foot: ["1–3: pick", "Esc: back"], mark: "from Claude · hosted"}},
  {id: "ask", title: "The model asks", note: "A question as is. Enter takes the highlighted choice; your own words answer too.",
   before: "", comp: "summarize this thread",
   panel: {label: "The model asks", body: "The whole thread, or only the last reply?",
           rows: [["1", "The whole thread"], ["2", "Only the last reply"]], on: 0,
           foot: ["1–2: pick", "or type a reply"]}},
  {id: "permission", title: "An approval", note: "What runs is shown in full. Nothing is highlighted and 1 is Deny: only 2 approves.",
   before: "", comp: "push my branch",
   panel: {label: "Claude Code wants to run", body: "git push origin parser-fix", code: true,
           rows: [["1", "Deny"], ["2", "Allow"]], on: -1, foot: ["1–2: pick", "or type why not"]}},
  {id: "handoff", title: "A handoff", note: "Sending a task to a helper is asked the same way: 1 keeps it here.",
   before: "", comp: "have claude fix the failing parser test",
   panel: {label: "Hand off to Claude Code", body: "Fix the failing parser test",
           rows: [["1", "No", "answer it here"], ["2", "Yes", "it opens in a new window"]], on: -1,
           foot: ["1–2: pick", "or type a reply"]}},
  {id: "answer", title: "An answer to read", note: "Several sentences, wrapped to a readable width.",
   before: "", comp: "what does this error mean",
   panel: {label: "The model says", body: "The parser reached the end of the file while a string was still open. The quote on line 12 is never closed, so everything after it was read as part of the string.",
           rows: [["1", "Insert it", "at the caret"], ["2", "Dismiss", "nothing is inserted"]], on: 0,
           foot: ["1–2: pick", "or type a reply"]}},
  {id: "progress", title: "An agent at work", note: "One line: what it is doing, and how to stop it.",
   before: "", comp: "fix the failing parser test",
   panel: {status: "Reading tests/test_parser.py", busy: true, foot: ["Esc: stop"]}},
  {id: "failed", title: "A failed request", note: "Your words stay; the panel says why, and Enter sends them again.",
   before: "Hi Sam, ", comp: "decline the offsite politely",
   panel: {failed: "The model is offline", foot: ["Enter: retry", "Esc: back"]}},
  {id: "terminal", title: "In a terminal", note: "Continue is quiet on a command line; an instruction offers commands.",
   terminal: true, before: "~/claudish $ ", comp: "undo my last commit but keep the changes",
   panel: {rows: [["1", "git reset --soft HEAD~1"], ["2", "git reset --mixed HEAD~1"]], on: 0, mono: true,
           foot: ["1–2: pick", "Esc: back"]}},
  {id: "mode-compose", title: "A mode switch: compose", note: "A Shift tap: the mode, and how to go back, briefly at the caret. The taskbar or menu bar shows it all along.",
   before: "Thanks for the review — I'll", toast: "compose"},
  {id: "mode-continue", title: "A mode switch: continue", note: "And back: a neutral tile, so only compose wears the accent.",
   before: "Thanks for the review — I'll", toast: "continue"},
];

// Key names: the platform's own (a skin token). macOS menus show glyphs, without boxes.
const KEYS = {macos: {Enter: "↩", Esc: "⎋", Tab: "⇥", Shift: "⇧"}};

const $ = (id) => document.getElementById(id);
const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

// A state's panel, in the shape of Composition.panel() (claudish/composition.py), which kit.js
// draws for the lab, the demo, and (natively) every platform. "Tab: keep" is a key and its verb;
// any other footer words are the free words after the keys.
function described(spec) {
  const foot = [], tail = [];
  for (const words of spec.foot || []) {
    const match = /^([^:]+): (.+)$/.exec(words);
    if (match) foot.push([match[1], match[2]]); else tail.push(words);
  }
  return {label: spec.label || null, body: spec.body || null, code: Boolean(spec.code), mono: Boolean(spec.mono),
          rows: (spec.rows || []).map(([key, text, legend]) => ({key, text, legend: legend || null})),
          on: spec.on === undefined ? -1 : spec.on, foot, tail: tail.join(" ") || null,
          tile: spec.failed ? "warn" : "ai", status: spec.status || null, busy: Boolean(spec.busy),
          failed: spec.failed || null, mark: spec.mark || null};
}

// The host: a window of the platform's own kind with a text box, the caret in it.
function frame(skin, state) {
  const host = el("div", `host ${skin}` + (state.terminal ? " terminal" : ""));
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
  if (state.panel) text.append(Kit.panel(described(state.panel), KEYS[skin] || {}));
  if (state.toast) {  // Composition.toast(): a panel with only a footer
    const compose = state.toast === "compose";
    text.append(Kit.toast({tile: compose ? "ai" : "cd", status: compose ? "Compose" : "Continue",
                           foot: [["Shift", compose ? "back" : "compose"]]}, KEYS[skin] || {}));
  }
  host.append(bar, text);
  return host;
}

// Under the caret's line, the panel's content starting at the caret: every platform knows the
// caret (GNOME knows nothing else, so no platform anchors to the composition's start).
function place(host) {
  const text = host.querySelector(".host-text");
  const anchor = host.querySelector(".anchor");
  const caret = host.querySelector(".host-caret");
  const box = text.getBoundingClientRect();
  const line = caret.getBoundingClientRect();
  const start = line;
  const lineBottom = line.bottom;
  for (const floating of host.querySelectorAll(".k-panel, .k-toast")) {
    const style = getComputedStyle(floating);
    const inset = parseFloat(style.paddingLeft) + parseFloat(style.borderLeftWidth)
      + (floating.classList.contains("k-panel") ? parseFloat(getComputedStyle(floating).getPropertyValue("--k-row-x")) || 0 : 0);
    // Clamped to the screen, as a real input method's window is (it floats over the app's).
    const left = Math.max(8 - box.left, Math.min(start.left - box.left - inset,
                                                 document.documentElement.clientWidth - box.left - floating.offsetWidth - 8));
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
  ["The panel: header, rows, footer, keycaps", "Claudish's PIME candidate window, drawn with Direct2D and DirectWrite (GDI cannot anti-alias the rounded keycaps and tile)", "cd_AI's panel (panel.py): NSVisualEffectView, menu material", "the extension's popup, fed by the engine over D-Bus (the Shell's IBus popup has no header, keycaps, or tile)"],
  ["The mode switch", "the same overlay window", "the same overlay panel", "the extension's label"],
  ["Light and dark", "the apps' theme setting", "the effective appearance", "the shell's colour scheme"],
];

function feasibility() {
  const section = el("section", "drawn");
  section.append(el("h2", "", "How each platform draws it"),
                 el("p", "", "Every element has to be drawable on every platform. Where one cannot be, the design changes for all of them."));
  const table = el("table");
  const head = el("tr");
  ["", "Windows 11", "macOS", "GNOME (X11 and Wayland)"].forEach((h) => head.append(el("th", "", h)));
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
