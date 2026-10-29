"use strict";
// The demo is an input method, drawn: one editor, a composition at the caret, a candidate window,
// and the same rules as claudish/composition.py (continue types straight in; compose holds your
// words: Tab rewrites them, Shift+Enter does them as an instruction, Enter keeps them; a Shift tap switches). Typed keys arrive through a hidden textarea, so phone
// keyboards and the browser's own input methods still work.
const $ = (id) => document.getElementById(id);
const sink = $("input");
// Rendered by moving these nodes around the text; held here so they are never lost from a render.
const PREEDIT = $("preedit"), CARET = $("caret"), GHOST = $("ghost"), PLACEHOLDER = $("placeholder");
const MAX = 512;
const HINTS = {
  continue: "Type as usual. Pause after a word: the rest of the sentence waits in grey; Tab takes it. Tap Shift to compose.",
  compose: "Type, or select some text. Tab offers a rewrite (Tab again takes it); Shift+Enter asks the model to do it; Enter keeps it as it is. Tap Shift to type straight in.",
};
const SHIFT_TAP_MS = 500;  // Shift alone, released within this: the mode switch
// [label, mode, text, the key that finishes it]
const SAMPLES = [
  ["rewrite", "compose", "This is very important.", "Tab"],
  ["continue", "continue", "Thanks for the quick review. ", ""],
  ["ask", "compose", "decline the meeting politely, propose Thursday", "Shift+Enter"],
];
const IN_BROWSER = document.querySelector('meta[name="claudish-backend"]')?.content === "browser";
let browserBackend = null;
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
  mode: "compose",   // where cd_AI starts
  asked: null,       // compose: what the pending or shown result is ("rewrite" or "instruct")
  candidate: "",
  candidates: [],
  converted: false,  // compose: the rewrite shows in the panel (your words stay the composition)
  working: false,
  failed: false,
  error: "",     // why the last request failed, in plain words
  reply: "",     // what you type once an instruction is sent: a reply, or your next words
  highlight: 0,  // the highlighted draft (↑ and ↓ move it)
  editing: false,  // the instruction came back to the caret (Esc edit): the next Esc drops it
  dropped: "",   // the last words Esc dropped (an instruction, or a reply): Shift+Esc brings them back
  droppedReply: false,
  nudged: null,  // Enter on the model's text: what the panel showed then (Tab's key lights while it lasts)
  revision: 0,
};
let timer = null;
let typing = null;  // a sample typing itself

function change(text) {
  state.text = text;
  state.candidate = "";
  state.candidates = [];
  state.converted = false;
  state.asked = null;
  state.working = state.failed = false;
  state.error = state.reply = "";
  state.highlight = 0;
  state.editing = false;
  state.revision++;
}
const live = () => state.mode === "continue";
const composing = () => !live() && Boolean(state.text);
// Sent: the instruction stays the composition while its exchange is open, and a reply takes its
// place (docs/design/design.md). A rewrite waits in the panel: only Tab puts the model's words in.
const sent = () => state.asked === "instruct" && (state.working || state.failed || Boolean(state.candidate));
const shown = () => sent() ? state.reply || state.text : state.text;
const ghost = () => live() && !selected() && state.candidate.length > state.text.length
  && state.candidate.startsWith(state.text) ? state.candidate.slice(state.text.length) : "";
function automatic() {
  // Only continue asks on a pause, at a word boundary (not at the start of an empty line), and only
  // at the end of a line: in the middle of text a suggestion would cover what follows. Rewrite asks
  // on Tab and instruct on Shift+Enter: nothing is sent while you type.
  const inside = Boolean(doc.text[doc.caret]) && doc.text[doc.caret] !== "\n";
  return live() && !inside && Boolean(state.text) && !/[\p{L}\p{N}\n]$/u.test(state.text);
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
  if (composing()) commit(shown());  // what the composition shows (your words, or a reply)
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
  if (IN_BROWSER && !browserBackend) {  // nothing to ask yet: the Run button is the next step, not an error
    state.working = false;
    if (!live()) state.asked = null;
    setStatus("Run the model in this browser first: the button above.");
    $("load-model")?.classList.add("attention");
    setTimeout(() => $("load-model")?.classList.remove("attention"), 1600);
    render();
    return;
  }
  const text = state.text, mode = live() ? "continue" : state.asked, started = performance.now();
  const controller = new AbortController();
  const limit = setTimeout(() => controller.abort(), Math.max(15000, serviceTimeout * 1000 + 2000));
  setStatus("");  // the panel says what is happening
  try {
    let data;
    if (IN_BROWSER) {
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
    if (mode === "rewrite" && state.working) state.converted = true;  // asked with Tab: shown as it arrives
    state.working = false;
    if (mode === "instruct" && state.nudged === pending())
      state.nudged = showing();  // Enter was pressed while they came, and nothing since
    const elapsed = Math.round(performance.now() - started);
    $("timing").textContent = data.backend === "browser" ? `${elapsed} ms in this browser`
      : `${elapsed} ms · ${data.backend === "rules" ? "rules, no model" : "model"}`;
    setStatus("");
  } catch (error) {
    if (revision !== state.revision) return;
    state.working = false;
    if (mode === "continue") return;  // continue stays quiet: no suggestion is a fine answer
    state.failed = true;  // the panel says why; your words stay
    state.error = error.name === "AbortError" ? "the model took too long"
      : error instanceof TypeError ? "the model is offline"
      : /no model is set up/.test(error.message) ? "no model is set up" : "the request failed";
    setStatus("");
  } finally {
    clearTimeout(limit);
    render();
  }
}

// What the panel shows: the same description as claudish/composition.py's panel(), so the demo
// looks as the input methods do. null: nothing (continue's suggestion speaks for itself).
// Enter on a draft lights its row's Tab, the key that takes it, until a key changes the panel.
const showing = () => JSON.stringify([state.text, state.reply, state.highlight, state.candidate]);
const pending = () => JSON.stringify(["pending", state.text, state.reply]);  // a nudge while the drafts come
const nudge = () => state.nudged !== null && state.nudged === showing();

function panel() {
  if (live() || !state.text) return null;
  const shown = {thread: [], label: null, body: null, code: false, rows: [], on: -1, foot: [], tail: null, tile: "ai",
                 status: null, busy: false, failed: null, replying: false};
  // Once the composition no longer shows your instruction (you type a reply), the panel says it.
  if (sent() && state.reply) shown.thread = [{label: "You asked", body: state.text}];
  const typing = sent() && state.reply ? {replying: true, on: -1, foot: [["Shift+Enter", "ask"], ["Esc", "cancel"]]} : {};
  if (state.working) return {...shown, status: state.asked === "rewrite" ? "rewriting" : "working", busy: true,
                             foot: [["Esc", "stop"]], ...typing};
  if (state.failed) return {...shown, tile: "warn", failed: state.error || "the request failed",  // Tab retries a rewrite
                            foot: [[state.asked === "rewrite" ? "Tab" : "Shift+Enter", "retry"], ["Esc", "edit"]], ...typing};
  if (state.asked === "instruct" && state.candidate) {
    const readings = state.candidates;
    return {...shown, rows: draftsShown(readings, state.highlight).map((text) => ({text, legend: null})), on: state.highlight,
            foot: [...(readings.length > 1 ? [["↑↓", "choose"]] : []), ["Tab", "insert"], ["Esc", "edit"]],
            nudge: nudge(), ...typing};
  }
  if (state.converted) return {...shown, label: "Rewrite", body: shortened(state.candidate, PANEL_ROWS),
                               foot: [["Tab", "insert"], ["Esc", "dismiss"]]};
  // Composing: the keys show from the first key (what each Enter does must be known).
  return {...shown, foot: [["Tab", "rewrite"], ["Shift+Enter", "ask"], state.editing ? ["Esc", "drop"] : ["Enter", "keep"]]};
}
// The panel stays shorter than a screen, as composition.py keeps it (PANEL_ROWS rows of about ROW
// characters): past it, drafts other than the highlighted one show two rows, a taller text its first
// rows and an ellipsis. Tab still takes the whole text.
const PANEL_ROWS = 24, ROW = 60;
const rowsOf = (text) => (text || "").split("\n").reduce((rows, line) => rows + Math.max(1, Math.ceil(line.length / ROW)), 0);
function shortened(text, rows) {
  if (rowsOf(text) <= rows) return text;
  if (rows <= 2) text = text.split(/\s+/).filter(Boolean).join(" ");
  const kept = [];
  let room = rows * ROW;
  for (const line of text.split("\n")) {
    if (line.length >= room) {
      const head = line.slice(0, room - 1);
      kept.push((head.includes(" ") ? head.slice(0, head.lastIndexOf(" ")) : head).replace(/[ ,;:—-]+$/, "") + "…");
      break;
    }
    kept.push(line);
    room -= Math.max(1, Math.ceil(line.length / ROW)) * ROW;
    if (room <= 0) { kept[kept.length - 1] = kept[kept.length - 1].replace(/[ ,;:—-]+$/, "") + "…"; break; }
  }
  return kept.join("\n");
}
function draftsShown(drafts, on) {
  if (drafts.reduce((rows, draft) => rows + rowsOf(draft), 0) <= PANEL_ROWS) return drafts;
  const room = Math.max(PANEL_ROWS - 2 * (drafts.length - 1), 6);
  return drafts.map((draft, index) => shortened(draft, index === on ? room : 2));
}
// A click on a draft: it goes in at the caret (choices are not numbered; the mouse picks directly).
function pickRow(number) {
  const picked = state.candidates[number - 1];
  if (picked === undefined || state.reply) return;
  commit(picked); change(""); changed();
}

// Never silently: a drop says so, briefly, with the key that brings it back.
const dropped = () => toast({tile: "ai", status: "dropped", foot: [["Shift+Esc", "restore"]]});

// A Shift tap (or a click on the input source): continue <-> compose. Leaving compose keeps what
// you see, as it is.
function switchMode() {
  flash("Shift");
  if (live()) { state.mode = "compose"; change(""); }
  else {
    const kept = shown();
    if (kept) commit(kept);
    state.mode = "continue";
    change(context());
  }
  showMode();
  changed();
  toast();
}

// Briefly at the caret: the mode switch (its tile, its name, and the key back), or what Esc
// dropped, with the key that brings it back (composition.py's toast and dropped_toast).
function toast(spec = null) {
  const compose = state.mode === "compose";
  const node = Kit.toast(spec || {tile: compose ? "ai" : "cd", status: compose ? "compose" : "continue",
                                  foot: [["Shift", compose ? "continue" : "compose"]]});
  const editor = $("editor").getBoundingClientRect(), caret = CARET.getBoundingClientRect();
  node.style.left = `${Math.max(12, caret.left - editor.left - 14)}px`;
  node.style.top = `${caret.bottom - editor.top + 6}px`;
  document.querySelectorAll("#editor > .k-toast").forEach((old) => old.remove());
  $("editor").append(node);
  setTimeout(() => node.remove(), 2000);  // as long as every platform shows a toast
}

// Keys, as an input method sees them. Returns true when the key was taken.
function key(name, shift = false) {
  flash(name === "Enter" && shift ? "Shift+Enter" : name);
  document.querySelectorAll("#editor > .k-toast").forEach((old) => old.remove());  // a key ends a toast
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
  // Choices are not numbered: digits are text, as Space is; ↑ and ↓ choose, Tab takes.
  if ((name === "ArrowUp" || name === "ArrowDown") && state.asked === "instruct" && state.candidate
      && !state.reply) {  // ↑ and ↓ move the highlight, without wrapping (one draft: taken, nothing moves)
    const count = state.candidates.length;
    state.highlight = Math.max(0, Math.min(count - 1, state.highlight + (name === "ArrowUp" ? -1 : 1)));
    render();
    return true;
  }
  if (name === "Enter") {
    if (!state.text) { commit("\n"); render(); return true; }  // nothing composed: a newline
    if (!shift) {  // Enter only puts your own words in; the next Enter is the editor's (a newline)
      if (sent() || state.working || state.converted) {  // once the model is asked Enter is gated, a rewrite included
        if (state.asked === "instruct" && state.candidate) state.nudged = showing();  // the row lights Tab
        else if (state.working) state.nudged = pending();
        render();
        return true;
      }
      commit(shown()); change(""); changed(); return true;
    }
    if (sent() && state.reply.trim()) {  // your next words: a follow-up instruction
      change(state.reply.trim());
      state.asked = "instruct"; state.working = true; render(); ask(state.revision);
      return true;
    }
    // Shift+Enter talks to the model: it never inserts the model's text (Tab does).
    if (state.asked === "instruct" && state.candidate) { state.nudged = showing(); render(); return true; }  // the row lights Tab
    if (state.converted) return true;  // the rewrite goes in with Tab, as its footer says
    if (!state.working) {  // Shift+Enter sends it as an instruction
      state.asked = "instruct"; state.working = true; state.failed = false; state.nudged = null; render(); ask(state.revision);
    } else if (state.asked === "instruct") {
      state.nudged = pending();  // a reflexive key: Tab lights when they come
    }
    return true;
  }
  if (name === "Tab") {
    if (!state.text && selected()) {  // a selection: your words, as if you had just typed them
      const [start, end] = selection();
      const words = doc.text.slice(start, end);  // one line you could have typed (composition.py's selectable)
      if (words.length <= MAX && words.trim() && !/[\n\r\v\f\u0085\u2028\u2029]/.test(words)) { removeSelection(); change(words); render(); return true; }
    }
    if (!state.text) return false;
    if (state.reply) return true;  // a reply you are typing: Shift+Enter sends it, and Tab takes nothing over it
    // The first Tab asks for the rewrite, which shows in the panel as it arrives (your words stay);
    // the next inserts it (or an instruction's highlighted draft). A pending answer is not stale text: Tab waits.
    if (state.converted || (state.asked === "instruct" && state.candidate)) {  // the rewrite, or the highlighted draft
      commit(state.converted ? state.candidate : state.candidates[state.highlight]); change(""); changed();
    } else if (state.asked === "rewrite" && state.candidate) { state.converted = true; render(); }
    else if (!state.working) {
      state.asked = "rewrite"; state.working = true; state.failed = false; render(); ask(state.revision);
    }
    return true;
  }
  if (name === "Escape") {  // one step back: what you typed, then edit, then drop
    if (shift && state.dropped && state.droppedReply && sent() && !state.reply) {  // Shift+Esc: the cleared reply
      state.reply = state.dropped; state.dropped = ""; render();
      return true;
    }
    if (shift && !state.text && state.dropped) {  // Shift+Esc: the dropped instruction, back to edit
      change(state.dropped); state.dropped = ""; state.editing = true; render();
      return true;
    }
    if (shift) return false;  // nothing to bring back: the key is the page's, as in composition.py
    if (!state.text) return false;
    if (sent() && state.reply) {  // what you typed goes, and says so; Shift+Esc brings it back
      state.dropped = state.reply; state.droppedReply = true; state.reply = ""; render(); dropped(); return true;
    }
    if (state.converted) {  // your words again, the rewrite forgotten: Tab asks for another take
      state.converted = false; state.candidate = ""; state.candidates = []; state.editing = true; render(); return true;
    }
    // Sent, or a rewrite pending or failed: back to your words, to edit (a late answer is ignored).
    if (sent() || state.working || state.failed) { change(state.text); state.editing = true; render(); return true; }
    state.dropped = state.text; state.droppedReply = false;
    change("");
    render();
    dropped();
    return true;
  }
  if (name === "Backspace") {
    if (state.converted) { state.converted = false; render(); return true; }  // your words again
    if (sent()) { state.reply = state.reply.slice(0, -1); render(); return true; }  // a reply; the instruction stays
    if (state.text) change(state.text.slice(0, -1));
    else if (selected()) removeSelection();
    else if (doc.caret) { doc.text = doc.text.slice(0, doc.caret - 1) + doc.text.slice(doc.caret); moveTo(doc.caret - 1); }
    changed();
    return true;
  }
  if (name.length === 1) {
    if (selected() && !state.text) removeSelection();  // typing replaces the selection
    // Nothing composed: only a letter or a digit starts a composition; spaces and punctuation are the app's.
    if (!state.text && !/[\p{L}\p{N}]/u.test(name)) { commit(name); changed(); return true; }
    // A rewrite showing in the panel: typing on goes on with your words (the rewrite goes).
    if (state.text.length >= MAX) { commit(state.text); change(""); }
    // Sent: what you type is your next words, at the caret; a Space with nothing typed does nothing.
    if (sent()) { if (name !== " " || state.reply) state.reply += name; render(); return true; }
    change(state.text + name);  // as typed: em dashes come from the model, never from a key
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
  // The panel, as every platform draws it (kit.js; claudish/composition.py's panel()).
  const window = $("candidates");
  const spec = panel();
  window.replaceChildren(...(spec ? [Kit.panel(spec, {}, pickRow)] : []));
  if (spec) document.querySelectorAll("#editor > .k-toast").forEach((toast) => toast.remove());  // a panel replaces a toast
  window.hidden = !spec;
  placeCandidateWindow();
  $("copy").disabled = $("clear").disabled = !doc.text;
}

function placeCandidateWindow() {
  const window = $("candidates");
  const editor = $("editor").getBoundingClientRect();
  const caret = CARET.getBoundingClientRect();
  // The panel is as wide as its words, up to the editor (the demo has no 440 px cap), as a real
  // panel fits its screen.
  const panel = window.querySelector(".k-panel, .k-toast");
  const room = `${editor.width - 16}px`;
  if (panel) Object.assign(panel.style, {maxWidth: room, minWidth: `min(var(--k-min), ${room})`});
  // As on every platform: under the line, the panel's content starting where the composition
  // starts (what IMK, TSF and IBus report while something is composed), or at the caret.
  const start = PREEDIT.textContent ? PREEDIT.getClientRects()[0] || caret : caret;
  const inset = 14;  // the panel's border, padding, and row inset (kit.css)
  const from = PREEDIT.textContent ? start.left : caret.right;
  let left = Math.max(8, Math.min(from - editor.left - inset, editor.width - window.offsetWidth - 8));
  // It opens there and stays where it opened while it shows on that line and its anchor is at or
  // right of it: it never slides while you type; if you delete back past it, it moves.
  const line = Math.round(caret.bottom - editor.top), opened = placeCandidateWindow.opened;
  if (!window.hidden && opened && opened.line === line && left >= opened.left) left = opened.left;
  placeCandidateWindow.opened = window.hidden ? null : {left, line};
  window.style.left = `${left}px`;
  window.style.top = `${caret.bottom - editor.top + 6}px`;
  sink.style.left = `${caret.left - editor.left}px`;  // the browser's own IME window follows the caret too
  sink.style.top = `${caret.top - editor.top}px`;
}

function showMode() {
  $("source-mode").textContent = state.mode;
  $("source").setAttribute("aria-label", `Input source: cd_AI, ${state.mode}. Tap Shift or click to switch.`);
  $("hint").textContent = HINTS[state.mode];
}
function setStatus(text) { $("status").textContent = text; }
// The key strip is tappable (a phone keyboard has no Shift+Enter): a tap is that key's press.
document.addEventListener("pointerdown", (event) => {
  const strip = event.target.closest(".keystrip [data-key]");
  if (!strip || strip.dataset.key === "Shift") return;
  event.preventDefault();  // the editor keeps the focus
  stopTyping();
  const [name, shift] = strip.dataset.key === "Shift+Enter" ? ["Enter", true] : [strip.dataset.key, false];
  key(name, shift);
});
function flash(name) {
  const strip = document.querySelector(`[data-key="${name === "ArrowUp" ? "ArrowDown" : name}"]`);
  if (!strip) return;
  strip.classList.add("pressed");
  setTimeout(() => strip.classList.remove("pressed"), 220);
}

// Input from the hidden textarea.
sink.addEventListener("keydown", (event) => {
  if (event.isComposing) return;
  if (event.ctrlKey || event.metaKey || event.altKey) shiftDownAt = null;  // Ctrl+Shift, Alt+Shift: a chord, not a tap
  if (event.ctrlKey || event.metaKey) {
    if (event.altKey) return;
    settle();  // a shortcut ends a composition: your words go in first
    if (event.key.toLowerCase() === "a") { event.preventDefault(); doc.anchor = 0; doc.caret = doc.text.length; }
    changed();
    return;  // copy, cut, and paste arrive as events below
  }
  if (event.altKey) return;
  if (event.key === "Shift") {
    // Right after another key it is rolled typing (a fast capital), not a tap: composition.py's rule.
    if (!event.repeat) shiftDownAt = performance.now() - typedAt < ROLLED_SHIFT_MS ? null : performance.now();
    return;
  }
  shiftDownAt = null;  // Shift with another key (a capital, Shift+Enter): not a tap
  typedAt = performance.now();
  const named = ["Tab", "Enter", "Escape", "Backspace", "Delete", "ArrowLeft", "ArrowRight", "Home", "End"]
    .includes(event.key) || (state.asked === "instruct" && state.candidate && (event.key === "ArrowUp" || event.key === "ArrowDown"));
  if (named) {
    if (event.key === "Enter" && event.shiftKey && !composing()) return;  // a newline, as the app's
    stopTyping();
    if (key(event.key, event.shiftKey)) event.preventDefault();
  }
});
// A Shift tap switches mode, as Shift switches English and pinyin in a Chinese input method.
let shiftDownAt = null;
let typedAt = -Infinity;
const ROLLED_SHIFT_MS = 300;
sink.addEventListener("keyup", (event) => {
  if (event.key !== "Shift") return;
  const chord = event.ctrlKey || event.altKey || event.metaKey;
  const tapped = !chord && shiftDownAt !== null && performance.now() - shiftDownAt <= SHIFT_TAP_MS;
  shiftDownAt = null;
  if (tapped) { stopTyping(); switchMode(); }
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
// A paste is the app's, as with any input method: your words go in first, then the pasted text as
// is. To compose it, select it and press Tab.
function paste(text) {
  stopTyping();
  settle();
  commit(text.slice(0, 5000));
  change(live() ? context() : "");
  changed();
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
  shiftDownAt = null;  // Shift+click extends a selection: not a tap
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
$("source").addEventListener("click", () => { switchMode(); sink.focus(); });

// Samples type themselves, key by key, through the same path as your keys.
function stopTyping() { if (typing) { clearInterval(typing); typing = null; } }
$("samples").addEventListener("click", (event) => {
  const button = event.target.closest("[data-sample]");
  if (!button) return;
  stopTyping();
  sink.focus();
  settle();
  if (state.mode !== button.dataset.mode) switchMode();
  if (selected()) removeSelection();  // a sample replaces the selection, as typing would
  if (doc.caret > 0 && doc.text[doc.caret - 1] !== "\n") commit("\n");  // its own line, unless at one already
  const chars = [...button.dataset.sample];
  typing = setInterval(() => {
    if (!chars.length) {
      stopTyping();
      if (button.dataset.then === "Shift+Enter") key("Enter", true);
      else if (button.dataset.then) key(button.dataset.then);
      return;
    }
    key(chars.shift());
  }, 45);
});
function renderSamples() {
  const buttons = SAMPLES.map(([label, mode, sample, then]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.mode = mode;
    button.dataset.sample = sample;
    button.dataset.then = then;
    const tag = document.createElement("span");
    tag.className = "sample-mode";
    tag.textContent = label;
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
    $("connection").className = "connection online";
    $("connection").replaceChildren(document.createElement("i"),
      document.createTextNode(data.backend === "rules" ? "Rules demo connected"
        : data.backend === "claude" ? "Claude API connected" : data.backend === "command" ? "Agent command connected"
        : "Model service connected"));
    $("backend").textContent = data.backend === "rules" ? "RULES MODE · NO MODEL"
      : data.backend === "claude" ? "cd_AI · CLAUDE API" : "cd_AI · MODEL API";
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
    const name = (document.querySelector('meta[name="claudish-model"]')?.content || "The model").replace(/\s*\(.*\)$/, "");
    $("model-copy").textContent = note || `${name} is ready. Type below.`;
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
  const [, named, size] = model.match(/^(.*?)\s*\((.*)\)$/) || [, model, ""];
  const offer = size ? `${named}, a ${size} download.` : `${named}.`;  // "Qwen2.5 0.5B, a 491 MB download."
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
  $("model-copy").textContent = offer;
  $("load-model").addEventListener("click", loadInBrowser);
  // Only once the model runs: it stops the model (whose files are open while it runs) and deletes them.
  $("remove-model").addEventListener("click", async () => {
    const { removeStored } = await import("./browser.js");
    try { await browserBackend.exit(); } catch {}
    browserBackend = null;
    await removeStored();
    $("remove-model").hidden = true;
    $("model-strip").classList.remove("ready");
    $("model-copy").textContent = offer;
    $("connection").className = "connection";
    $("connection").replaceChildren(document.createElement("i"), document.createTextNode("In-browser model"));
    setStatus("Removed the model from this browser.");
  });
  $("connection").className = "connection";
  $("connection").replaceChildren(document.createElement("i"), document.createTextNode("In-browser model"));
  $("backend").textContent = "cd_AI · IN-BROWSER LLM";
} else {
  checkConnection();
  setInterval(checkConnection, 15000);
}
