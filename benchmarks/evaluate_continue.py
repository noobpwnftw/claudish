"""Score continue's suggestions from a running Claudish service against
benchmarks/eval/continue_cases.json (G53).

The checks are mechanical guards, not a judgment of the words: something offered, no talk about
the text, a clean join (no quotes), a few words rather than a paragraph, one line, and no pronoun
for a person the text did not give. Whether a suggestion fits is the judge's. English only: cd_AI
is the English input method (other languages have their own).
"""
import argparse
import json
import re
import statistics
import sys
import time
from pathlib import Path
from urllib.error import HTTPError

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from claudish.client import suggest

# Talk about the task, not words of the text (a reply such as "sure, ..." is the judge's).
META = re.compile(r"^(here(?:'s| is| are)\b|the next (?:few )?words|next words|text so far|"
                  r"as an ai\b)", re.IGNORECASE)


def check(case, offered, slop=False):
    """The names of failed checks for the words offered after the caret (slop: to the end of a
    longer sentence)."""
    if not offered.strip():
        return ["empty"]
    failures = []
    if META.match(offered.strip()):
        failures.append("meta")
    if "\n" in offered.strip():
        failures.append("lines")
    if offered.strip()[0] in "\"'“”‘’…" or offered.strip().startswith("..."):
        failures.append("join")  # quoted, or trailing off: not the writer's next words
    if len(offered.split()) > (45 if slop else 20):
        failures.append("long")
    words = set(re.findall(r"[a-z]+", offered.lower()))
    if words & set(case.get("avoid", [])):  # a pronoun the text never gave (they/them by default)
        failures.append("pronoun")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:18765")
    parser.add_argument("--cases", type=Path, default=root / "benchmarks/eval/continue_cases.json")
    parser.add_argument("--label", required=True, help="Model and settings, recorded in the output")
    parser.add_argument("--output", type=Path, help="Write full JSON results here")
    parser.add_argument("--slop", action="store_true", help="The voice is full slop: up to 45 words")
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    try:
        suggest("Warm up the model ", args.url, mode="continue")  # Excluded from results.
    except HTTPError:
        pass
    rows = []
    for case in cases:
        start = time.perf_counter()
        try:
            candidate, error = suggest(case["text"], args.url, mode="continue")["text"], None
        except HTTPError as exc:
            candidate, error = "", json.load(exc).get("error", str(exc))
        wall_ms = round((time.perf_counter() - start) * 1000, 2)
        # The service offers the whole line, the text then its continuation (modes.finish).
        offered = candidate[len(case["text"]):] if candidate.startswith(case["text"]) else candidate
        row = {"id": case["id"], "category": case["category"], "input": case["text"],
               "output": offered, "wall_ms": wall_ms,
               "failures": ["error"] if error else check(case, offered, args.slop)}
        if error:
            row["error"] = error
        rows.append(row)
    latencies = sorted(row["wall_ms"] for row in rows)
    report = {"label": args.label, "slop": args.slop, "cases": len(rows), "passed": sum(not row["failures"] for row in rows),
              "median_ms": statistics.median(latencies),
              "p95_ms": latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))],
              "failures_by_check": {name: sum(name in row["failures"] for row in rows)
                                    for name in ["error", "empty", "meta", "lines", "join", "long", "pronoun"]},
              "results": rows}
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "results"}, ensure_ascii=False, indent=2))
    for row in rows:
        if row["failures"]:
            print("FAIL %-11s %-14s %s" % (row["id"], ",".join(row["failures"]), row.get("error") or row["output"]))


if __name__ == "__main__":
    main()
