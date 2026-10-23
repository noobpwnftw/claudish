"""Score an instruction typed at a terminal prompt ("fix") against benchmarks/eval/fix_cases.json.

Each case becomes a terminal screen: the failed command at a prompt, and for an unknown program,
the shell's "command not found". The instruction "fix" is sent in instruct mode with that screen,
as the service does when it reads a terminal (G35), through an OpenAI-compatible model server.
A case with "fix": null is a legitimate command that failed for environmental reasons: the right
answer is the command unchanged, and any other command counts as harmful.
"""
import argparse
import json
import shlex
import statistics
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from claudish.model import Rewriter

PROMPT = "ana@laptop:~/project$ "


def screen(case, installed):
    program = case["command"].split()[0]
    lines = [PROMPT + case["command"]]
    if program not in installed:
        lines.append("bash: %s: command not found" % program)
    return "\n".join(lines + [PROMPT.rstrip()])


def same_command(a, b):
    try:
        return shlex.split(a) == shlex.split(b)
    except ValueError:
        return a.strip() == b.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model-url", default="http://127.0.0.1:18766")
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = json.loads((root / "benchmarks/eval/fix_cases.json").read_text(encoding="utf-8"))
    installed = set(data["installed"])
    rewriter = Rewriter("llama", args.model_url, 128, timeout=20)
    rows = []
    for case in data["cases"]:
        start = time.perf_counter()
        try:
            answer, error = rewriter.rewrite("fix", mode="instruct", app="gnome-terminal-server",
                                             screen=screen(case, installed))["text"].strip(), None
        except Exception as exc:
            answer, error = None, str(exc)
        wanted = case["fix"]
        if answer is None:
            verdict = "error"
        elif wanted is None:
            verdict = "kept" if same_command(answer, case["command"]) else "harmful"
        else:
            verdict = "fixed" if any(same_command(answer, w) for w in wanted) else "wrong"
        rows.append({"id": case["id"], "command": case["command"], "answer": answer, "error": error,
                     "verdict": verdict, "ms": round((time.perf_counter() - start) * 1000, 1)})
    counts = {verdict: sum(row["verdict"] == verdict for row in rows)
              for verdict in ["fixed", "wrong", "kept", "harmful", "error"]}
    report = {"label": args.label, "cases": len(rows), **counts,
              "median_ms": statistics.median(row["ms"] for row in rows), "results": rows}
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "results"}))
    for row in rows:
        if row["verdict"] not in ("fixed", "kept"):
            print("%-8s %-15s %-40s -> %s" % (row["verdict"], row["id"], row["command"], row["answer"] or row["error"]))


if __name__ == "__main__":
    main()
