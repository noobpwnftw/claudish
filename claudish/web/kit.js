"use strict";
// The one look at the caret (kit.css), built from a panel description in the shape of Claudish's
// Composition.panel() (claudish/composition.py): the demo and the design lab draw from it, as the
// input methods do on each platform (docs/design/design.md). Nodes, not HTML: the words come
// from a model.
(() => {
  // The AI tile's letters, drawn: centred the same in every font and browser (a text "AI" sat high).
  const AI_MARK = '<svg viewBox="0 0 18 18" width="18" height="18" aria-hidden="true"><path d="M4 12.65 6.5 5.9 9 12.65M4.95 10.3h3.1M10.55 5.9h4.2M12.65 5.9v6.2M10.55 12.1h4.2" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="bevel"/></svg>';
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  };

  // A key and its verb: a keycap ("Tab"; a platform may name it, as macOS's ⇥) and the word.
  function hint(key, verb, keys) {
    const span = el("span", "k-hint");
    span.append(el("span", "k-cap", keys[key] || key), verb);
    return span;
  }

  // The footer: the AI tile (or a warning mark, or continue's neutral tile), what is happening,
  // each key with its verb, and the free words.
  function footer(spec, keys) {
    const foot = el("div", "k-foot");
    if (spec.tile === "warn") foot.append(el("span", "k-warn", "!"));  // a failure reads without colour
    else if (spec.tile === "cd") foot.append(el("span", "k-tile cd", "cd"));
    else {
      const mark = el("span", "k-tile ai");
      mark.setAttribute("role", "img");
      mark.setAttribute("aria-label", "AI");
      mark.innerHTML = AI_MARK;
      foot.append(mark);
    }
    if (spec.status) {
      const status = el("span", "k-status");
      if (spec.busy) status.append(el("span", "k-spin"));
      status.append(spec.status);
      foot.append(status);
    }
    if (spec.failed) foot.append(el("span", "k-status failed", spec.failed));
    for (const [key, verb] of spec.foot || []) foot.append(hint(key, verb, keys));
    if (spec.tail) foot.append(el("span", "k-hint", spec.tail));
    return foot;
  }

  // The panel: an optional header (a small label, then the content as is), the rows (the
  // highlighted one carries the key that takes it; every row keeps that column), the footer.
  // pick(number): a click on a row.
  function panel(spec, keys = {}, pick = null) {
    const rows = spec.rows || [];
    const thread = spec.thread || [];
    const node = el("div", "k-panel" + (rows.length || spec.body || thread.length ? "" : " bare") + (spec.on >= 0 ? " takes" : "")
                         + (spec.replying ? " replying" : ""));
    // The exchange so far, as labelled turns ("You asked", "You answered"): your words at full size.
    for (const turn of thread) {
      const head = el("div", "k-head k-turn");
      head.append(el("span", "k-label", turn.label), el("span", "k-body", turn.body));
      node.append(head);
    }
    if (spec.body) {
      const head = el("div", "k-head");
      if (spec.label) head.append(el("span", "k-label", spec.label));
      head.append(el("span", "k-body" + (spec.code ? " code" : ""), spec.body));
      node.append(head);
    }
    rows.forEach((row, index) => {
      const line = el("div", "k-row" + (index === spec.on ? " on" : ""));
      const words = el("span", "k-text" + (spec.mono ? " k-mono" : ""), row.text);
      if (row.legend) words.append(el("span", "k-legend", " — " + row.legend));
      line.append(words);
      if (index === spec.on) {
        const take = el("span", "k-take");
        const key = spec.take || "Tab";  // Tab takes a draft or a choice
        take.append(el("span", "k-cap" + (spec.nudge ? " lit" : ""), keys[key] || key));  // lit: Enter was pressed on it
        line.append(take);
      }
      if (pick) line.addEventListener("mousedown", (event) => { event.preventDefault(); pick(index + 1); });
      node.append(line);
    });
    node.append(footer(spec, keys));
    return node;
  }

  // The mode switch: a panel with only a footer, briefly at the caret.
  function toast(spec, keys = {}) {
    const node = el("div", "k-toast");
    for (const child of footer(spec, keys).childNodes) node.append(child.cloneNode(true));
    return node;
  }

  window.Kit = {panel, toast};
})();
