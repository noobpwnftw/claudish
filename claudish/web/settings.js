"use strict";
// The settings window (claudish/settings.py has the model). `claudish settings` and the macOS
// window open this page with a ticket in the fragment, which is never sent anywhere: the page
// trades it, once, for a token that opens settings only, keeps that for this window (a reload
// keeps working), and drops the ticket from the address.
const fragment = new URLSearchParams(location.hash.slice(1));
history.replaceState(null, "", location.pathname);
const $ = (id) => document.getElementById(id);
const VOICE_WORDS = "Your own words";
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
  if (!response.ok) throw new Error(data.error || `the service answered ${response.status}`);
  return data;
}

function say(id, text, bad) {
  $(id).textContent = text || "";
  $(id).classList.toggle("bad", Boolean(bad));
}

function ready(state) {
  const backend = (state.service || {}).backend;
  return (backend === "claude" && state.key !== "missing") || ((backend === "openai" || backend === "llama") && !state.server_problem);
}

function status(state) {
  const backend = (state.service || {}).backend;
  if (backend === "claude") return state.key === "missing" ? ["Add your Claude key below to start.", ""] : ["Ready: Claude writes for you.", "good"];
  if (state.server_problem) return [state.server_problem.charAt(0).toUpperCase() + state.server_problem.slice(1) + ".", "bad"];
  if (backend === "openai" || backend === "llama") return [`Ready: ${state.server.model || "your model"} writes for you.`, "good"];
  if (backend === "none") return ["Pick a model below to start.", ""];
  return ["cd_AI is running.", ""];
}

let shown = null;
function render(state) {
  shown = state;
  const [line, kind] = status(state);
  $("status").textContent = line;
  $("status").className = kind;
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
  $("models").replaceChildren(...state.server_models.map((name) => Object.assign(document.createElement("option"), {value: name})));
  voices(state);
}

function voices(state) {
  const group = $("voices");
  if (!group.childElementCount) {
    const rows = state.tones.map((tone) => voiceRow(tone.name, tone.name[0].toUpperCase() + tone.name.slice(1), tone.about));
    const own = voiceRow("", VOICE_WORDS, "A few words, such as “plain and friendly”.");
    own.classList.add("own");
    const words = document.createElement("input");
    words.type = "text";
    words.id = "own-words";
    words.maxLength = 200;
    words.setAttribute("aria-label", VOICE_WORDS);
    words.addEventListener("change", () => words.value.trim() && change({tone: words.value}, "voice-message", "Voice saved."));
    words.addEventListener("focus", () => { own.querySelector("input[type=radio]").checked = true; });
    own.querySelector("span").append(words);
    group.replaceChildren(...rows, own);
  }
  for (const radio of group.querySelectorAll("input[type=radio]")) {
    radio.checked = state.own_words ? radio.value === "" : radio.value === state.tone;
  }
  if (state.own_words && document.activeElement !== $("own-words")) $("own-words").value = state.tone;
}

function voiceRow(value, title, about) {
  const row = document.createElement("label");
  row.className = "row choice";
  const radio = document.createElement("input");
  radio.type = "radio";
  radio.name = "voice";
  radio.value = value;
  radio.addEventListener("change", () => {
    if (value) change({tone: value}, "voice-message", `${title} it is.`);
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

async function sample() {
  // One real rewrite in the chosen voice: what Tab will do, before you log out and try it.
  if (!shown || !ready(shown)) return;
  $("sample").hidden = false;
  $("sample").textContent = "Trying it: “ok” becomes…";
  try {
    const answer = await call("/suggest", {text: "ok", mode: "rewrite"});
    $("sample").textContent = `Trying it: “ok” becomes “${answer.text}”`;
  } catch (error) {
    $("sample").textContent = `The model did not answer: ${error.message}.`;
  }
}

async function change(body, message, done) {
  say(message, body.key ? "Checking the key with Anthropic…" : body.server ? "Checking the server…" : "");
  try {
    render(await call("/settings", body));
    say(message, done);
    sample();
    return true;
  } catch (error) {
    say(message, error.message.charAt(0).toUpperCase() + error.message.slice(1) + ".", true);
    return false;  // what you filled in stays, to correct
  }
}

document.querySelectorAll("input[name=choice]").forEach((radio) => radio.addEventListener("change", () => {
  if (radio.value === "claude") {
    change({choice: "claude"}, "model-message", "cd_AI now writes with Claude.");
  } else {  // a server must answer before cd_AI switches to it: fill it in first
    $("claude").hidden = true;
    $("server").hidden = false;
    say("model-message", "Fill in your server, then Use this server.");
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
  change({server: {url: $("url").value, model: $("model").value}, choice: "server"}, "model-message",
         "cd_AI now writes with your server.");
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
}
start().catch((error) => {
  $("status").textContent = error.message.charAt(0).toUpperCase() + error.message.slice(1) + ".";
  $("status").className = "bad";
});
