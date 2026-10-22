"""Launch a persistent llama-server. Works with Windows and Linux binaries."""
import argparse
import shutil
import subprocess
from pathlib import Path

from download_llama import installed

root = Path(__file__).resolve().parents[1]


def arguments(parser):
    parser.add_argument("--preset", choices=["tiny", "small"], default="small")
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
    filename = ("SmolLM2-135M-Instruct-Q4_K_M.gguf" if args.preset == "tiny"
                else "qwen2.5-0.5b-instruct-q4_k_m.gguf")
    model = root / "models" / filename
    if not model.is_file():
        raise ValueError("run python scripts/download_model.py " + args.preset)
    return [server, "-m", str(model), "--host", "127.0.0.1", "--port", args.port,
            "-c", "2048", "-ngl", args.gpu_layers, "-t", "4", "-np", "1"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    arguments(parser)
    args = parser.parse_args()
    try:
        cmd = command(args)
    except ValueError as exc:
        parser.error(str(exc))
    raise SystemExit(subprocess.call(cmd))
