"use strict";
const $ = (id) => document.getElementById(id);
const draft = $("draft");
const output = $("output");
let revision = 0;
let candidate = "";
let timer;
let inflight = false;
let queued = false;
let composing = false;
let hosted = false;  // true when the service sends text to a hosted model
let backend = "";
let serviceTimeout = 3;  // seconds; the service reports its backend's timeout in /health
let mode = "rewrite";
const MODES = {
  rewrite: {title: "THE CLAUDISH EDIT", accept: "Accept rewrite", ask: "Rewrite", enter: "keep your wording", placeholder: "We should use a smaller model."},
  continue: {title: "THE CONTINUATION", accept: "Accept continuation", ask: "Continue", enter: "keep your wording", placeholder: "Thanks for the quick review on"},
  instruct: {title: "THE DRAFT", accept: "Accept draft", ask: "Write", enter: "send, then insert", placeholder: "decline the meeting politely, propose Thursday"},
};

function status(label) { $("candidate-state").textContent = label; }
function resetCandidate() {
  candidate = "";
  $("accept").disabled = true;
  $("candidate").textContent = mode === "instruct"
    ? (draft.value.trim() ? "Press Enter to send the instruction." : "Type an instruction,\nthen press Enter.")
    : draft.value.trim() ? "Considering your wording…" : "A nuanced perspective is\njust a keystroke away.";
  $("candidate").classList.add("placeholder");
  $("timing").textContent = hosted ? `${backend.toUpperCase()} · HOSTED MODEL` : "LOCAL MODEL · NO CLOUD REQUIRED";
  status(!draft.value.trim() ? "AWAITING A THOUGHT" : mode === "instruct" ? "ENTER SENDS" : "COMPOSING");
}

function edited() {
  revision++;
  queued = false;
  clearTimeout(timer);
  $("count").textContent = `${draft.value.length} / 512`;
  $("keep").disabled = !draft.value.trim();
  $("feedback").textContent = "";
  resetCandidate();
  // Rewrite and continue ask on every pause; an instruction waits for Enter.
  if (!composing && mode !== "instruct" && draft.value.trim().length >= 3) {
    timer = setTimeout(requestSuggestion, 180);
  }
}

async function requestSuggestion() {
  clearTimeout(timer);
  if (composing || draft.value.trim().length < 3) return;
  if (inflight) { queued = true; return; }
  queued = false;
  inflight = true;
  const current = revision;
  const text = draft.value;
  const started = performance.now();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), Math.max(hosted ? 15000 : 5000, serviceTimeout * 1000 + 2000));
  document.querySelector(".workspace").classList.add("busy");
  status(hosted ? "THINKING REMOTELY" : "THINKING LOCALLY");
  $("rewrite").disabled = true;
  try {
    const response = await fetch("/suggest", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, mode }), signal: controller.signal,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "The rewrite could not be completed.");
    if (current !== revision) return;
    candidate = data.text;
    $("candidate").textContent = candidate;
    $("candidate").classList.remove("placeholder");
    $("accept").disabled = false;
    const elapsed = Math.round(performance.now() - started);
    $("timing").textContent = `${elapsed} ms ROUND TRIP · ${Math.round(data.elapsed_ms)} ms ${data.backend === "rules" ? "RULES" : "INFERENCE"}`;
    status(data.backend === "rules" ? "RULES DEMO · READY" : "A THOUGHTFUL REVISION");
  } catch (error) {
    if (current === revision) {
      status("YOUR WORDS ARE STILL HERE");
      $("candidate").textContent = "The rewrite will have to wait.";
      $("feedback").textContent = error.name === "AbortError"
        ? "The model took too long. Try a shorter phrase, or keep your wording."
        : `${error.message} You can still keep your wording.`;
    }
  } finally {
    clearTimeout(timeout);
    inflight = false;
    $("rewrite").disabled = false;
    document.querySelector(".workspace").classList.remove("busy");
    if (queued) { queued = false; requestSuggestion(); }
  }
}

function commit(useCandidate) {
  const text = useCandidate ? candidate : draft.value;
  if (!text.trim()) return;
  output.value += (output.value ? "\n\n" : "") + text;
  $("copy").disabled = false;
  $("clear").disabled = false;
  draft.value = "";
  edited();
  $("feedback").textContent = useCandidate ? "Rewrite committed. Your next thought?" : "Your wording, committed.";
  draft.focus();
}

draft.addEventListener("beforeinput", (event) => {
  if (!composing && !event.isComposing && $("dash-toggle").checked && event.inputType === "insertText" && event.data === "-") {
    event.preventDefault();
    if (draft.value.length - (draft.selectionEnd - draft.selectionStart) >= 512) return;
    draft.setRangeText("—", draft.selectionStart, draft.selectionEnd, "end");
    edited();
  }
});
draft.addEventListener("input", edited);
draft.addEventListener("compositionstart", () => { composing = true; revision++; queued = false; clearTimeout(timer); resetCandidate(); });
draft.addEventListener("compositionend", () => { composing = false; edited(); });
draft.addEventListener("keydown", (event) => {
  if (event.isComposing || composing || event.ctrlKey || event.metaKey || event.altKey) return;
  if (event.key === "Tab" && !event.shiftKey && candidate) { event.preventDefault(); commit(true); }
  else if (event.key === "Enter" && !event.shiftKey && draft.value.trim()) {
    event.preventDefault();
    if (mode !== "instruct") commit(false);
    else if (candidate) commit(true);  // The second Enter inserts the result.
    else if (!inflight) requestSuggestion();  // The first sends the instruction.
  }
  else if (event.key === "Escape" && draft.value.trim()) { event.preventDefault(); commit(false); }
});
document.querySelectorAll('input[name="mode"]').forEach((input) => input.addEventListener("change", () => {
  mode = input.value;
  $("candidate-title").textContent = MODES[mode].title;
  $("accept-label").textContent = MODES[mode].accept;
  $("rewrite-label").textContent = MODES[mode].ask;
  $("enter-hint").textContent = MODES[mode].enter;
  draft.placeholder = MODES[mode].placeholder;
  edited();  // The old candidate belonged to another mode; ask again.
  draft.focus();
}));
$("accept").addEventListener("click", () => commit(true));
$("keep").addEventListener("click", () => commit(false));
$("rewrite").addEventListener("click", requestSuggestion);
document.querySelectorAll("[data-sample]").forEach((button) => button.addEventListener("click", () => {
  draft.value = button.dataset.sample;
  edited();
  draft.focus();
}));
$("copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(output.value);
    $("feedback").textContent = "Copied to clipboard.";
  } catch {
    output.focus();
    output.select();
    $("feedback").textContent = "Text selected. Press Ctrl+C (or Command+C) to copy.";
  }
});
$("clear").addEventListener("click", () => {
  output.value = "";
  $("copy").disabled = true;
  $("clear").disabled = true;
  $("feedback").textContent = "Committed text cleared.";
});

async function checkConnection() {
  try {
    const response = await fetch("/health", { signal: AbortSignal.timeout(3000) });
    if (!response.ok) throw new Error("unavailable");
    const data = await response.json();
    serviceTimeout = Number(data.timeout) || 3;
    if (hosted !== Boolean(data.hosted) || backend !== data.backend) {
      hosted = Boolean(data.hosted);
      backend = data.backend;
      $("inference-note").textContent = hosted ? "Hosted inference, as configured." : "Actual local inference.";
      if (!candidate) resetCandidate();
    }
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
checkConnection();
setInterval(checkConnection, 15000);
