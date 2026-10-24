"use strict";
// The settings window (claudish/settings.py has the model). The window opens this page with the
// service token in the fragment, which is never sent anywhere; it is dropped from the address at
// once and kept only in this page.
const token = new URLSearchParams(location.hash.slice(1)).get("token");
history.replaceState(null, "", location.pathname);
const $ = (id) => document.getElementById(id);
const VOICE_WORDS = "Your own words";

async function call(method, body) {
  const response = await fetch("/settings" + (method === "GET" ? "/state" : ""), {
    method,
    headers: Object.assign({"X-Claudish-Token": token || ""}, body ? {"Content-Type": "application/json"} : {}),
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

function status(state) {
  const service = state.service || {};
  if (state.problem) return [`Saved, but cd_AI could not use it: ${state.problem}`, "bad"];
  if (service.backend === "claude") {
    return state.key === "missing" ? ["Ready once you save a Claude key below.", "bad"] : ["Ready: Claude writes for you.", "good"];
  }
  if (service.backend === "openai" || service.backend === "llama") return [`Ready: ${state.server.model || "your model"} writes for you.`, "good"];
  if (service.backend === "none") return ["No model yet: pick one below.", "bad"];
  return [`Running with the ${service.backend} backend.`, ""];
}

let shown = null;
function render(state) {
  shown = state;
  const [line, kind] = status(state);
  $("status").textContent = line;
  $("status").className = kind;
  for (const radio of document.querySelectorAll("input[name=choice]")) radio.checked = radio.value === state.choice;
  $("claude").hidden = state.choice !== "claude";
  $("server").hidden = state.choice !== "server";
  $("other").hidden = !["local", "other"].includes(state.choice);
  $("other").textContent = state.choice === "local"
    ? "cd_AI uses the local model that `claudish setup --profile local` set up. Pick one above to change that."
    : `cd_AI uses the profile “${state.profile}” from its config. Pick one above to change that.`;
  $("key-state").textContent = {saved: `Saved in ${state.key_where}`, environment: "From ANTHROPIC_API_KEY",
                                missing: "Not set"}[state.key];
  $("key-state").classList.toggle("good", state.key !== "missing");
  if (document.activeElement !== $("url")) $("url").value = state.server.url;
  if (document.activeElement !== $("model")) $("model").value = state.server.model;
  $("config").textContent = state.config;
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

async function change(body, message, done) {
  say(message, body.key ? "Checking the key with Anthropic…" : "");
  try {
    const state = await call("POST", body);
    render(state);
    say(message, state.problem ? "" : done);
    return true;
  } catch (error) {
    say(message, error.message.charAt(0).toUpperCase() + error.message.slice(1) + ".", true);
    if (shown) render(shown);
    return false;
  }
}

document.querySelectorAll("input[name=choice]").forEach((radio) => radio.addEventListener("change", () =>
  change({choice: radio.value}, "model-message", radio.value === "claude" ? "cd_AI now writes with Claude." : "cd_AI now writes with your model server.")));
$("claude").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("claude").querySelector("button");
  button.disabled = true;
  if (await change({key: $("key").value}, "model-message", "Key saved. Anthropic accepted it.")) $("key").value = "";
  button.disabled = false;
});
$("server").addEventListener("submit", (event) => {
  event.preventDefault();
  change({server: {url: $("url").value, model: $("model").value}}, "model-message", "Saved.");
});

if (!token) {
  $("status").textContent = "Open this from cd_AI's menu: Settings…";
  $("status").className = "bad";
} else {
  call("GET").then(render).catch((error) => {
    $("status").textContent = `cd_AI's service did not answer (${error.message}).`;
    $("status").className = "bad";
  });
}
