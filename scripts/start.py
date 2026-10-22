"""Start the model and IME service together; Ctrl+C stops both."""
import argparse
import json
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import build_opener, ProxyHandler
from run_model import arguments, command

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from claudish import config
from claudish.model import Rewriter
from claudish.server import make_server


def local_rewriter(endpoint, profile=None):
    """The profile's context, bindings, modes, and prompt, with this script's model.

    Without --profile: "local" when the config file has it, else the file's default."""
    if profile is None and config.default_path().is_file():
        try:
            profiles = json.loads(config.default_path().read_text(encoding="utf-8")).get("profiles") or {}
        except (OSError, ValueError, AttributeError):
            profiles = {}  # resolve() below reports the real problem
        profile = "local" if "local" in profiles else None
    name, settings, prompt, context = config.resolve(profile=profile)
    if settings["backend"] != "llama":
        raise ValueError("profile %r uses the %s backend; start.py runs the local model, so use "
                         "`python -m claudish serve --profile %s`" % (name, settings["backend"], name))
    settings["model_url"] = endpoint
    return Rewriter.from_settings(settings, prompt, context, name)


def main():
    parser = argparse.ArgumentParser(description="Start Claudish and its local model")
    arguments(parser)
    parser.add_argument("--profile", help='Config profile for context, bindings, and modes (default: "local")')
    args = parser.parse_args()
    endpoint = "http://127.0.0.1:" + args.port
    try:
        cmd = command(args)
        rewriter = local_rewriter(endpoint, args.profile)
    except ValueError as exc:
        parser.error(str(exc))

    def interrupt(signum, frame):
        raise KeyboardInterrupt

    # SIGTERM (kill, service managers) must stop the model too, not orphan it.
    signal.signal(signal.SIGTERM, interrupt)
    # Bind the service first, so port conflicts do not leave an orphan model.
    server = make_server(rewriter)
    process = None
    try:
        process = subprocess.Popen(cmd)
        opener = build_opener(ProxyHandler({}))
        deadline = time.monotonic() + 60
        while True:
            if process.poll() is not None:
                raise RuntimeError("llama-server exited during startup")
            try:
                with opener.open(endpoint + "/health", timeout=0.5) as response:
                    if response.status == 200:
                        break
            except OSError:
                pass
            if time.monotonic() > deadline:
                raise RuntimeError("model did not become ready within 60 seconds")
            time.sleep(0.1)
        print("cd_AI ready. Browser demo: http://127.0.0.1:18765", flush=True)
        print("Ctrl+C stops the service and model.", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
