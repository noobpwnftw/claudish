"""Launch a persistent llama-server. Works with Windows and Linux binaries."""
import argparse
import shutil
import subprocess
from pathlib import Path

from download_llama import installed
from download_model import PRESETS

root = Path(__file__).resolve().parents[1]


def arguments(parser):
    parser.add_argument("--preset", choices=list(PRESETS), default="gemma")
    parser.add_argument("--server", help="Path to llama-server or llama-server.exe")
    parser.add_argument("--gpu-layers", default="99", help="Set 0 for a CPU-only machine")
    parser.add_argument("--port", default="18766")


def command(args):
    server = args.server or shutil.which("llama-server") or shutil.which("llama-server.exe")
    if not server:
        candidate = root / ".tools/build/bin/llama-server"
        if candidate.is_file():
            server = str(candidate)
    if not server:
        server = installed() and str(installed())
    if not server:
        raise ValueError("run python scripts/download_llama.py, or supply --server /path/to/llama-server")
    model = root / "models" / PRESETS[args.preset][2]
    if not model.is_file():
        raise ValueError("run python scripts/download_model.py " + args.preset)
    # Gemma 4 thinks first unless told not to, which no request waits for (benchmarks/README.md).
    extra = ["--jinja", "--chat-template-kwargs", '{"enable_thinking":false}', "-c", "4096"] if args.preset == "gemma" \
        else ["-c", "2048"]
    return [server, "-m", str(model), "--host", "127.0.0.1", "--port", args.port,
            "-ngl", args.gpu_layers, "-t", "4", "-np", "1"] + extra


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    arguments(parser)
    args = parser.parse_args()
    try:
        cmd = command(args)
    except ValueError as exc:
        parser.error(str(exc))
    raise SystemExit(subprocess.call(cmd))
