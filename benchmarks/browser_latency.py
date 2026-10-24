"""Time a model in the browser, as the static demo runs it (wllama, llama.cpp in WebAssembly) (G53).

python benchmarks/browser_latency.py --model models/X.gguf [--cases 20] [--executable chromium]

Builds the static demo, serves it and the model from a plain static server, loads the model in
headless Chromium (cross-origin isolated, so threaded), and times continue and rewrite on the
first cases of the evaluation sets, after one warm-up request each. Reports the load time and the
median and p95 per mode, as JSON. The hardware is the machine running the browser.
"""
import argparse
import asyncio
import functools
import http.server
import json
import shutil
import statistics
import sys
import tempfile
import threading
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_static_demo import build  # noqa: E402

RUN = """async ([texts]) => {
  const { createBrowserBackend } = await import("./browser.js");
  const templates = await (await fetch("templates.json")).json();
  const started = performance.now();
  const backend = await createBrowserBackend(templates, new URL("model.gguf", location.href).href, () => {});
  const load_ms = performance.now() - started;
  const times = {};
  for (const [mode, cases] of Object.entries(texts)) {
    try { await backend.suggest(cases[0], mode); } catch (error) {}  // warm-up, excluded
    times[mode] = [];
    for (const text of cases) {
      const begun = performance.now();
      try { await backend.suggest(text, mode); } catch (error) {}  // a refusal still took the time
      times[mode].push(performance.now() - begun);
    }
  }
  return { load_ms, times, threads: self.crossOriginIsolated, cores: navigator.hardwareConcurrency };
}"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


async def measure(url, texts, executable):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(**({"executable_path": executable} if executable else {}))
        page = await browser.new_page()
        await page.goto(url)
        await page.wait_for_function("() => self.crossOriginIsolated", timeout=15000)  # after one reload
        result = await page.evaluate(RUN, [texts])
        await browser.close()
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--cases", type=int, default=20)
    parser.add_argument("--executable")
    args = parser.parse_args()
    cases = {"continue": json.loads((ROOT / "benchmarks/eval/continue_cases.json").read_text(encoding="utf-8")),
             "rewrite": json.loads((ROOT / "benchmarks/eval/cases.json").read_text(encoding="utf-8"))}
    texts = {mode: [case["text"] for case in rows[:args.cases]] for mode, rows in cases.items()}
    with tempfile.TemporaryDirectory() as directory:
        site = build(Path(directory) / "demo")
        shutil.copyfile(args.model, site / "model.gguf")
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(site)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            result = asyncio.run(measure("http://127.0.0.1:%d/" % server.server_port, texts, args.executable))
        finally:
            server.shutdown()
    report = {"model": args.model.name, "bytes": args.model.stat().st_size, "load_ms": round(result["load_ms"]),
              "threads": result["threads"], "cores": result["cores"]}
    for mode, times in result["times"].items():
        times = sorted(times)
        report[mode] = {"median_ms": round(statistics.median(times)),
                        "p95_ms": round(times[min(len(times) - 1, int(len(times) * 0.95))]), "n": len(times)}
    print(json.dumps(report))


if __name__ == "__main__":
    main()
