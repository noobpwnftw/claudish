"""Score `claudish fix` against benchmarks/eval/fix_cases.json with an OpenAI-compatible model server.

A case with "fix": null is a legitimate command that failed for environmental
reasons; any change to it counts as harmful. PATH lookups are replaced by the
case file's "installed" list, so results do not depend on this machine.
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from claudish import fix
from claudish.model import Rewriter


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model-url", default="http://127.0.0.1:18766")
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = json.loads((root / "benchmarks/eval/fix_cases.json").read_text(encoding="utf-8"))
    installed = set(data["installed"])
    rewriter = Rewriter("llama", args.model_url, 128, timeout=20, prompt=(fix.SYSTEM, fix.examples()))
    rows = []
    for case in data["cases"]:
        program = case["command"].split()[0]
        start = time.perf_counter()
        try:
            suggestion, error = fix.suggest(rewriter, case["command"], case["status"], installed,
                                            program in installed), None
        except Exception as exc:
            suggestion, error = None, str(exc)
        wanted = case["fix"]
        if wanted is None:
            verdict = "kept" if suggestion is None else "harmful"
        else:
            verdict = ("no fix" if suggestion is None else
                       "fixed" if any(fix.same_command(suggestion, w) for w in wanted) else "wrong")
        rows.append({"id": case["id"], "command": case["command"], "suggestion": suggestion, "error": error,
                     "verdict": verdict, "ms": round((time.perf_counter() - start) * 1000, 1)})
    counts = {verdict: sum(row["verdict"] == verdict for row in rows)
              for verdict in ["fixed", "wrong", "no fix", "kept", "harmful"]}
    report = {"label": args.label, "cases": len(rows), **counts,
              "median_ms": statistics.median(row["ms"] for row in rows), "results": rows}
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "results"}))
    for row in rows:
        if row["verdict"] not in ("fixed", "kept"):
            print("%-8s %-15s %-40s -> %s" % (row["verdict"], row["id"], row["command"], row["suggestion"] or row["error"]))


if __name__ == "__main__":
    main()
