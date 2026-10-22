"""Judge whether rewrites keep their meaning, with a larger local model (G12).

python benchmarks/judge.py --calibrate                       # agreement with hand labels
python benchmarks/judge.py --results eval/spark-small.json   # judge an evaluate.py report

Any OpenAI-compatible server works; llama.cpp constrains the reply to the JSON schema.
Texts are sent only to --model-url (default: loopback).
"""
import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler

root = Path(__file__).resolve().parents[1]
LABELS = ["same", "adds", "reply", "changed", "language"]
SYSTEM = """You check an automatic rewrite of a short message. The rewrite may change style and
wording freely, and may become more formal or verbose. Decide whether it keeps the meaning.

Answer with one verdict:
- same: the same message, with the same speaker, target, and facts; style changes only.
- adds: it adds a fact, claim, request, opinion, or sentiment that is not in the original.
- reply: it answers or reacts to the original instead of restating it (for example "Thanks!" becomes "You're welcome!").
- changed: it loses or alters meaning, such as a dropped detail, a changed action, number, or target, or a different addressee.
- language: it is in a different language from the original.

Check the language first: if the rewrite is not in the original's language, answer "language"
even when the meaning matches. Judge strictly: if anything is added or lost, it is not "same"."""
SCHEMA = {"type": "object", "properties": {"verdict": {"type": "string", "enum": LABELS},
                                             "reason": {"type": "string"}},
          "required": ["verdict", "reason"]}


def judge(url, source, output, timeout=60):
    payload = {"messages": [{"role": "system", "content": SYSTEM},
                            {"role": "user", "content": "Original: %s\nRewrite: %s" % (source, output)}],
               "temperature": 0, "max_tokens": 200,
               "response_format": {"type": "json_schema", "json_schema": {"name": "verdict", "schema": SCHEMA}}}
    request = Request(url.rstrip("/") + "/v1/chat/completions", data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json"})
    with build_opener(ProxyHandler({})).open(request, timeout=timeout) as response:
        reply = json.load(response)["choices"][0]["message"]["content"]
    data = json.loads(reply)
    return data["verdict"], data.get("reason", "")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model-url", default="http://127.0.0.1:18766")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--calibrate", action="store_true", help="Compare with benchmarks/eval/judge_labels.json")
    group.add_argument("--results", type=Path, help="An evaluate.py JSON report to judge")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.calibrate:
        pairs = json.loads((root / "benchmarks/eval/judge_labels.json").read_text(encoding="utf-8"))["pairs"]
    else:
        report = json.loads(args.results.read_text(encoding="utf-8"))
        pairs = [{"id": row["id"], "source": row["input"], "output": row["output"]}
                 for row in report["results"] if row.get("output")]
    started, rows = time.perf_counter(), []
    for pair in pairs:
        verdict, reason = judge(args.model_url, pair["source"], pair["output"])
        rows.append(dict(pair, verdict=verdict, reason=reason))
    summary = {"pairs": len(rows), "seconds": round(time.perf_counter() - started, 1),
               "verdicts": dict(Counter(row["verdict"] for row in rows))}
    if args.calibrate:
        exact = sum(row["verdict"] == row["label"] for row in rows)
        binary = sum((row["verdict"] == "same") == (row["label"] == "same") for row in rows)
        summary.update(exact_agreement=round(exact / len(rows), 3), same_vs_not_agreement=round(binary / len(rows), 3),
                       confusion={"%s->%s" % key: count for key, count in sorted(Counter(
                           (row["label"], row["verdict"]) for row in rows if row["label"] != row["verdict"]).items())})
    print(json.dumps(summary, indent=1))
    for row in rows:
        if args.calibrate and row["verdict"] != row["label"]:
            print("%-8s judge=%-8s %-10s %s -> %s\n         %s" % (row["label"], row["verdict"], row["id"],
                                                                row["source"], row["output"], row["reason"]))
    if args.output:
        args.output.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1) + "\n",
                               encoding="utf-8")
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
