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

// Each state: the text box around the caret, what cd_AI draws there, and the panel.
const STATES = [
  {id: "continue", title: "Continue: a suggestion", note: "The rest of the sentence after the caret, in grey. Tab takes it; typing ignores it.",
   before: "Thanks for the review — I'll", ghost: " send the revised draft by Friday."},
  {id: "compose", title: "Compose: typing", note: "Your words, as any input method's. The panel's AI tile says compose; the keys say what is next.",
   before: "Quick update for the team: ", comp: "running late, start without me",
   panel: {foot: ["Tab: rewrite", "Enter: ask AI"]}},
  {id: "rewriting", title: "Compose: rewriting", note: "Your words stay as they are while the model works.",
   before: "Quick update for the team: ", comp: "running late, start without me",
   panel: {status: "rewriting"}},
  {id: "converted", title: "Compose: the rewrite in place", note: "It takes your words' place; the panel keeps yours, until you keep it.",
   before: "Quick update for the team: ", comp: "I'm running a little late — please start without me.",
   panel: {was: "running late, start without me", foot: ["Tab: keep", "Esc: undo"]}},
  {id: "drafts", title: "An instruction's drafts", note: "Enter asked; three readings come back. The first is highlighted.",
   before: "Hi Sam, ", comp: "decline the offsite politely",
   panel: {rows: [["1", "Thank you for the invitation — I'm afraid I can't make the offsite this time."],
                  ["2", "I'd love to join, but I won't be able to attend the offsite."],
                  ["3", "Unfortunately the offsite clashes with a deadline, so I'll have to sit this one out."]],
           on: 0, foot: ["1–3: pick", "Esc: back"]}},
  {id: "hosted", title: "A hosted model answered", note: "The same drafts, with a mark when the answer came from a hosted model.",
   before: "Hi Sam, ", comp: "decline the offsite politely",
   panel: {rows: [["1", "Thank you for the invitation — I'm afraid I can't make the offsite this time."],
                  ["2", "I'd love to join, but I won't be able to attend the offsite."]],
           on: 0, foot: ["1–2: pick", "Esc: back"], mark: "hosted: Claude"}},
  {id: "ask", title: "The model asks", note: "A question as is. Enter takes the highlighted first choice.",
   before: "", comp: "summarize this thread",
   panel: {label: "The model asks", body: "The whole thread, or only the last reply?",
           rows: [["1", "The whole thread"], ["2", "Only the last reply"]], on: 0,
           foot: ["Enter: the first", "1–2", "or type a reply"]}},
  {id: "permission", title: "An approval", note: "Nothing is highlighted: only a number answers it, so Enter never approves.",
   before: "", comp: "push my branch",
   panel: {body: "Allow Bash?", rows: [["1", "Allow", "git push origin parser-fix"], ["2", "Deny"]], on: -1,
           foot: ["1–2", "or type a reply"]}},
  {id: "handoff", title: "A handoff", note: "Sending a task to a helper is a question too, answered with a number.",
   before: "", comp: "have claude fix the failing parser test",
   panel: {label: "Send this task to claude?", body: "Fix the failing parser test",
           rows: [["1", "Yes", "it opens in a new window"], ["2", "No", "answer it here instead"]], on: -1,
           foot: ["1–2", "or type a reply"]}},
  {id: "answer", title: "An answer to read", note: "Several sentences, wrapped to a readable width.",
   before: "", comp: "what does this error mean",
   panel: {label: "The model says", body: "The parser reached the end of the file while a string was still open. The quote on line 12 is never closed, so everything after it was read as part of the string.",
           rows: [["1", "Insert it", "at the caret"], ["2", "Dismiss", "nothing is inserted"]], on: 0,
           foot: ["Enter: the first", "1–2", "or type a reply"]}},
  {id: "progress", title: "An agent at work", note: "One muted line: what it is doing.",
   before: "", comp: "fix the failing parser test",
   panel: {status: "Reading tests/test_parser.py"}},
  {id: "failed", title: "A failed request", note: "Your words stay; Enter sends them again.",
   before: "Hi Sam, ", comp: "decline the offsite politely",
   panel: {failed: "failed", foot: ["Enter: retry", "Esc: back"]}},
  {id: "terminal", title: "In a terminal", note: "Continue is quiet on a command line; an instruction offers commands.",
   terminal: true, before: "~/claudish $ ", comp: "undo my last commit but keep the changes",
   panel: {rows: [["1", "git reset --soft HEAD~1"], ["2", "git reset --mixed HEAD~1"]], on: 0, mono: true,
           foot: ["1–2: pick", "Esc: back"]}},
  {id: "mode", title: "A mode switch", note: "A Shift tap: the mode's tile and name, briefly, at the caret.",
   before: "Thanks for the review — I'll", toast: "compose"},
];

const $ = (id) => document.getElementById(id);
const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

// "Tab: keep" becomes a keycap and its action; "1–2" a keycap alone; anything else plain words.
function hint(text) {
  const span = el("span", "k-hint");
  const match = /^([^:]+): (.+)$/.exec(text);
  if (match) {
    span.append(el("span", "k-cap", match[1]), match[2]);
  } else if (/^[0-9–-]+$/.test(text) || /^(Tab|Enter|Esc)$/.test(text)) {
    span.append(el("span", "k-cap", text));
  } else {
    span.textContent = text;
  }
  return span;
}

function panel(spec) {
  const node = el("div", "k-panel" + (spec.rows || spec.body ? "" : " bare"));
  if (spec.body) {
    const head = el("div", "k-head");
    if (spec.label) head.append(el("span", "k-label", spec.label));
    head.append(el("span", "k-body", spec.body));
    node.append(head);
  }
  (spec.rows || []).forEach(([key, text, legend], index) => {
    const row = el("div", "k-row" + (index === spec.on ? " on" : ""));
    row.append(el("span", "k-key", key));
    const words = el("span", "k-text" + (spec.mono ? " k-mono" : ""), text);
    if (legend) words.append(el("span", "k-legend", " — " + legend));
    row.append(words);
    node.append(row);
  });
  if (spec.was) node.append(el("div", "k-was", spec.was));
  const foot = el("div", "k-foot");
  foot.append(el("span", "k-tile ai", "AI"));
  if (spec.status) {
    const status = el("span", "k-status k-dots", spec.status);
    foot.append(status);
  }
  if (spec.failed) foot.append(el("span", "k-status failed", spec.failed));
  (spec.foot || []).forEach((text) => foot.append(hint(text)));
  if (spec.mark) foot.append(el("span", "k-mark", spec.mark));
  node.append(foot);
  return node;
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
  if (state.ghost) line.append(el("span", "k-ghost", state.ghost));
  text.append(line);
  if (state.panel) text.append(panel(state.panel));
  if (state.toast) {
    const toast = el("div", "k-toast");
    const tile = state.toast === "compose" ? el("span", "k-tile ai", "AI") : el("span", "k-tile cd", "cd");
    toast.append(tile, state.toast);
    text.append(toast);
  }
  host.append(bar, text);
  return host;
}

// As input methods do: the panel under the composition's start, its text aligned with your words.
function place(host) {
  const text = host.querySelector(".host-text");
  const anchor = host.querySelector(".anchor");
  const caret = host.querySelector(".host-caret");
  const box = text.getBoundingClientRect();
  const line = caret.getBoundingClientRect();
  // The composition's part on the caret's line (a long one wraps): the panel goes under its start.
  const parts = anchor.firstChild ? [...anchor.firstChild.getClientRects()] : [];
  const start = parts.filter((r) => r.bottom > line.top + 1 && r.top < line.bottom - 1)[0] || line;
  const lineBottom = line.bottom;
  for (const floating of host.querySelectorAll(".k-panel, .k-toast")) {
    const style = getComputedStyle(floating);
    const inset = parseFloat(style.paddingLeft) + parseFloat(style.borderLeftWidth)
      + (floating.classList.contains("k-panel") ? parseFloat(getComputedStyle(floating).getPropertyValue("--k-row-x")) || 0 : 0);
    const left = Math.max(8, Math.min(start.left - box.left - inset, box.width - floating.offsetWidth - 8));
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
  ["The suggestion after the caret", "cd_AI's overlay window at the caret", "cd_AI's overlay panel (panel.py)", "the extension's label at the IBus cursor"],
  ["The composition (plain underline)", "TSF composition", "IMK marked text", "IBus preedit (Wayland text-input)"],
  ["The panel: header, rows, footer, keycaps", "Claudish's PIME candidate window", "cd_AI's panel (panel.py)", "the extension's candidate popup"],
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
