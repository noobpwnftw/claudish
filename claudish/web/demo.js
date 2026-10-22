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
// The static build (scripts/build_static_demo.py) runs the model in this page instead of calling a service.
const IN_BROWSER = document.querySelector('meta[name="claudish-backend"]')?.content === "browser";
let browserBackend = null;
const MODES = {
  rewrite: {title: "THE CLAUDISH EDIT", accept: "Accept rewrite", ask: "Rewrite", enter: "keep your wording", prompt: "NEED A FIRST THOUGHT?",
    samples: ["This is very important.", "Let's explore the options.", "We should use a smaller model."], placeholder: "Type something ordinary…"},
  continue: {title: "THE CONTINUATION", accept: "Accept continuation", ask: "Continue", enter: "keep your wording", prompt: "START A SENTENCE",
    samples: ["Thanks for the quick review on", "We should postpone the launch until", "The best part of this release is"], placeholder: "Start a sentence…"},
  instruct: {title: "THE DRAFT", accept: "Accept draft", ask: "Write", enter: "send, then insert", prompt: "TRY AN INSTRUCTION",
    samples: ["decline the meeting politely, propose Thursday", "thank the team for shipping the release", "write a two-line story about a cat"], placeholder: "Type an instruction, then press Enter…"},
};

function status(label) { $("candidate-state").textContent = label; }
function resetCandidate() {
  candidate = "";
  $("accept").disabled = true;
  $("candidate").textContent = IN_BROWSER && !browserBackend ? "Run the model above, then type something ordinary."
    : mode === "instruct"
    ? (draft.value.trim() ? "Press Enter to send the instruction." : "Type an instruction, then press Enter.")
    : draft.value.trim() ? "Considering your wording…" : "A nuanced perspective is just a keystroke away.";
  $("candidate").classList.add("placeholder");
  $("timing").textContent = hosted ? `${backend.toUpperCase()} · HOSTED MODEL` : "LOCAL\u00a0MODEL\u00a0· NO\u00a0CLOUD\u00a0REQUIRED";
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
  if (!composing && mode !== "instruct" && draft.value.trim().length >= 3 && (!IN_BROWSER || browserBackend)) {
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
    let data;
    if (IN_BROWSER) {
      if (!browserBackend) throw new Error("Load the model first.");
      data = await browserBackend.suggest(text, mode);
    } else {
      const response = await fetch("/suggest", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, mode }), signal: controller.signal,
      });
      data = await response.json();
      if (!response.ok) throw new Error(data.error || "The rewrite could not be completed.");
    }
    if (current !== revision) return;
    candidate = data.text;
    $("candidate").textContent = candidate;
    $("candidate").classList.remove("placeholder");
    $("accept").disabled = false;
    const elapsed = Math.round(performance.now() - started);
    $("timing").textContent = data.backend === "browser" ? `${elapsed} ms IN THIS BROWSER`
      : `${elapsed} ms ROUND TRIP · ${Math.round(data.elapsed_ms)} ms ${data.backend === "rules" ? "RULES" : "INFERENCE"}`;
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
  renderSamples();
  draft.placeholder = MODES[mode].placeholder;
  edited();  // The old candidate belonged to another mode; ask again.
  draft.focus();
}));
$("accept").addEventListener("click", () => commit(true));
$("keep").addEventListener("click", () => commit(false));
$("rewrite").addEventListener("click", requestSuggestion);
function renderSamples() {
  $("samples-label").textContent = MODES[mode].prompt;
  const buttons = MODES[mode].samples.map((sample) => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.sample = sample;
    button.textContent = sample + " ↗";
    return button;
  });
  $("samples").replaceChildren($("samples-label"), ...buttons);
}
// One listener for every chip: samples change with the mode. Instruct samples wait for Enter.
$("samples").addEventListener("click", (event) => {
  const button = event.target.closest("[data-sample]");
  if (!button) return;
  draft.value = button.dataset.sample;
  edited();
  draft.focus();
});
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
    edited();
  } catch (error) {
    strip.classList.remove("loading");
    $("load-model").textContent = "Try loading the model again";
    $("feedback").textContent = `The model could not start here: ${error.message}`;
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
} else {
  checkConnection();
  setInterval(checkConnection, 15000);
}
