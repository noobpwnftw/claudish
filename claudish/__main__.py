import argparse
import json
import os
import shlex
import shutil
import statistics
import sys
import time
from urllib.error import HTTPError
from .client import suggest
from . import config, fix
from .model import Rewriter
from .server import make_server


def main():
    parser = argparse.ArgumentParser(description="cd_AI — Claudish input method")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--config", metavar="FILE", help="Profiles file (default: %s, if present)"
                       % config.default_path())
    serve.add_argument("--profile", help="Profile to use from the config file")
    # The flags below override the profile; their defaults live in config.DEFAULTS.
    serve.add_argument("--backend", choices=config.BACKENDS,
                       help="llama/openai: any OpenAI-compatible server at --model-url; "
                            "claude: the Anthropic API (credentials from ANTHROPIC_API_KEY or `ant auth login`)")
    serve.add_argument("--claude-model")
    serve.add_argument("--model-url")
    serve.add_argument("--model", help="Model name to request from an OpenAI-compatible server")
    serve.add_argument("--api-key-env", metavar="NAME",
                       help="Environment variable holding a bearer key for --model-url")
    serve.add_argument("--timeout", type=float, help="Seconds to wait for --model-url")
    serve.add_argument("--prompt", metavar="FILE",
                       help='Rewrite template JSON: {"system": "...", "examples": [["in", "out"], ...]}')
    serve.add_argument("--port", type=int, default=18765)
    serve.add_argument("--max-tokens", type=int)
    rewrite = commands.add_parser("rewrite")
    rewrite.add_argument("text")
    rewrite.add_argument("--url", default="http://127.0.0.1:18765")
    bench = commands.add_parser("bench")
    bench.add_argument("--runs", type=int, default=10)
    bench.add_argument("--url", default="http://127.0.0.1:18765")
    fixer = commands.add_parser("fix", help="Suggest a fix for the last failed shell command")
    fixer.add_argument("--config", metavar="FILE")
    fixer.add_argument("--profile")
    fixer.add_argument("--status", type=int, default=1, help="Exit status, with an explicit command")
    fixer.add_argument("words", nargs="*", metavar="-- COMMAND", help="Fix this command instead of the last failure")
    hook = commands.add_parser("shell-hook", help='Print shell integration: eval "$(claudish shell-hook bash)"')
    hook.add_argument("shell", choices=sorted(fix.HOOKS))
    args = parser.parse_args()
    if args.command == "shell-hook":
        if shutil.which("claudish"):
            launcher = "claudish"
        else:  # Running from a checkout: call this Python with the project on its path.
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            launcher = "PYTHONPATH=%s %s -m claudish" % (shlex.quote(root), shlex.quote(sys.executable))
        print(fix.shell_hook(args.shell, launcher))
        return
    if args.command == "fix":
        return fix_command(parser, args)
    if args.command == "serve":
        overrides = {key: getattr(args, key, None) for key in config.DEFAULTS}  # file-only keys have no flag
        try:
            profile, settings, prompt, context = config.resolve(args.config, args.profile, overrides)
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        api_key = None
        if settings["api_key_env"]:
            api_key = os.environ.get(settings["api_key_env"])
            if not api_key:
                parser.error("environment variable %s is not set" % settings["api_key_env"])
        try:
            rewriter = Rewriter(settings["backend"], settings["model_url"], settings["max_tokens"],
                                settings["claude_model"], settings["model"], api_key, settings["timeout"], prompt,
                                context)
        except ImportError:
            parser.error('the claude backend needs the Anthropic SDK: pip install "claudish-ime[claude]"')
        rewriter.profile = profile
        server = make_server(rewriter, args.port)
        if rewriter.hosted:
            target = ("the Anthropic API (%s)" % settings["claude_model"] if rewriter.claude
                      else settings["model_url"])
            print("Typed text will be sent to %s." % target, flush=True)
        print("cd_AI listening on http://127.0.0.1:%s (%s%s)" % (
            server.server_port, settings["backend"], ", profile " + profile if profile else ""), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    elif args.command == "rewrite":
        print(json.dumps(suggest(args.text, args.url), ensure_ascii=False, indent=2))
    else:
        if args.runs < 1:
            parser.error("--runs must be positive")
        samples = ["We should use a smaller model.", "This is very important.",
                   "Let's explore the options.", "The test failed because the file was missing."]
        try:
            suggest(samples[0], args.url)  # Warmup excluded from measured samples.
        except HTTPError:
            pass
        results = []
        for index in range(args.runs):
            source = samples[index % len(samples)]
            start = time.perf_counter()
            try:
                response = suggest(source, args.url)
            except HTTPError as exc:
                response = {"error": json.load(exc).get("error", str(exc))}
            results.append({"input": source,
                            "wall_ms": round((time.perf_counter() - start) * 1000, 2),
                            **response})
        latencies = sorted(r["wall_ms"] for r in results)
        print(json.dumps({"runs": args.runs, "successes": sum("text" in r for r in results),
                          "median_ms": statistics.median(latencies),
                          "p95_ms": latencies[min(len(latencies)-1, int(len(latencies)*0.95))],
                          "results": results}, ensure_ascii=False, indent=2))


def fix_command(parser, args):
    if args.words:
        status, directory, command = args.status, os.getcwd(), " ".join(args.words)
    else:
        failure = fix.last_failure()
        if failure is None:
            sys.exit('no failed command recorded; add eval "$(claudish shell-hook bash)" to your shell rc')
        status, directory, command = failure
    try:
        _, settings, _, _ = config.resolve(args.config, args.profile)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    api_key = os.environ.get(settings["api_key_env"]) if settings["api_key_env"] else None
    try:
        # The profile picks the backend; the fix template replaces its rewrite template and context.
        rewriter = Rewriter(settings["backend"], settings["model_url"], 128, settings["claude_model"],
                            settings["model"], api_key, settings["timeout"], (fix.SYSTEM, fix.examples()))
        suggestion = fix.suggest(rewriter, command, status)
    except ImportError:
        sys.exit('the claude backend needs the Anthropic SDK: pip install "claudish-ime[claude]"')
    except OSError as exc:
        where = "the Anthropic API" if settings["backend"] == "claude" else settings["model_url"]
        sys.exit("cannot reach the model at %s (%s); start one with `python scripts/start.py` "
                 "or choose a profile" % (where, exc))
    except Exception as exc:
        sys.exit("fix failed: %s" % exc)
    if suggestion is None:
        sys.exit("no fix found for: " + command)
    print(suggestion)


if __name__ == "__main__":
    main()
