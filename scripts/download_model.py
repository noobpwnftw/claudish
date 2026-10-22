"""Download one of the tested GGUF presets and verify it. Python standard library only."""
import argparse
import hashlib
import os
import platform
import shutil
import ssl
import subprocess
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

# Pinned to the upstream revisions measured in benchmarks/; the hashes are their LFS SHA-256.
PRESETS = {
    "tiny": ("lmstudio-community/SmolLM2-135M-Instruct-GGUF", "04f7f8a05a8e4bc208e88d11e8c9122be36c2f9b",
             "SmolLM2-135M-Instruct-Q4_K_M.gguf", 105454144,
             "bda484992f9655d22504b14e57985257fa6a86937c61f957cf99c10a3bcae169"),
    "small": ("Qwen/Qwen2.5-0.5B-Instruct-GGUF", "9217f5db79a29953eb74d5343926648285ec7e67",
              "qwen2.5-0.5b-instruct-q4_k_m.gguf", 491400032,
              "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db"),
}


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def open_url(url):
    """urlopen, plus a fix for fresh Windows installs: Windows fetches missing root certificates
    on demand, but only for its own TLS stack, so Python fails until something else has
    connected. curl.exe (Windows 10+) uses that stack; one request installs the root. Downloads
    stay safe either way: every file is checked against its pinned SHA-256."""
    try:
        return urlopen(url, timeout=30)
    except URLError as exc:
        curl = shutil.which("curl.exe")
        if not (platform.system() == "Windows" and curl and isinstance(exc.reason, ssl.SSLCertVerificationError)):
            raise
        subprocess.run([curl, "-sIL", "-o", "NUL", url], capture_output=True, timeout=60)
        return urlopen(url, timeout=30)


def download(url, target, size, digest, progress=None):
    """Write to a .part file and rename only after the size and hash match."""
    target = Path(target)
    if target.exists():
        if target.stat().st_size == size and sha256(target) == digest:
            return False
        raise ValueError("%s exists but does not match the tested model; move it aside and retry" % target)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    try:
        hasher, received = hashlib.sha256(), 0
        with open_url(url) as response, open(partial, "wb") as output:
            for block in iter(lambda: response.read(1 << 20), b""):
                output.write(block)
                hasher.update(block)
                received += len(block)
                if progress:
                    progress(received, size)
        if received != size or hasher.hexdigest() != digest:
            raise ValueError("downloaded file failed verification (%d of %d bytes); retry" % (received, size))
        os.replace(partial, target)
    finally:
        if partial.exists():
            partial.unlink()
    return True


def target(preset):
    return Path(__file__).resolve().parents[1] / "models" / PRESETS[preset][2]


def fetch(preset="small", progress=None):
    """Download and verify a preset; returns (path, whether anything was fetched)."""
    repo, revision, filename, size, digest = PRESETS[preset]
    endpoint = os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/")
    url = "%s/%s/resolve/%s/%s" % (endpoint, repo, revision, filename)
    return target(preset), download(url, target(preset), size, digest, progress)


def main():
    parser = argparse.ArgumentParser(description="Download a tested Claudish model into models/")
    parser.add_argument("preset", choices=PRESETS, default="small", nargs="?")
    args = parser.parse_args()

    def progress(received, total):
        sys.stderr.write("\r%s: %d/%d MB" % (PRESETS[args.preset][2], received >> 20, total >> 20))

    try:
        path, fetched = fetch(args.preset, progress if sys.stderr.isatty() else None)
    except (OSError, ValueError) as exc:
        parser.exit(1, "\ndownload failed: %s\n" % exc)
    print(("\nDownloaded and verified " if fetched else "Already present and verified: ") + str(path))


if __name__ == "__main__":
    main()
