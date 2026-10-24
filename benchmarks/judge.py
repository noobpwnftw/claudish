"""Judge rewrites (do they keep their meaning?) and continue's suggestions (do they fit?) with a
larger local model (G12, G53).

python benchmarks/judge.py --calibrate                       # agreement with hand labels
python benchmarks/judge.py --results benchmarks/eval/spark-small.json   # judge an evaluate.py report
python benchmarks/judge.py --task continue --calibrate       # the same for continue
python benchmarks/judge.py --task slop --results R.json      # a rewrite in the slop tone

Any OpenAI-compatible server works; llama.cpp constrains the reply to the JSON schema.
"""
import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler

root = Path(__file__).resolve().parents[1]
TASKS = {
    "rewrite": {
        "labels": ["same", "adds", "reply", "changed", "language"],
        "file": "judge_labels.json",
        "pair": "Original: %s\nRewrite: %s",
        "system": """You check an automatic rewrite of a short message. The rewrite may change style and
wording freely, and may become more formal or verbose. Decide whether it keeps the meaning.

Answer with one verdict:
- same: the same message, with the same speaker, target, and facts; style changes only.
- adds: it adds a fact, claim, request, opinion, or sentiment that is not in the original.
- reply: it answers or reacts to the original instead of restating it (for example "Thanks!" becomes "You're welcome!").
- changed: it loses or alters meaning, such as a dropped detail, a changed action, number, or target, or a different addressee.
- language: it is in a different language from the original.

Check the language first: if the rewrite is not in the original's language, answer "language"
even when the meaning matches. Judge strictly: if anything is added or lost, it is not "same".""",
    },
    "slop": {
        "labels": ["slop", "tame", "changed", "adds", "reply"],
        "file": "slop_labels.json",
        "pair": "Original: %s\nSlop rewrite: %s",
        "system": """You check an automatic rewrite that is meant to be deliberately over-the-top corporate
"slop", as a joke: the same message, inflated with effusive buzzwords, em dashes and grandiosity.
Inflation is the point: flourish, enthusiasm and generic corporate phrases ("align on our shared
vision", "unlock meaningful synergies") are expected, and they are not added facts. Decide whether
it keeps the message, and whether it is really slop.

Answer with one verdict:
- slop: the same message (a yes stays a yes, a no stays a no, a question stays a question; the same addressee; every name, number, date, code term and URL kept), unmistakably inflated into over-the-top corporate prose.
- tame: the same message, but only lightly polished: it does not read as over-the-top slop.
- changed: the message is lost or altered: a yes or a no flipped or softened into its opposite, a name, number, date, action or addressee dropped or changed, or a question turned into a statement.
- adds: it commits the writer to something concrete they did not say: a new fact, date, number, promise or request (generic enthusiasm and buzzwords do not count).
- reply: it answers or reacts to the original instead of restating it as its writer (for example "Thanks!" becomes "You're welcome!").

Check the meaning first: a changed message is "changed" however funny it is.""",
    },
    "continue": {
        "labels": ["good", "echo", "off", "reply", "meta"],
        "file": "continue_labels.json",
        "pair": "Text so far: %s\nSuggested next words: %s",
        "system": """You check an autocomplete suggestion: the words an input method offers to put right
after what the writer has typed so far. The writer takes it with one key or ignores it. A good
suggestion reads as the writer's own next words: it follows on from the text, joins it cleanly
(spacing, capitalisation, punctuation); it may be polished, verbose or deliberately over the top
whatever the text's own tone, and it may say something new, as any continuation does.

Answer with one verdict:
- good: the text followed by the suggestion reads as one natural piece of writing by the writer.
- echo: it repeats words the writer already wrote instead of going on.
- off: it does not follow on: a non sequitur, a contradiction, a broken join, or ungrammatical together.
- reply: it answers or addresses the writer (for example "Thanks for" goes on "Sure, happy to help!") instead of writing as them.
- meta: it talks about the text or the task ("Here are the next words", "The writer means") instead of continuing it.

Read the text and the suggestion together, as one line, before you decide.""",
    },
}


def schema(task):
    return {"type": "object", "properties": {"verdict": {"type": "string", "enum": TASKS[task]["labels"]},
                                             "reason": {"type": "string"}},
            "required": ["verdict", "reason"]}


def judge(url, source, output, timeout=60, task="rewrite"):
    payload = {"messages": [{"role": "system", "content": TASKS[task]["system"]},
                            {"role": "user", "content": TASKS[task]["pair"] % (source, output)}],
               "temperature": 0, "max_tokens": 600,
               "response_format": {"type": "json_schema", "json_schema": {"name": "verdict", "schema": schema(task)}}}
    request = Request(url.rstrip("/") + "/v1/chat/completions", data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json"})
    with build_opener(ProxyHandler({})).open(request, timeout=timeout) as response:
        reply = json.load(response)["choices"][0]["message"]["content"]
    data = json.loads(reply)
    return data["verdict"], data.get("reason", "")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model-url", default="http://127.0.0.1:18766")
    parser.add_argument("--task", choices=TASKS, default="rewrite")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--calibrate", action="store_true", help="Compare with the task's hand labels in benchmarks/eval/")
    group.add_argument("--results", type=Path, help="An evaluate.py JSON report to judge")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.calibrate:
        pairs = json.loads((root / "benchmarks/eval" / TASKS[args.task]["file"]).read_text(encoding="utf-8"))["pairs"]
    else:
        report = json.loads(args.results.read_text(encoding="utf-8"))
        pairs = [{"id": row["id"], "source": row["input"], "output": row["output"]}
                 for row in report["results"] if row.get("output")]
    started, rows = time.perf_counter(), []
    for pair in pairs:
        verdict, reason = judge(args.model_url, pair["source"], pair["output"], task=args.task)
        rows.append(dict(pair, verdict=verdict, reason=reason))
    summary = {"pairs": len(rows), "seconds": round(time.perf_counter() - started, 1),
               "verdicts": dict(Counter(row["verdict"] for row in rows))}
    if args.calibrate:
        exact = sum(row["verdict"] == row["label"] for row in rows)
        best = TASKS[args.task]["labels"][0]  # "same", "slop", "good": the verdict that passes
        binary = sum((row["verdict"] == best) == (row["label"] == best) for row in rows)
        summary.update(exact_agreement=round(exact / len(rows), 3), pass_vs_not_agreement=round(binary / len(rows), 3),
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
