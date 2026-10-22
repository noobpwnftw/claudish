"""Start the model and IME service together; Ctrl+C stops both."""
import argparse
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import build_opener, ProxyHandler
from run_model import arguments, command

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from claudish.model import Rewriter
from claudish.server import make_server


def main():
    parser = argparse.ArgumentParser(description="Start Claudish and its local model")
    arguments(parser)
    args = parser.parse_args()
    try:
        cmd = command(args)
    except ValueError as exc:
        parser.error(str(exc))
    endpoint = "http://127.0.0.1:" + args.port
    # Bind the service first, so port conflicts do not leave an orphan model.
    server = make_server(Rewriter(endpoint=endpoint))
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
