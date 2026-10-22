"""Download a pinned llama.cpp release build (llama-server) into .tools/ and verify it.

Python standard library only. The archive is checked against its size and the SHA-256
GitHub publishes for the release asset before anything is unpacked.
"""
import argparse
import os
import platform
import shutil
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

from download_model import download

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / ".tools"
BUILD = "b11822"
RELEASE = "https://github.com/ggml-org/llama.cpp/releases/download/%s/" % BUILD

# (os, machine, variant) -> (asset, size, sha256). CPU builds run everywhere; the macOS arm64
# build includes Metal. Vulkan uses the GPU on most Linux and Windows machines.
ASSETS = {
    ("Linux", "x64", "cpu"): ("llama-b11822-bin-ubuntu-x64.tar.gz", 22337962,
                              "66ed965b14cc844232d4cf6bc262492dce788e6b81cfa2dd97fba2e566339657"),
    ("Linux", "arm64", "cpu"): ("llama-b11822-bin-ubuntu-arm64.tar.gz", 18043651,
                                "9e631e1279619547f012e700d75961354162a386f04bfa1028e84f041db59e3c"),
    ("Linux", "x64", "vulkan"): ("llama-b11822-bin-ubuntu-vulkan-x64.tar.gz", 34980343,
                                 "836d60aee67ab476082c0ff6f4d57643b394e7f4a0ba0d8b207cf66544b77545"),
    ("Linux", "arm64", "vulkan"): ("llama-b11822-bin-ubuntu-vulkan-arm64.tar.gz", 28329527,
                                   "6ddfe8bd223291c00da1790a3b58199c6c7b600a2c68407e70bfe8e7ff165943"),
    ("Windows", "x64", "cpu"): ("llama-b11822-bin-win-cpu-x64.zip", 24074974,
                                "b9484b510a37320ada6d6bac9b0864af3d855320347ccd90fa5ece7b3d9aed88"),
    ("Windows", "arm64", "cpu"): ("llama-b11822-bin-win-cpu-arm64.zip", 12701616,
                                  "d8edc332e61f55c18bd31ceeb61617d367cb98bd13e0cf96f88e6d1caa86b013"),
    ("Windows", "x64", "vulkan"): ("llama-b11822-bin-win-vulkan-x64.zip", 36875726,
                                   "e6fdb5c3fe8ec8a2eb0d49701b4e83730a2e68c56a6ece0c3868dce4167891eb"),
    ("Windows", "arm64", "vulkan"): ("llama-b11822-bin-win-vulkan-arm64.zip", 25087940,
                                     "3860fb4f64f4e66e651468f5504443d073b5149f883e76cbbe0b18963639ae83"),
    ("Darwin", "arm64", "cpu"): ("llama-b11822-bin-macos-arm64.tar.gz", 16151570,
                                 "3b95b08b23178b7f39e07182d99fe42a8bef575df9083e12b927d0a8b3d879a8"),
    ("Darwin", "x64", "cpu"): ("llama-b11822-bin-macos-x64.tar.gz", 11888792,
                               "f7589bd09880c278cb1c103666065f07850f9d81d75c5f5e29a36231723636a5"),
}
MACHINES = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64", "arm64": "arm64"}


def host():
    return platform.system(), MACHINES.get(platform.machine().lower(), platform.machine().lower())


def executable_name(system=None):
    return "llama-server.exe" if (system or platform.system()) == "Windows" else "llama-server"


def installed():
    """The llama-server this script installed, or None."""
    for directory in sorted(TOOLS.glob("llama-%s-*" % BUILD)):
        candidate = directory / executable_name()
        if candidate.is_file():
            return candidate
    return None


def unpack(archive, target):
    """Unpack into target, refusing members that would land outside it."""
    target = Path(target).resolve()

    def inside(name):
        destination = (target / name).resolve()
        if destination != target and target not in destination.parents:
            raise ValueError("unsafe path in archive: %s" % name)

    if str(archive).endswith(".zip"):
        with zipfile.ZipFile(archive) as bundle:
            for name in bundle.namelist():
                inside(name)
            bundle.extractall(target)
        return
    with tarfile.open(archive) as bundle:
        members = bundle.getmembers()
        for member in members:
            inside(member.name)
            if member.issym() or member.islnk():
                inside(os.path.join(os.path.dirname(member.name), member.linkname) if member.issym()
                       else member.linkname)
            elif not (member.isfile() or member.isdir()):
                raise ValueError("unexpected member type in archive: %s" % member.name)
        if hasattr(tarfile, "data_filter"):
            bundle.extractall(target, members=members, filter="data")
        else:
            bundle.extractall(target, members=members)


def install(variant="cpu", progress=None):
    """Download, verify, and unpack; returns (path to llama-server, whether anything was fetched)."""
    system, machine = host()
    key = (system, machine, variant)
    if key not in ASSETS:
        raise ValueError("no pinned llama.cpp %s build for %s %s; get one from "
                         "https://github.com/ggml-org/llama.cpp/releases and pass --server" % (variant, system, machine))
    asset, size, digest = ASSETS[key]
    destination = TOOLS / ("llama-%s-%s" % (BUILD, variant))
    server = destination / executable_name(system)
    if server.is_file():
        return server, False
    TOOLS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=TOOLS) as scratch:
        archive = Path(scratch) / asset
        download(RELEASE + asset, archive, size, digest, progress)
        unpacked = Path(scratch) / "unpacked"
        unpack(archive, unpacked)
        found = [p for p in unpacked.rglob(executable_name(system)) if p.is_file()]
        if len(found) != 1:
            raise ValueError("expected one %s in %s, found %d" % (executable_name(system), asset, len(found)))
        if destination.exists():
            shutil.rmtree(destination)
        os.replace(found[0].parent, destination)  # its libraries sit beside it and must stay there
    if system != "Windows":
        server.chmod(server.stat().st_mode | 0o111)
    return server, True


def main():
    parser = argparse.ArgumentParser(description="Download a pinned llama.cpp build (llama-server) into .tools/")
    parser.add_argument("--variant", choices=["cpu", "vulkan"], default="cpu",
                        help="cpu runs everywhere (Metal on Apple silicon); vulkan uses most GPUs on Linux/Windows")
    args = parser.parse_args()

    def progress(received, total):
        sys.stderr.write("\rllama.cpp %s: %d/%d MB" % (BUILD, received >> 20, total >> 20))

    try:
        server, fetched = install(args.variant, progress if sys.stderr.isatty() else None)
    except (OSError, ValueError) as exc:
        parser.exit(1, "\ndownload failed: %s\n" % exc)
    print(("\nDownloaded and verified " if fetched else "Already present: ") + str(server))


if __name__ == "__main__":
    main()
