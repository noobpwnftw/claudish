"""Launch a persistent llama-server. Works with Windows and Linux binaries."""
import argparse
import subprocess
import sys
from pathlib import Path

from download_llama import find_server
from download_model import PRESETS

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from claudish.warm import llama_command  # noqa: E402


def arguments(parser):
    parser.add_argument("--preset", choices=list(PRESETS), default="gemma")
    parser.add_argument("--server", help="Path to llama-server or llama-server.exe")
    parser.add_argument("--gpu-layers", default="99", help="Set 0 for a CPU-only machine")
    parser.add_argument("--port", default="18766")


def command(args):
    server = args.server or find_server()
    if not server:
        raise ValueError("run python scripts/download_llama.py, or supply --server /path/to/llama-server")
    model = root / "models" / PRESETS[args.preset][2]
    if not model.is_file():
        raise ValueError("run python scripts/download_model.py " + args.preset)
    return llama_command(server, model, args.port, args.preset == "gemma", args.gpu_layers)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    arguments(parser)
    args = parser.parse_args()
    try:
        cmd = command(args)
    except ValueError as exc:
        parser.error(str(exc))
    raise SystemExit(subprocess.call(cmd))
