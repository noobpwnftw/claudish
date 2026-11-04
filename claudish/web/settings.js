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
  }).catch(() => { throw Object.assign(new Error("cd_AI's service does not answer"), {down: true}); });
  // A 403: this window's token is gone (the service restarted), not a refusal to fix here.
  if (response.status === 403) throw Object.assign(new Error(reopen()), {expired: true});
  const data = await response.json().catch(() => ({}));
  const said = data.said && data.said !== "the request failed" ? data.said : "";  // plain words when they say more
  if (!response.ok) throw new Error(said || data.error || `the service answered ${response.status}`);
  return data;
}

// A sentence from an error; cd_AI's name and an address keep their case.
const sentence = (text) => (/^(cd_AI|https?:)/.test(text) ? text : text.charAt(0).toUpperCase() + text.slice(1)).replace(/\.?$/, ".");
const typed = () => (shown && shown.claudish) || "claudish";  // how claudish is run on this computer
const reopen = () => `this window has expired: open Settings again from cd_AI's menu (Settings…) or with \`${typed()} settings\``;

function say(id, text, bad) {
  $(id).textContent = text || "";
  $(id).classList.toggle("bad", Boolean(bad));
}

function subscription(state) {
  // A model process cd_AI runs: Claude Code, Codex, or a local model's server (its "command").
  const names = {"claude-code": "Claude Code", codex: "Codex", llama: "the local model"};
  const service = state.service || {};
  return service.backend === "llama" && !service.model ? null : names[service.backend] || null;
}

function ready(state) {
  const backend = (state.service || {}).backend;
  return (backend === "claude" && state.key !== "missing") || ((backend === "openai" || backend === "llama") && !state.server_problem)
    || (subscription(state) && (!(state.service || {}).model || state.service.model === "warm"));
}

function status(state) {
  const backend = (state.service || {}).backend;
  const problem = (state.service || {}).problem;
  if (problem) return [`cd_AI does not use its config: ${problem.replace(/\.$/, "")}.`, "bad"];
  const unavailable = (state.service || {}).unavailable;  // its model cannot run here: another can be picked
  if (unavailable) return [`cd_AI has no model: ${unavailable.replace(/\.$/, "")}.`, "bad"];
  const name = subscription(state);
  if (name) {
    const model = state.service.model || "warm";
    if (model.startsWith("failed:")) {  // most often not logged in: the CLI says so where you run it
      const why = model.slice(7).trim().replace(`${name}: `, "").replace(/\.$/, "");
      const run = state.command ? ` Run ${state.command} in a terminal and log in, then try a rewrite.` : "";
      return [`${name.charAt(0).toUpperCase() + name.slice(1)} could not start: ${why}.${run}`, "bad"];
    }
    if (model === "starting" || model === "restarting") return [`${model === "starting" ? "Starting" : "Restarting"} ${name}…`, ""];
    return [`Ready: ${name} writes for you.`, "good"];
  }
  if (backend === "claude") return state.key === "missing" ? [locked(state) ? "No Claude key yet." : "Add your Claude key below to start.", ""]
    : ["Ready: Claude writes for you.", "good"];
  if (state.server_problem) return [sentence(state.server_problem), "bad"];
  if (backend === "openai" || backend === "llama") return [`Ready: ${state.model || "your model"} writes for you.`, "good"];
  if (backend === "none") return ["Pick a model below to start.", ""];
  return ["cd_AI is running.", ""];
}

let shown = null, viewVersion = 0, sampleVersion = 0, healthTimer, lockTimer, toneTimer, started = false;
// Every change would be refused while the config in use does not read: the file comes first.
const locked = (state) => Boolean((state.service || {}).problem || state.config_locked);

async function recheck() {
  try {
    render(await call("/settings/state"));
  } catch (error) {
    if (error.expired) return lost(error);
    lockTimer = setTimeout(recheck, 500);
  }
}

function lost(error) {
  // The service is gone, or this window's token is: only that, as for a config that does not read.
  if (!error.down && !error.expired) return false;
  clearTimeout(healthTimer);
  clearTimeout(lockTimer);
  $("status").textContent = error.expired ? sentence(error.message)
    : `cd_AI's service is not running. Start it with \`${typed()} service install\`, then open Settings again.`;
  $("status").className = "bad";
  $("controls").hidden = true;
  $("config-fix").hidden = true;
  if (error.down) lockTimer = setTimeout(recheck, 500);
  return true;
}

function showStatus(state) {
  const [line, kind] = status(state);
  $("status").textContent = line;
  $("status").className = kind;
  if (kind === "bad" && subscription(state)) say("model-message", "");  // not "now writes with" beside it
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
      if (version === viewVersion && !lost(error)) say("status", error.message, true);
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
  const [asks, keeps] = state.summon === "Enter" ? ["Enter", "Shift+Enter"] : ["Shift+Enter", "Enter"];
  const kbd = (keys) => keys.split("+").map((key) => `<kbd>${key}</kbd>`).join("+");
  $("next-keys").innerHTML = `${kbd(asks)} asks the model; ${kbd(keeps)} keeps your words.`;
  // The service's own problem is in the status line; another profile's, the window may switch to, here.
  const problem = (state.service || {}).problem ? "" : state.config_problem;
  $("config-fix").hidden = !((state.service || {}).problem || state.config_problem);
  if (started) $("controls").hidden = locked(state);  // only what fails, and how to fix it
  clearTimeout(lockTimer);
  if (locked(state)) lockTimer = setTimeout(recheck, 500);  // the fix applies when the file is saved
  $("config-fix").textContent = (problem ? `A model you can pick here does not read: ${problem}. ` : "") +
    `Fix it in ${state.config} (it applies when you save), or move that file aside and run ${typed()} init.`;
  for (const radio of document.querySelectorAll("input[name=choice]")) radio.checked = radio.value === state.choice;
  $("claude").hidden = state.choice !== "claude";
  $("try").hidden = false;  // the model in use; hidden while another is picked but not yet in use
  $("server").hidden = state.choice !== "server";
  $("other").hidden = !["local", "other"].includes(state.choice);
  $("other").textContent = state.choice === "local"
    ? "cd_AI uses the local model that `claudish setup --profile local` set up. Pick one above to change that."
    : `cd_AI uses the profile “${state.profile}” from its config. Pick one above to change that.`;
  $("key-state").textContent = {saved: `Saved in ${state.key_where}`, missing: "Not set",
                                profile: "Your `ant auth login` profile (a saved key goes first)",
                                environment: `${state.key_env} in your environment (used before a saved key)`}[state.key];
  $("key-state").classList.toggle("good", state.key !== "missing");
  if (document.activeElement !== $("url")) $("url").value = state.server.url;
  if (document.activeElement !== $("model")) $("model").value = state.server.model;
  $("server-key-state").textContent = state.server.key === "saved" ? `Key saved for this address in ${state.server.key_where}` : "";
  $("models").replaceChildren(...state.server_models.map((name) => Object.assign(document.createElement("option"), {value: name})));
  tones(state);
  for (const radio of document.getElementsByName("summon")) radio.checked = radio.value === state.summon;
  for (const radio of document.getElementsByName("hints")) radio.checked = radio.value === (state.hints === false ? "off" : "on");
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
    words.addEventListener("blur", () => { if (!words.value.trim() && shown) tones(shown); });  // nothing saved: the tone in use
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
    clearTimeout(toneTimer);  // ↑↓ through the list: only where it stops is saved (and tried)
    if (value) toneTimer = setTimeout(() => change({tone: value}, "tone-message", `${title} it is.`), 400);
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
    if (lost(error)) return;
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
  const keys = ["summon", "hints"].includes(Object.keys(body).join());  // keys and hints change no rewrite: no new example
  if (!keys) {
    sampleVersion++;
    $("sample").hidden = true;
  }
  say(message, body.key ? "Checking the key with Anthropic…" : body.server ? "Checking the API…" : "");
  try {
    render(await call("/settings", body));
    say(message, done);
    if (!keys) sample();
    return true;
  } catch (error) {
    if (lost(error)) {
      say(message, "");
      return false;
    }
    say(message, sentence(error.message), true);
    if (shown) showStatus(shown);
    return false;  // what you filled in stays, to correct
  }
}

document.querySelectorAll("input[name=choice]").forEach((radio) => radio.addEventListener("change", () => {
  if (radio.value === "claude") {
    change({choice: "claude"}, "model-message", "cd_AI now writes with Claude.").then((done) => {
      if (done && shown && shown.key === "missing") say("model-message", "");  // nothing writes yet: the status says what to add
      if (!done && shown) render(shown);  // not switched: the radio goes back to what is in use
    });
  } else if (radio.value === "claude-code" || radio.value === "codex") {
    $("claude").hidden = $("server").hidden = true;
    const name = radio.value === "codex" ? "Codex" : "Claude Code";
    change({choice: radio.value}, "model-message", `cd_AI now writes with ${name}.`).then((done) => {
      if (!done && shown) render(shown);  // not switched: the radio goes back to what is in use
    });
  } else {  // an API must answer before cd_AI switches to it: fill it in first
    $("claude").hidden = true;
    $("server").hidden = false;
    $("try").hidden = $("sample").hidden = shown && shown.choice !== "server";
    say("model-message", "Fill in the API, then Use this API.");
  }
}));
$("claude").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("claude").querySelector("button");
  button.disabled = true;
  const environment = shown && shown.key === "environment";
  if (await change({key: $("key").value}, "model-message", environment
    ? `Key saved. ${shown.key_env} in your environment is still used first.` : "Key saved. Anthropic accepted it.")) {
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
  started = true;
  $("controls").disabled = false;
  $("controls").hidden = locked(shown);
}
start().catch((error) => {
  if (lost(error)) return;
  $("status").textContent = sentence(error.message);
  $("status").className = "bad";
});

for (const radio of document.getElementsByName("hints")) {
  radio.addEventListener("change", () => change({hints: radio.value === "on"}, "hints-message",
                                                radio.value === "on" ? "Hints show." : "The panel shows only what is pending."));
}
for (const radio of document.getElementsByName("summon")) {
  radio.addEventListener("change", () => change({summon: radio.value}, "keys-message", `${radio.value} asks the model.`));
}
