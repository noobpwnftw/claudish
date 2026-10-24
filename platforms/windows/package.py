"""Build cd_AI-setup.exe (G61): one installer for Windows on x64 and ARM64, no Python to install.

python platforms/windows/package.py [--pime-root C:\\PIME-build] [--out dist\\windows]

Run on Windows with Python 3.10+, internet access, and Inno Setup 6 (ISCC.exe). It assembles:
- cd_AI's PIME (platforms/windows/pime: a released PIME's files with cd_AI's text service and
  launcher built over them by build-pime.ps1, each with cd_AI's own names), with cd_AI as its only
  input method;
- an embeddable Python for each of x64 and ARM64 with cd_AI and the Anthropic SDK, for the
  service; the installer copies the one for the machine's architecture;
then compiles cd_AI.iss. The installer asks for an administrator once (the text service is
registered for the machine), and does the rest as the person installing: cd_AI added to their
input sources, a starter config, the service at every login, and cd_AI's settings in the browser.
"""
import argparse
import io
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARCHES = {"x64": ("amd64", "win_amd64"), "arm64": ("arm64", "win_arm64")}  # embeddable zip, wheel platform
TEXT_SERVICE = "{62D8D2ED-5004-44D6-9FAE-B4DE895D953E}"  # cd_AI's PIME's own (pime.patch, PIMEImeModule.cpp)


def download(url):
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


def python_for(arch, target, wheels):
    """An embeddable Python at target, with cd_AI and its Claude extra in Lib\\site-packages."""
    version = "%d.%d.%d" % sys.version_info[:3]  # this Python's own version has an embeddable build
    embed, platform = ARCHES[arch]
    zipfile.ZipFile(io.BytesIO(download("https://www.python.org/ftp/python/%s/python-%s-embed-%s.zip"
                                        % (version, version, embed)))).extractall(target)
    # The embeddable Python reads its path from pythonXY._pth: add site-packages, and site itself.
    pth = next(target.glob("python*._pth"))
    pth.write_text(pth.read_text().replace("#import site", "import site") + "Lib\\site-packages\n")
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--target", str(target / "Lib/site-packages"),
                    "--platform", platform, "--python-version", "%d.%d" % sys.version_info[:2],
                    "--implementation", "cp", "--only-binary=:all:", "anthropic>=2", *map(str, wheels)], check=True)


def pime(pime_root, target):
    """build-pime.ps1's tree with cd_AI as its only input method, its shared modules beside it."""
    # Only the Python backend: registration and the launcher go through every backend in
    # backends.json, so another backend's input methods would be registered as cd_AI's.
    skipped = shutil.ignore_patterns("Uninstall.exe", "__pycache__")

    def ignore(folder, names):
        top = {"node", "go-backend"} if Path(folder) == Path(pime_root) else set()
        return set(skipped(folder, names)) | (top & set(names))
    shutil.copytree(pime_root, target, ignore=ignore)
    backends = json.loads((target / "backends.json").read_text(encoding="utf-8"))
    (target / "backends.json").write_text(json.dumps([b for b in backends if b.get("name") == "python"], indent=4),
                                          encoding="utf-8")
    methods = target / "python/input_methods"
    for other in methods.iterdir():
        if other.is_dir() and other.name != "claudish":
            shutil.rmtree(other)
    plugin = methods / "claudish"
    if plugin.exists():
        shutil.rmtree(plugin)
    shutil.copytree(HERE / "claudish", plugin, ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("composition.py", "client.py", "screen.py"):
        shutil.copy(ROOT / "claudish" / name, plugin / name)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pime-root", type=Path, default=Path(r"C:\PIME-build"), help="build-pime.ps1's tree")
    parser.add_argument("--out", type=Path, default=ROOT / "dist/windows")
    parser.add_argument("--iscc", type=Path, default=Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"))
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("the installer is built on Windows")
    if not (args.pime_root / "python/textService.py").is_file():
        parser.error("no PIME at %s: install PIME, then build Claudish's over it (platforms/windows/pime)" % args.pime_root)
    if not args.iscc.is_file():
        parser.error("no Inno Setup at %s (https://jrsoftware.org/isdl.php)" % args.iscc)
    version = json.loads((HERE / "claudish/ime.json").read_text(encoding="utf-8"))["version"]
    profile = json.loads((HERE / "claudish/ime.json").read_text(encoding="utf-8"))["guid"]
    payload = args.out / "payload"
    shutil.rmtree(payload, ignore_errors=True)
    payload.mkdir(parents=True)
    with tempfile.TemporaryDirectory() as work:
        subprocess.run([sys.executable, "-m", "pip", "wheel", "--quiet", "--no-deps", "-w", work, str(ROOT)], check=True)
        wheels = list(Path(work).glob("*.whl"))
        for arch in ARCHES:
            python_for(arch, payload / ("python-" + arch), wheels)
    pime(args.pime_root, payload / "PIME")
    script = (HERE / "cd_AI.iss").read_text(encoding="utf-8")
    # In the script's sections a { opens one of Inno's constants: the GUIDs' are doubled there.
    for key, value in (("TEXT_SERVICE_ESCAPED", TEXT_SERVICE.replace("{", "{{")),
                       ("PROFILE_ESCAPED", profile.replace("{", "{{")),
                       ("VERSION", version), ("TEXT_SERVICE", TEXT_SERVICE), ("PROFILE", profile)):
        script = script.replace("@%s@" % key, value)
    (payload / "cd_AI.iss").write_text(script, encoding="utf-8")
    shutil.copy(HERE / "claudish/icon.ico", payload / "icon.ico")
    # `claudish` on PATH, as on Linux and macOS: cd_AI's own Python with -m claudish.
    (payload / "bin").mkdir()
    (payload / "bin" / "claudish.cmd").write_bytes(b'@"%~dp0..\\python\\python.exe" -m claudish %*\r\n')
    subprocess.run([str(args.iscc), "/Q", "/O" + str(args.out), str(payload / "cd_AI.iss")], check=True)
    print("Built:", args.out / "cd_AI-setup.exe")


if __name__ == "__main__":
    main()
