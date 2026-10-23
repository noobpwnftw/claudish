// In-browser backend for the static demo: llama.cpp compiled to WebAssembly (wllama), same templates
// as the service (templates.json is generated from claudish/modes.py). Typed text never leaves the page.
// wllama loads only when the model runs: the page imports this module on every visit to measure
// what is stored.
const WLLAMA = "https://cdn.jsdelivr.net/npm/@wllama/wllama@3.8.1/esm/index.js";

const WASM = { default: "https://cdn.jsdelivr.net/npm/@wllama/wllama@3.8.1/esm/wasm/wllama.wasm" };

// Port of claudish.modes.finish: a continuation is joined onto the typed text.
function finish(mode, text, output) {
  if (mode !== "continue") return output;
  // Small models sometimes echo the text, or its last words, before continuing it.
  if (output.startsWith(text)) output = output.slice(text.length);
  else if (text.trim() && output.toLowerCase().startsWith(text.trim().toLowerCase())) output = output.slice(text.trim().length);
  output = output.trim().replace(/^"|"$/g, "").trim();
  if (/[ \n]$/.test(text)) output = output.replace(/^[,;: ]+/, "");
  if (!output) return "";
  const joiner = /[ \n]$/.test(text) || ",.;:!?—)".includes(output[0]) ? "" : " ";
  return text + joiner + output;
}

// What this page keeps in the browser's storage, and a way to remove it.
// What this site keeps in the browser is only the model (the page itself stores nothing), so the
// whole origin-private file system and Cache Storage are measured and removed: wllama's cache
// manager knows only its finished files, and a download cut short (no room) or an older version's
// files stayed behind, still counted by the browser and impossible to remove from the page.
async function walk(directory, visit) {
  for await (const [name, handle] of directory.entries()) {
    if (handle.kind === "directory") await walk(handle, visit);
    else await visit(directory, name, handle);
  }
}
export async function storedBytes() {
  let bytes = 0;
  try {
    await walk(await navigator.storage.getDirectory(), async (_, __, handle) => {
      bytes += (await handle.getFile()).size;
    });
  } catch {}
  try {
    for (const name of await caches.keys()) {
      const cache = await caches.open(name);
      for (const request of await cache.keys()) {
        const response = await cache.match(request);
        bytes += Number(response?.headers.get("content-length") || 0);
      }
    }
  } catch {}
  return bytes;
}
export async function removeStored() {
  try {
    const root = await navigator.storage.getDirectory();
    for await (const name of root.keys()) await root.removeEntry(name, { recursive: true });
  } catch {}
  try { for (const name of await caches.keys()) await caches.delete(name); } catch {}
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

// Port of claudish.modes.parroted: the template's own example answers, or words already before the
// caret, are not suggestions.
function parroted(mode, text, candidate, examples) {
  if (mode !== "continue" || !candidate.startsWith(text)) return false;
  const rest = candidate.slice(text.length).trim().toLowerCase();
  if (!rest) return true;
  const answers = new Set(examples.filter((m) => m.role === "assistant").map((m) => m.content.trim().toLowerCase()));
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
