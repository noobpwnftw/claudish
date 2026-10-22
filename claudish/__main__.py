import argparse
import json
import os
import statistics
import time
from urllib.error import HTTPError
from .client import suggest
from .model import Rewriter, load_prompt
from .server import make_server


def main():
    parser = argparse.ArgumentParser(description="cd_AI — Claudish input method")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--backend", choices=["llama", "openai", "claude", "rules"], default="llama",
                       help="llama/openai: any OpenAI-compatible server at --model-url; "
                            "claude: the Anthropic API (credentials from ANTHROPIC_API_KEY or `ant auth login`)")
    serve.add_argument("--claude-model", default="claude-opus-5-5")
    serve.add_argument("--model-url", default="http://127.0.0.1:18766")
    serve.add_argument("--model", help="Model name to request from an OpenAI-compatible server")
    serve.add_argument("--api-key-env", metavar="NAME",
                       help="Environment variable holding a bearer key for --model-url")
    serve.add_argument("--timeout", type=float, default=3, help="Seconds to wait for --model-url")
    serve.add_argument("--prompt", metavar="FILE",
                       help='Rewrite template JSON: {"system": "...", "examples": [["in", "out"], ...]}')
    serve.add_argument("--port", type=int, default=18765)
    serve.add_argument("--max-tokens", type=int, default=64)
    rewrite = commands.add_parser("rewrite")
    rewrite.add_argument("text")
    rewrite.add_argument("--url", default="http://127.0.0.1:18765")
    bench = commands.add_parser("bench")
    bench.add_argument("--runs", type=int, default=10)
    bench.add_argument("--url", default="http://127.0.0.1:18765")
    args = parser.parse_args()
    if args.command == "serve":
        api_key = None
        if args.api_key_env:
            api_key = os.environ.get(args.api_key_env)
            if not api_key:
                parser.error("environment variable %s is not set" % args.api_key_env)
        try:
            prompt = load_prompt(args.prompt) if args.prompt else None
        except (OSError, ValueError) as exc:
            parser.error("--prompt: %s" % exc)
        try:
            rewriter = Rewriter(args.backend, args.model_url, args.max_tokens, args.claude_model,
                                args.model, api_key, args.timeout, prompt)
        except ImportError:
            parser.error('the claude backend needs the Anthropic SDK: pip install "claudish-ime[claude]"')
        server = make_server(rewriter, args.port)
        if rewriter.hosted:
            target = "the Anthropic API (%s)" % args.claude_model if rewriter.claude else args.model_url
            print("Typed text will be sent to %s." % target, flush=True)
        print("cd_AI listening on http://127.0.0.1:%s (%s)" % (server.server_port, args.backend), flush=True)
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


if __name__ == "__main__":
    main()
