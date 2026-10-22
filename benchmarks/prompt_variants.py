"""Score system-prompt/example variants against a running llama-server, bypassing the service.

python scripts/run_model.py --preset small   # in another terminal
python benchmarks/prompt_variants.py benchmarks/eval/prompt-variants.json
"""
import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, ROOT)
from claudish import model

spec = importlib.util.spec_from_file_location("evaluate", ROOT + "/benchmarks/evaluate.py")
evaluate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluate)
cases = json.load(open(ROOT + "/benchmarks/eval/cases.json", encoding="utf-8"))

variants = json.load(open(sys.argv[1], encoding="utf-8"))
for name, variant in variants.items():
    model.SYSTEM = variant["system"]
    model.EXAMPLES = [m for pair in variant["examples"] for m in
                      ({"role": "user", "content": pair[0]}, {"role": "assistant", "content": pair[1]})]
    frame = (lambda s: "Text to rewrite: \"" + s + "\"") if variant.get("frame") else (lambda s: s)
    model.EXAMPLES = [dict(m, content=frame(m["content"])) if m["role"] == "user" else m for m in model.EXAMPLES]
    rewriter = model.Rewriter()
    original = rewriter.rewrite
    rewriter.rewrite = lambda text: original(frame(text))
    rewriter.rewrite("Warm up the model.")
    outputs = []
    for case in cases:
        start = time.perf_counter()
        try:
            outputs.append((rewriter.rewrite(case["text"])["text"], None, round((time.perf_counter() - start) * 1000, 2)))
        except Exception as exc:
            outputs.append((None, str(exc), round((time.perf_counter() - start) * 1000, 2)))
    report = evaluate.score(cases, outputs)
    print("== %s: pass %d/%d changed %d dash %d median %.0fms p95 %.0fms %s" % (
        name, report["faithful"], report["cases"], report["faithful_and_changed"], report["added_em_dash"],
        report["median_ms"], report["p95_ms"], {k: v for k, v in report["failures_by_check"].items() if v}))
    for row in report["results"]:
        flag = "FAIL " + ",".join(row["failures"]) if row["failures"] else "ok"
        print("  %-10s %-22s %s" % (row["id"], flag[:22], row.get("output") or row.get("error")))
