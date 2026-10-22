"""Score rewrites from a running Claudish service against benchmarks/eval/cases.json.

The checks are mechanical fidelity guards, not a judgment of prose quality:
kept names/numbers, no invented numbers, preserved negation, no chat preamble or quoting, no
truncation, and a sane length. Style is reported separately.
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

NEGATION = re.compile(r"\b(not|no|never|none|nobody|nothing|neither|nor|cannot|without|"
                      r"no one|unable|refrain|avoid|lack\w*)\b|n't\b|n’t\b", re.IGNORECASE)
PREAMBLE = re.compile(r"^(sure|certainly|of course|here(?:'s| is)|okay|rewritten|rewrite|"
                      r"polished|revised)\b", re.IGNORECASE)
QUOTES = "\"'“”‘’"
WORDS = ("zero _ two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
         "sixteen seventeen eighteen nineteen twenty").split()
NUMBER_WORDS = dict({word: i for i, word in enumerate(WORDS) if word != "_"},  # "one" is usually a pronoun
                    **{word: 10 * i for i, word in enumerate("thirty forty fifty sixty seventy eighty ninety".split(), 3)})
NUMBER = re.compile(r"\d+(?:\.\d+)?|\b(?:%s)\b" % "|".join(NUMBER_WORDS), re.IGNORECASE)


def numbers(text):
    return {float(NUMBER_WORDS.get(token.lower(), token)) for token in NUMBER.findall(text)}


def check(case, output):
    """Return the names of failed fidelity checks for one rewrite."""
    source = case["text"]
    failures = ["missing:" + item for item in case.get("keep", []) if item not in output]
    if case.get("any_of") and not any(word in output for word in case["any_of"]):
        failures.append("language")
    if numbers(output) - numbers(source):
        failures.append("new-number")
    if NEGATION.search(source) and not NEGATION.search(output):
        failures.append("negation")
    if PREAMBLE.match(output) and not PREAMBLE.match(source):
        failures.append("preamble")
    if len(output) > 1 and output[0] in QUOTES and output[-1] in QUOTES and source[0] not in QUOTES:
        failures.append("quoted")
    if not 0.6 <= len(output) / len(source) <= max(4.0, 40 / len(source)):
        failures.append("length")
    return failures


def score(cases, outputs):
    rows = []
    for case, (output, error, wall_ms) in zip(cases, outputs):
        row = {"id": case["id"], "category": case["category"], "input": case["text"], "wall_ms": wall_ms}
        if error:
            row.update(error=error, failures=["error"])
        else:
            changed = output.strip().lower() != case["text"].strip().lower()
            row.update(output=output, failures=check(case, output), changed=changed,
                       em_dash="—" in output and "—" not in case["text"])
        rows.append(row)
    ok = [row for row in rows if not row["failures"]]
    latencies = sorted(row["wall_ms"] for row in rows)
    return {
        "cases": len(rows),
        "faithful": len(ok),
        "errors": sum("error" in row for row in rows),
        "faithful_and_changed": sum(row["changed"] for row in ok),
        "added_em_dash": sum(row.get("em_dash", False) for row in ok),
        "median_ms": statistics.median(latencies),
        "p95_ms": latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))],
        "failures_by_check": {name: sum(any(f.split(":")[0] == name for f in row["failures"]) for row in rows)
                              for name in ["error", "missing", "new-number", "language", "negation", "preamble",
                                           "quoted", "length"]},
        "results": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:18765")
    parser.add_argument("--cases", type=Path, default=root / "benchmarks/eval/cases.json")
    parser.add_argument("--label", required=True, help="Model and settings, recorded in the output")
    parser.add_argument("--output", type=Path, help="Write full JSON results here")
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    try:
        suggest("Warm up the model.", args.url)  # Excluded from results.
    except HTTPError:
        pass
    outputs = []
    for case in cases:
        start = time.perf_counter()
        try:
            output, error = suggest(case["text"], args.url)["text"], None
        except HTTPError as exc:
            output, error = None, json.load(exc).get("error", str(exc))
        outputs.append((output, error, round((time.perf_counter() - start) * 1000, 2)))
    report = {"label": args.label, **score(cases, outputs)}
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {key: value for key, value in report.items() if key != "results"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for row in report["results"]:
        if row["failures"]:
            print("FAIL %-12s %-28s %s" % (row["id"], ",".join(row["failures"]),
                                          row.get("output", row.get("error"))))


if __name__ == "__main__":
    main()
