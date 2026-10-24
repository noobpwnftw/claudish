import argparse
import json
import statistics
import sys
import time
from urllib.error import HTTPError
from .client import suggest
from . import config
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
    serve.add_argument("--templates", metavar="FILE",
                       help="Templates JSON in the shape of claudish/templates.json, naming what it changes")
    serve.add_argument("--port", type=int, default=18765)
    serve.add_argument("--max-tokens", type=int)
    rewrite = commands.add_parser("rewrite")
    rewrite.add_argument("text")
    rewrite.add_argument("--url", default="http://127.0.0.1:18765")
    bench = commands.add_parser("bench")
    bench.add_argument("--runs", type=int, default=10)
    bench.add_argument("--url", default="http://127.0.0.1:18765")
    setup = commands.add_parser("setup", help="Everything from a fresh checkout to typing: model, config, MCP, "
                                "input method, start at login, then doctor")
    setup.add_argument("--profile", help='Which profile to set up (default: the config\'s, else "claude"; "local" downloads a local model)')
    setup.add_argument("--yes", action="store_true", help="Do every step without asking")
    setup.add_argument("--tone", help='The voice: "plain", "fix" (correct, keep your words), or your own words '
                       "(default: Claudish's, polished with em dashes)")
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
    recent = commands.add_parser("recent", help="What the last requests sent, to which model, and what came back "
                                 "(in the service's memory only)")
    recent.add_argument("--full", action="store_true", help="Print the whole system prompt and turn")
    recent.add_argument("--clear", action="store_true", help="Forget them now")
    recent.add_argument("--url", default="http://127.0.0.1:18765")
    init = commands.add_parser("init", help="Write a starter config with example profiles")
    init.add_argument("--config", metavar="FILE", help="Where to write it (default: %s)" % config.default_path())
    # `service ... -- ARGS`: split before argparse, so no flag of ours can be swallowed into ARGS
    # (argparse.REMAINDER once took --dry-run and really installed a unit).
    argv, passthrough = sys.argv[1:], []
    if argv[:1] == ["service"] and "--" in argv:
        argv, passthrough = argv[:argv.index("--")], argv[argv.index("--") + 1:]
    args = parser.parse_args(argv)
    if args.command == "recent":
        if args.clear:
            from .client import call
            call(args.url, "/recent/clear", {})
            return print("Cleared.")
        return show_recent(args.url, args.full)
    if args.command == "textbox-mcp":
        from .textbox_mcp import main as textbox_mcp
        return textbox_mcp()
    if args.command == "setup":
        from . import setup as wizard
        sys.exit(wizard.run(args.profile, args.yes, args.dry_run, args.variant, args.skip, args.tone))
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
        flags = ("backend", "claude_model", "model_url", "model", "api_key_env", "timeout", "templates", "max_tokens")
        overrides = {key: getattr(args, key) for key in flags}
        try:
            profile, settings, templates, context = config.resolve(args.config, args.profile, overrides)
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        try:
            rewriter = Rewriter.from_settings(settings, templates, context, profile)
        except ValueError as exc:
            parser.error(str(exc))
        except ImportError:
            parser.error('the claude backend needs the Anthropic SDK: pip install "claudish-ime[claude]"')
        def load(name):
            """Another profile of this config, for an app a binding routes to it."""
            _, routed, routed_templates, routed_context = config.resolve(args.config, name)
            return Rewriter.from_settings(routed, routed_templates, routed_context, name)
        rewriter.loader = load
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


def show_recent(url, full=False):
    """The service's last requests: who answered, what was observed, what was sent, how long it took."""
    import time
    from .client import call
    try:
        items = call(url, "/recent")["recent"]
    except Exception as exc:
        sys.exit("cannot read the service's recent requests: %s" % exc)
    if not items:
        print("No requests yet.")
    for item in items:
        where = " · ".join(str(part) for part in (item.get("app"), item.get("kind")) if part) or "no app"
        print("%s  %s in %s  →  %s%s (%s%s)" % (
            time.strftime("%H:%M:%S", time.localtime(item["time"])), item["mode"], where,
            item.get("backend"), " " + item["model"] if item.get("model") else "",
            "hosted" if item.get("hosted") else "local", ", profile " + item["profile"] if item.get("profile") else ""))
        print("  consulted: %s" % (", ".join(item.get("consulted") or []) or "nothing"))
        print("  outcome:   %s%s" % (item.get("outcome", "running"),
                                     ", %s ms" % item["elapsed_ms"] if item.get("elapsed_ms") is not None else ""))
        for name in ("system", "turn"):
            text = item.get(name) or ""
            if not full and len(text) > 300:
                text = text[:300] + " … (%d characters; --full shows all)" % len(text)
            print("  %s:\n    %s" % (name, text.replace("\n", "\n    ")))
        print()


if __name__ == "__main__":
    main()
