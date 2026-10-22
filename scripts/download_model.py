"""Download one of the tested GGUF presets with the Hugging Face CLI."""
import argparse
import subprocess
from pathlib import Path

PRESETS = {
    "tiny": ("lmstudio-community/SmolLM2-135M-Instruct-GGUF", "SmolLM2-135M-Instruct-Q4_K_M.gguf"),
    "small": ("Qwen/Qwen2.5-0.5B-Instruct-GGUF", "qwen2.5-0.5b-instruct-q4_k_m.gguf"),
}
parser = argparse.ArgumentParser()
parser.add_argument("preset", choices=PRESETS, default="small", nargs="?")
args = parser.parse_args()
repo, filename = PRESETS[args.preset]
subprocess.run(["hf", "download", repo, filename, "--local-dir",
                str(Path(__file__).resolve().parents[1] / "models")], check=True)
