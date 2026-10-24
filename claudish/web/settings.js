"use strict";
// The settings window (claudish/settings.py has the model). `claudish settings` and the macOS
// window open this page with a ticket in the fragment; the page trades it for a settings token,
// keeps that for this window, and drops the ticket from the address.
const fragment = new URLSearchParams(location.hash.slice(1));
history.replaceState(null, "", location.pathname);
const $ = (id) => document.getElementById(id);
const TONE_WORDS = "Described";
const remember = (name, value) => { try { sessionStorage.setItem(name, value); } catch (error) { /* private window */ } };
const recall = (name) => { try { return sessionStorage.getItem(name); } catch (error) { return null; } };
if (fragment.get("first")) remember("cd_AI-first", "1");
let token = recall("cd_AI-settings");

async function call(path, body) {
  const response = await fetch(path, {
    method: body ? "POST" : "GET",
    headers: Object.assign({"X-Claudish-Settings": token || ""}, body ? {"Content-Type": "application/json"} : {}),
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  const said = data.said && data.said !== "the request failed" ? data.said : "";  // plain words when they say more
  if (!response.ok) throw new Error(said || data.error || `the service answered ${response.status}`);
  return data;
}

function say(id, text, bad) {
  $(id).textContent = text || "";
  $(id).classList.toggle("bad", Boolean(bad));
}

function subscription(state) {
  const names = {"claude-code": "Claude Code", codex: "Codex"};
  const backend = (state.service || {}).backend;
  return names[backend] || (backend === "command" ? names[state.choice] : null);
}

function ready(state) {
  const backend = (state.service || {}).backend;
  return (backend === "claude" && state.key !== "missing") || ((backend === "openai" || backend === "llama") && !state.server_problem)
    || (subscription(state) && (!(state.service || {}).model || state.service.model === "warm"));
}

function status(state) {
  const backend = (state.service || {}).backend;
  const name = subscription(state);
  if (name) {
    const model = state.service.model || "warm";
    if (model.startsWith("failed:")) return [`${name} could not start: ${model.slice(7).trim()}`, "bad"];
    if (model === "starting" || model === "restarting") return [`${model === "starting" ? "Starting" : "Restarting"} ${name}…`, ""];
    if (model === "stopped") return [`${name} is stopped. Pick it again below to start it.`, "bad"];
    return [`Ready: ${name} writes for you.`, "good"];
  }
  if (backend === "claude") return state.key === "missing" ? ["Add your Claude key below to start.", ""] : ["Ready: Claude writes for you.", "good"];
  if (state.server_problem) return [state.server_problem.charAt(0).toUpperCase() + state.server_problem.slice(1) + ".", "bad"];
  if (backend === "openai" || backend === "llama") return [`Ready: ${state.server.model || "your model"} writes for you.`, "good"];
  if (backend === "none") return ["Pick a model below to start.", ""];
  return ["cd_AI is running.", ""];
}

let shown = null, viewVersion = 0, sampleVersion = 0, healthTimer;
function showStatus(state) {
  const [line, kind] = status(state);
  $("status").textContent = line;
  $("status").className = kind;
  $("try").querySelector("button").disabled = !ready(state) &&
    !(subscription(state) && (state.service.model || "").startsWith("failed:"));
}

function followStartup(version) {
  if (!shown || !["starting", "restarting"].includes((shown.service || {}).model)) return;
  healthTimer = setTimeout(async () => {
    try {
      const service = await call("/health");
      if (version !== viewVersion) return;
      shown.service = service;
      showStatus(shown);
      followStartup(version);
    } catch (error) {
      if (version === viewVersion) say("status", error.message, true);
    }
  }, 500);
}

function render(state) {
  shown = state;
  viewVersion++;
  sampleVersion++;  // an older model or tone must never supply the displayed example
  clearTimeout(healthTimer);
  $("sample").hidden = true;
  showStatus(state);
  followStartup(viewVersion);
  $("next").hidden = !recall("cd_AI-first");
  for (const radio of document.querySelectorAll("input[name=choice]")) radio.checked = radio.value === state.choice;
  $("claude").hidden = state.choice !== "claude";
  $("server").hidden = state.choice !== "server";
  $("other").hidden = !["local", "other"].includes(state.choice);
  $("other").textContent = state.choice === "local"
    ? "cd_AI uses the local model that `claudish setup --profile local` set up. Pick one above to change that."
    : `cd_AI uses the profile “${state.profile}” from its config. Pick one above to change that.`;
  $("key-state").textContent = {saved: `Saved in ${state.key_where}`, missing: "Not set",
                                environment: "ANTHROPIC_API_KEY in your environment (used before a saved key)"}[state.key];
  $("key-state").classList.toggle("good", state.key !== "missing");
  if (document.activeElement !== $("url")) $("url").value = state.server.url;
  if (document.activeElement !== $("model")) $("model").value = state.server.model;
  $("server-key-state").textContent = state.server.key === "saved" ? `Key saved for this address in ${state.key_where}` : "";
  $("models").replaceChildren(...state.server_models.map((name) => Object.assign(document.createElement("option"), {value: name})));
  tones(state);
}

function tones(state) {
  const group = $("tones");
  if (!group.childElementCount) {
    const rows = state.tones.map((tone) => toneRow(tone.name, tone.name[0].toUpperCase() + tone.name.slice(1), tone.about));
    const own = toneRow("", TONE_WORDS, "A few words, such as “plain and friendly”.");
    own.classList.add("own");
    const words = document.createElement("input");
    words.type = "text";
    words.id = "own-words";
    words.maxLength = 200;
    words.setAttribute("aria-label", TONE_WORDS);
    words.addEventListener("change", () => words.value.trim() && change({tone: words.value}, "tone-message", "Tone saved."));
    words.addEventListener("focus", () => { own.querySelector("input[type=radio]").checked = true; });
    own.querySelector("span").append(words);
    group.replaceChildren(...rows, own);
  }
  for (const radio of group.querySelectorAll("input[type=radio]")) {
    radio.checked = state.own_words ? radio.value === "" : radio.value === state.tone;
  }
  if (state.own_words && document.activeElement !== $("own-words")) $("own-words").value = state.tone;
}

function toneRow(value, title, about) {
  const row = document.createElement("label");
  row.className = "row choice";
  const radio = document.createElement("input");
  radio.type = "radio";
  radio.name = "tone";
  radio.value = value;
  radio.addEventListener("change", () => {
    if (value) change({tone: value}, "tone-message", `${title} it is.`);
    else $("own-words").focus();
  });
  const text = document.createElement("span");
  const strong = document.createElement("strong");
  strong.textContent = title;
  const small = document.createElement("small");
  small.textContent = about;
  text.append(strong, small);
  row.append(radio, text);
  return row;
}

async function sample(manual = false) {
  // One real rewrite in the chosen tone: what Tab will do, before you log out and try it.
  if (!shown || (!ready(shown) && !(manual && subscription(shown)))) return;
  const text = $("try-text").value.trim();
  if (!text) return;
  const version = ++sampleVersion;
  const button = $("try").querySelector("button");
  button.disabled = true;
  $("sample").hidden = false;
  $("sample").textContent = `Trying it: “${text}” becomes…`;
  try {
    const answer = await call("/suggest", {text, mode: "rewrite"});
    if (version !== sampleVersion) return;
    if (!answer.text) throw new Error("no rewrite was returned");
    $("sample").textContent = `“${text}” → “${answer.text}”`;
  } catch (error) {
    if (version !== sampleVersion) return;
    $("sample").textContent = `The model did not answer: ${error.message}.`;
  } finally {
    if (version === sampleVersion) {
      if (subscription(shown)) {
        try {
          const service = await call("/health");
          if (version !== sampleVersion) return;
          shown.service = service;
          showStatus(shown);
          followStartup(viewVersion);
        } catch (error) { /* the rewrite already reports a service failure */ }
      }
      button.disabled = false;
    }
  }
}

async function change(body, message, done) {
  sampleVersion++;
  $("sample").hidden = true;
  say(message, body.key ? "Checking the key with Anthropic…" : body.server ? "Checking the API…" : "");
  try {
    render(await call("/settings", body));
    say(message, done);
    sample();
    return true;
  } catch (error) {
    say(message, error.message.charAt(0).toUpperCase() + error.message.slice(1) + ".", true);
    if (shown) showStatus(shown);
    return false;  // what you filled in stays, to correct
  }
}

document.querySelectorAll("input[name=choice]").forEach((radio) => radio.addEventListener("change", () => {
  if (radio.value === "claude") {
    change({choice: "claude"}, "model-message", "cd_AI now writes with Claude.");
  } else if (radio.value === "claude-code" || radio.value === "codex") {
    $("claude").hidden = $("server").hidden = true;
    const name = radio.value === "codex" ? "Codex" : "Claude Code";
    change({choice: radio.value}, "model-message", `cd_AI now writes with ${name}.`).then((done) => {
      if (!done && shown) render(shown);  // not switched: the radio goes back to what is in use
    });
  } else {  // an API must answer before cd_AI switches to it: fill it in first
    $("claude").hidden = true;
    $("server").hidden = false;
    say("model-message", "Fill in the API, then Use this API.");
  }
}));
$("claude").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("claude").querySelector("button");
  button.disabled = true;
  const environment = shown && shown.key === "environment";
  if (await change({key: $("key").value}, "model-message", environment
    ? "Key saved. ANTHROPIC_API_KEY in your environment is still used first." : "Key saved. Anthropic accepted it.")) {
    $("key").value = "";
  }
  button.disabled = false;
});
$("server").addEventListener("submit", (event) => {
  event.preventDefault();
  change({server: {url: $("url").value, model: $("model").value, key: $("server-key").value}, choice: "server"},
         "model-message", "cd_AI now writes with this API.").then((done) => { if (done) $("server-key").value = ""; });
});
$("try").addEventListener("submit", (event) => {
  event.preventDefault();
  sample(true);
});

async function start() {
  const ticket = fragment.get("ticket");
  if (ticket) {
    try {
      token = (await call("/settings/session", {ticket})).token;
      remember("cd_AI-settings", token);
    } catch (error) {
      if (!token) throw error;
    }
  }
  if (!token) throw new Error("open this from cd_AI's menu (Settings…) or with `claudish settings`");
  render(await call("/settings/state"));
  $("controls").disabled = false;
}
start().catch((error) => {
  $("status").textContent = error.message.charAt(0).toUpperCase() + error.message.slice(1) + ".";
  $("status").className = "bad";
});
