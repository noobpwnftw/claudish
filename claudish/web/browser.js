// In-browser backend for the static demo: llama.cpp compiled to WebAssembly (wllama), same templates
// as the service (templates.json is generated from claudish/modes.py). Typed text never leaves the page.
import { Wllama } from "https://cdn.jsdelivr.net/npm/@wllama/wllama@3.8.1/esm/index.js";

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

export async function createBrowserBackend(templates, modelUrl, onProgress) {
  const wllama = new Wllama(WASM);
  await wllama.loadModelFromUrl(modelUrl, {
    n_ctx: 2048,
    progressCallback: ({ loaded, total }) => onProgress(loaded, total),
  });
  return {
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
      if (!output) throw new Error("The model offered nothing for this.");
      return { text: output, backend: "browser", mode, elapsed_ms: performance.now() - started };
    },
  };
}
