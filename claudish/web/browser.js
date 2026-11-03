// In-browser backend for the static demo: llama.cpp compiled to WebAssembly (wllama), same templates
// as the service (templates.json is generated from claudish/modes.py).
// The page imports this module when you run the model or remove it; wllama loads only to run it.
const WLLAMA = "https://cdn.jsdelivr.net/npm/@wllama/wllama@3.8.1/esm/index.js";

const WASM = { default: "https://cdn.jsdelivr.net/npm/@wllama/wllama@3.8.1/esm/wasm/wllama.wasm" };

// The characters modes.finish joins without a space (wide, full-width or half-width, not a symbol,
// not Hangul), generated from its rule; tests/test_web_finish.py checks they still match.
const WIDE = /[\u{2329}-\u{232A}\u{3000}-\u{3003}\u{3005}-\u{3011}\u{3014}-\u{301F}\u{3021}-\u{302D}\u{3030}-\u{3035}\u{3038}-\u{303D}\u{3041}-\u{3096}\u{3099}-\u{309A}\u{309D}-\u{30FF}\u{3105}-\u{312F}\u{3192}-\u{3195}\u{31A0}-\u{31BF}\u{31F0}-\u{31FF}\u{3220}-\u{3229}\u{3251}-\u{325F}\u{3280}-\u{3289}\u{32B1}-\u{32BF}\u{3400}-\u{4DBF}\u{4E00}-\u{A48C}\u{F900}-\u{FAFF}\u{FE10}-\u{FE19}\u{FE30}-\u{FE52}\u{FE54}-\u{FE61}\u{FE63}\u{FE68}\u{FE6A}-\u{FE6B}\u{FF01}-\u{FF03}\u{FF05}-\u{FF0A}\u{FF0C}-\u{FF1B}\u{FF1F}-\u{FF3D}\u{FF3F}\u{FF41}-\u{FF5B}\u{FF5D}\u{FF5F}-\u{FF9F}\u{16FE0}-\u{16FE4}\u{16FF0}-\u{16FF1}\u{17000}-\u{187F7}\u{18800}-\u{18CD5}\u{18D00}-\u{18D08}\u{1AFF0}-\u{1AFF3}\u{1AFF5}-\u{1AFFB}\u{1AFFD}-\u{1AFFE}\u{1B000}-\u{1B122}\u{1B132}\u{1B150}-\u{1B152}\u{1B155}\u{1B164}-\u{1B167}\u{1B170}-\u{1B2FB}\u{20000}-\u{2FFFD}\u{30000}-\u{3FFFD}]/u;

// Port of claudish.modes.finish: a continuation is joined onto the typed text.
function finish(mode, text, output) {
  if (mode !== "continue") return output;
  // Small models sometimes echo the text before continuing it: only a whole echo, up to a word's
  // end ("I " then "in fact" is not one).
  // "In" after "I", "We're" after "We"; never after a Chinese or Japanese character
  const last = Array.from(text).pop() || " ";  // a whole character: 𠮷 is two UTF-16 units
  const wordGoesOn = (at) => !WIDE.test(last) && !WIDE.test(Array.from(output.slice(at))[0] || " ")
    && /^([\p{L}\p{N}]|['’]\p{L})/u.test(output.slice(at));
  const echo = text.trim();
  if (output.startsWith(text) && !(/[\p{L}\p{N}]$/u.test(text) && wordGoesOn(text.length))) output = output.slice(text.length);
  else if (echo && output.toLowerCase().startsWith(echo.toLowerCase()) && !wordGoesOn(echo.length)) {
    output = output.slice(echo.length);
  }
  output = output.trim();
  // Or wrap all of it in quotes: a pair around the whole, not one that closes your open quote.
  if (output.length > 2 && output[0] === '"' && output.endsWith('"') && !output.slice(1, -1).includes('"')
      && (text.split('"').length - 1) % 2 === 0) output = output.slice(1, -1).trim();
  if (/[ \n]$/.test(text)) output = output.replace(/^[,;: ]+/, "");
  if (!output) return "";
  // Chinese and Japanese take no spaces between words; Korean does, and an emoji is spaced as a word.
  const wide = WIDE;
  // No space after an em dash, an opening bracket or a quote you opened, nor before a mark that
  // goes on your last letter.
  const opened = /[—(\[“‘]$/.test(text) || (text.endsWith('"') && (text.split('"').length - 1) % 2 === 1);
  const joiner = /[ \n]$/.test(text) || ",.;:!?—)".includes(output[0]) || wide.test(last) || wide.test(Array.from(output)[0])
    || opened || /^\p{M}/u.test(output) ? "" : " ";
  return text + joiner + output;
}

// What this page keeps in the browser's storage, and a way to remove it.
// The page stores nothing but the model, so removing it clears the page's file storage.
export async function removeStored() {
  try {
    const root = await navigator.storage.getDirectory();
    for await (const name of root.keys()) await root.removeEntry(name, { recursive: true });
  } catch {}
}

// Without room to store the model (a small quota: a guest profile, a full disk), it runs from memory:
// downloaded each visit, never half-written into storage. wllama's own "no cache" path still writes.
async function inMemory(modelUrl, onProgress) {
  const response = await fetch(modelUrl);
  if (!response.ok) throw new Error(`model download failed (${response.status})`);
  const total = Number(response.headers.get("content-length")) || 0;
  const reader = response.body.getReader();
  const chunks = [];
  let loaded = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    loaded += value.byteLength;
    onProgress(loaded, total);
  }
  return new Blob(chunks);
}

// Port of claudish.modes.parroted: the template's own example answers (a small model given nonsense,
// "tttt", repeats its example), or words already before the caret, are not suggestions.
function parroted(mode, text, candidate, examples) {
  const answers = new Set(examples.filter((m) => m.role === "assistant").map((m) => m.content.trim().toLowerCase()));
  if (mode !== "continue") {
    const asked = new Set(examples.filter((m) => m.role === "user").map((m) => m.content.trim().toLowerCase()));
    return answers.has(candidate.trim().toLowerCase()) && !asked.has(text.trim().toLowerCase());
  }
  if (!candidate.startsWith(text)) return false;
  const rest = candidate.slice(text.length).trim().toLowerCase();
  if (!rest) return true;
  return answers.has(rest) || (rest.length >= 12 && text.toLowerCase().includes(rest));
}

export async function createBrowserBackend(templates, modelUrl, onProgress, onNote = () => {}) {
  const { Wllama } = await import(WLLAMA);
  const wllama = new Wllama(WASM);
  const options = { n_ctx: 2048, progressCallback: ({ loaded, total }) => onProgress(loaded, total) };
  const cached = (await wllama.modelManager.getModels()).some((model) => model.url === modelUrl);
  const { usage = 0, quota = Infinity } = (await navigator.storage?.estimate?.()) || {};
  const fits = cached || quota - usage > templates.model_bytes * 1.05;
  if (fits) {
    try {
      await wllama.loadModelFromUrl(modelUrl, options);
    } catch (error) {
      if (!/quota/i.test(`${error.name} ${error.message}`)) throw error;
      await removeStored();  // a half-written copy only takes up room
      onNote("This browser ran out of room for the model, so it runs from memory and downloads each visit.");
      await wllama.loadModel([await inMemory(modelUrl, onProgress)], { n_ctx: 2048 });
    }
  } else {
    onNote("This browser has no room to keep the model, so it runs from memory and downloads each visit.");
    await wllama.loadModel([await inMemory(modelUrl, onProgress)], { n_ctx: 2048 });
  }
  return {
    // Stops the model: while it runs, its worker holds the stored files open and they cannot be removed.
    async exit() { await wllama.exit(); },
    async suggest(text, mode) {
      const spec = templates.modes[mode];
      if (!spec) throw new Error(`Unknown mode: ${mode}`);
      const started = performance.now();
      const response = await wllama.createChatCompletion({
        // Continue quotes the text as a task (spec.frame), so the model continues it instead of answering it.
        messages: [{ role: "system", content: spec.system }, ...spec.examples,
                   { role: "user", content: spec.frame ? spec.frame.replace("{text}", text) : text }],
        max_tokens: spec.max_tokens || templates.max_tokens,
        temperature: 0,  // greedy, as on the service
      });
      const choice = response.choices[0];
      if (choice.finish_reason === "length") throw new Error("The rewrite ran past its length budget; try a shorter phrase.");
      const output = finish(mode, text, (choice.message.content || "").trim());
      if (!output || parroted(mode, text, output, spec.examples)) throw new Error("The model offered nothing for this.");
      return { text: output, backend: "browser", mode, elapsed_ms: performance.now() - started };
    },
  };
}
