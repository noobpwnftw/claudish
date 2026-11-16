"""Compare models and templates from judged evaluation runs (G53).

python benchmarks/compare.py ROOT

ROOT holds one folder per template set (shipped, or a templates file's name), each with
evaluate.py reports (rewrite-MODEL.json), evaluate_continue.py reports (continue-MODEL.json),
and judge.py verdicts for them (rewrite-MODEL.judged-JUDGE.json). A rewrite passes when it
changed the text, passed the mechanical checks, and every judge says "same" (or "slop", on the
slop rubric); a suggestion
passes when it passed its checks and every judge says "good". Cases split in two by a hash
of their id: each model's template set is chosen on the dev half, and its score reported on
the test half, with a 95% Wilson interval, so no template is scored on the cases it was
chosen by.
"""
import argparse
import hashlib
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

PASS = {"rewrite": {"same", "slop"}, "continue": {"good"}}  # slop: a rewrite judged on the slop rubric


def half(case_id):
    return "dev" if hashlib.sha1(case_id.encode()).digest()[0] % 2 == 0 else "test"


def wilson(passed, total, z=1.96):
    if not total:
        return 0.0, 0.0
    p = passed / total
    centre = (p + z * z / (2 * total)) / (1 + z * z / total)
    spread = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return max(0.0, centre - spread), min(1.0, centre + spread)


def load(root):
    """(variant, task, model) -> {case id: passed}, and -> latencies."""
    passed, latency = {}, {}
    for report in sorted(root.glob("*/*-*.json")):
        if ".judged-" in report.name:
            continue
        task, model = report.stem.split("-", 1)
        if task not in PASS:
            continue
        rows = json.loads(report.read_text(encoding="utf-8"))["results"]
        verdicts = defaultdict(list)
        judged = sorted(report.parent.glob(report.stem + ".judged-*.json"))
        for path in judged:
            for row in json.loads(path.read_text(encoding="utf-8"))["rows"]:
                verdicts[row["id"]].append(row["verdict"])
        ok = {}
        for row in rows:
            good = not row["failures"] and row.get("output")
            if task == "rewrite":
                good = good and row.get("changed")
            ok[row["id"]] = bool(good) and len(verdicts[row["id"]]) == len(judged) > 0 and all(
                verdict in PASS[task] for verdict in verdicts[row["id"]])
        key = (report.parent.name, task, model)
        passed[key], latency[key] = ok, sorted(row["wall_ms"] for row in rows)
    return passed, latency


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    passed, latency = load(args.root)
    lines = []
    for task in PASS:
        models = sorted({model for _, t, model in passed if t == task})
        lines.append("\n%s (test half; template chosen on the dev half)\n" % task)
        lines.append("| Model | Template | Test pass | 95% interval | Dev pass | Median ms | p95 ms |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: |")
        rows = []
        for model in models:
            variants = [v for v, t, m in passed if t == task and m == model]
            def rate(variant, part):
                cases = {c: ok for c, ok in passed[(variant, task, model)].items() if half(c) == part}
                return sum(cases.values()), len(cases)
            best = max(variants, key=lambda v: (rate(v, "dev")[0], v == "shipped"))
            won, total = rate(best, "test")
            low, high = wilson(won, total)
            dev = rate(best, "dev")
            times = latency[(best, task, model)]
            rows.append((won / total if total else 0, "| %s | %s | %d/%d (%.0f%%) | %.0f–%.0f%% | %d/%d | %.0f | %.0f |" % (
                model, best, won, total, 100 * won / max(total, 1), 100 * low, 100 * high, dev[0], dev[1],
                statistics.median(times), times[min(len(times) - 1, int(len(times) * 0.95))])))
        lines += [row for _, row in sorted(rows, reverse=True)]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
