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
    setup = commands.add_parser("setup", help="Everything from a fresh checkout to typing: model, config, MCP, "
                                "input method, start at login, then doctor")
    setup.add_argument("--profile", help='Which profile to set up (default: the config\'s, else "local")')
    setup.add_argument("--yes", action="store_true", help="Do every step without asking")
    setup.add_argument("--dry-run", action="store_true", help="Show the plan; change nothing")
    setup.add_argument("--variant", choices=["cpu", "vulkan"], default="cpu", help="llama.cpp build to download")
    setup.add_argument("--skip", action="append", default=[], metavar="STEP",
                       choices=["config", "mcp", "llama.cpp", "model", "input", "starts"],
                       help="Skip a step (repeatable): config, mcp, llama.cpp, model, input, starts")
    doctor = commands.add_parser("doctor", help="Check the setup end to end and say how to fix problems")
    doctor.add_argument("--json", action="store_true", help="Machine-readable output for bug reports")
    service = commands.add_parser("service", help="Start Claudish at login (systemd, logon task, launchd)")
    service.add_argument("action", choices=["install", "uninstall", "status"])
    service.add_argument("--serve", action="store_true",
                         help="Run `claudish serve ARGS` instead of the local stack (scripts/start.py ARGS)")
    service.add_argument("--dry-run", action="store_true", help="Show what would be written and run")
    mcp = commands.add_parser("mcp", help="Import MCP servers from Claude and list their tools")
    mcp.add_argument("action", choices=["import", "list"])
    mcp.add_argument("--dry-run", action="store_true")
    mcp.add_argument("--replace", action="store_true", help="Overwrite servers already in the config")
    context_cmd = commands.add_parser("context", help="Show what context an app would get")
    context_cmd.add_argument("action", choices=["test"])
    context_cmd.add_argument("--app", required=True, help='App name as the input method reports it, e.g. "firefox"')
    context_cmd.add_argument("--profile")
    context_cmd.add_argument("--show", action="store_true", help="Also print the start of each provider's text")
    commands.add_parser("textbox-mcp", help="(started by Claudish) the text box as an MCP server for an agent")
    init = commands.add_parser("init", help="Write a starter config with example profiles")
    init.add_argument("--config", metavar="FILE", help="Where to write it (default: %s)" % config.default_path())
    hook = commands.add_parser("shell-hook", help='Print shell integration: eval "$(claudish shell-hook bash)"')
    hook.add_argument("shell", choices=sorted(fix.HOOKS))
    # `service ... -- ARGS`: split before argparse, so no flag of ours can be swallowed into ARGS
    # (argparse.REMAINDER once took --dry-run and really installed a unit).
    argv, passthrough = sys.argv[1:], []
    if argv[:1] == ["service"] and "--" in argv:
        argv, passthrough = argv[:argv.index("--")], argv[argv.index("--") + 1:]
    args = parser.parse_args(argv)
    if args.command == "textbox-mcp":
        from .textbox_mcp import main as textbox_mcp
        return textbox_mcp()
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
    if args.command == "setup":
        from . import setup as wizard
        sys.exit(wizard.run(args.profile, args.yes, args.dry_run, args.variant, args.skip))
    if args.command == "doctor":
        from . import doctor as checkup
        sys.exit(checkup.main(args.json))
    if args.command == "service":
        from . import service as manager
        sys.exit(manager.run(args.action, args.serve, passthrough, args.dry_run))
    if args.command == "mcp":
        from . import mcp_setup
        sys.exit(mcp_setup.import_servers(dry_run=args.dry_run, replace=args.replace) if args.action == "import"
                 else mcp_setup.list_servers())
    if args.command == "context":
        from . import mcp_setup
        try:
            sys.exit(mcp_setup.context_test(args.app, args.profile, args.show))
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
    if args.command == "init":
        try:
            path = config.write_starter(args.config)
        except (OSError, FileExistsError) as exc:
            sys.exit(str(exc))
        print("Wrote %s with profiles: %s (default: %s)." % (
            path, ", ".join(config.STARTER["profiles"]), config.STARTER["profile"]))
        print("Try one: claudish serve --profile ollama   (or claude, agent)")
        return
    if args.command == "serve":
        # Only real flags override the profile; other profile keys (and args.command, the
        # subcommand's name) must not.
        flags = ("backend", "claude_model", "model_url", "model", "api_key_env", "timeout", "prompt", "max_tokens")
        overrides = {key: getattr(args, key) for key in flags}
        try:
            profile, settings, prompt, context = config.resolve(args.config, args.profile, overrides)
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        try:
            rewriter = Rewriter.from_settings(settings, prompt, context, profile)
        except ValueError as exc:
            parser.error(str(exc))
        except ImportError:
            parser.error('the claude backend needs the Anthropic SDK: pip install "claudish-ime[claude]"')
        from .client import write_token
        server = make_server(rewriter, args.port, write_token())
        if rewriter.hosted:
            target = ("the Anthropic API (%s)" % settings["claude_model"] if rewriter.claude
                      else " ".join(settings["command"]) if settings["backend"] == "command"
                      else settings["model_url"])
            print("Typed text will be sent to %s." % target, flush=True)
        print("cd_AI listening on http://127.0.0.1:%s (%s%s)" % (
            server.server_port, settings["backend"], ", profile " + profile if profile else ""), flush=True)
        if rewriter.read_terminal:
            import threading
            from .screen import warm
            threading.Thread(target=warm, daemon=True).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
            rewriter.conversations.close()
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
