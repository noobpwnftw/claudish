"""Run the project's checks on this machine: the merge gate.

python scripts/check.py    # unit tests, compile, diff, IBus and PIME smokes, the settings page

Each check reports PASS, FAIL, or SKIP with a reason, and has 5 seconds (owner, 2026-10-24: a
check that takes longer is not one we run). Real typing on each OS is checked by hand.
"""
import argparse
import glob
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
PIME_URL = ("https://raw.githubusercontent.com/EasyIME/PIME/e0ddf2ffc180837c2e9f8be363de4455c7532962/"
            "python/textService.py")
PIME_SHA256 = "c84fc2e9e79824d0d7692c895ba385287f6e29a3e5ba8cc25945b913694026ce"
results = []


LIMIT = 5  # seconds a check may take


def run(name, command):
    started = time.monotonic()
    # Its own process group: on a timeout everything it started goes too (a service, a browser).
    process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               start_new_session=hasattr(os, "killpg"))
    try:
        out, err = process.communicate(timeout=LIMIT)
    except subprocess.TimeoutExpired:
        if hasattr(os, "killpg"):
            os.killpg(process.pid, 9)
        else:
            process.kill()
        process.communicate()
        results.append((name, "FAIL", "over %d s: make it faster or drop it" % LIMIT))
        return None
    status = "PASS" if process.returncode == 0 else "FAIL"
    output = (out + err).strip().splitlines()
    results.append((name, status, "%.1fs" % (time.monotonic() - started)))
    if status == "FAIL":
        # The traceback and what it asserted (a browser test appends a long page snapshot), then the end.
        start = next((i for i, line in enumerate(output) if line.startswith("Traceback")), None)
        shown = output[start:start + 14] + ["  ..."] + output[-8:] if start is not None else output[-25:]
        print("\n".join(shown))
    elif output:
        print("  " + output[-1])
    return process


def units():
    """The unit tests, one process per file, all at once: the step stays within LIMIT."""
    files = sorted(path.name for path in (ROOT / "tests").glob("test_*.py"))
    running = [(name, subprocess.Popen([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", name],
                                       cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True))
               for name in files]
    failed, count = [], 0
    for name, process in running:
        output = process.communicate()[0]
        count += sum(int(line.split()[1]) for line in output.splitlines() if line.startswith("Ran "))
        if process.returncode:
            failed.append(name)
            print(output)
    print("Ran %d tests in %d files%s" % (count, len(files), ": FAILED " + ", ".join(failed) if failed else ""))
    raise SystemExit(1 if failed else 0)


def skip(name, reason):
    results.append((name, "SKIP", reason))


def patched_pime_source(source):
    """The pinned textService.py with Claudish's PIME patch applied (its Python part), or None."""
    # Outside the checkout (git apply inside a repository skips paths outside its folder), and the
    # same folder every run.
    work = Path(tempfile.gettempdir()) / ("claudish-pime-%d" % os.getuid() if hasattr(os, "getuid") else "claudish-pime")
    shutil.rmtree(work, ignore_errors=True)
    (work / "python").mkdir(parents=True)
    target = work / "python/textService.py"
    shutil.copy(source, target)
    applied = subprocess.run(["git", "apply", "--include=python/textService.py",
                              str(ROOT / "platforms/windows/pime/pime.patch")], cwd=work, capture_output=True)
    return target if applied.returncode == 0 else None


def pime_source():
    target = ROOT / ".tools/pime/textService.py"
    if not target.is_file():
        try:
            data = urlopen(PIME_URL, timeout=LIMIT).read()
        except OSError as exc:
            return None, "cannot download PIME textService.py: %s" % exc
        if hashlib.sha256(data).hexdigest() != PIME_SHA256:
            return None, "downloaded PIME textService.py does not match the pinned hash"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    elif hashlib.sha256(target.read_bytes()).hexdigest() != PIME_SHA256:
        return None, "%s does not match the pinned hash" % target
    return target, None


def chromium_path(args):
    return args.chromium or next(iter(sorted(glob.glob(os.path.expanduser(
        "~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")))), None)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--browser-python", help="Python with Playwright installed")
    parser.add_argument("--chromium", help="Chromium executable for Playwright")
    parser.add_argument("--units", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.units:
        return units()

    run("unit tests", [sys.executable, __file__, "--units"])
    import importlib.util
    missing = [name for name in ("anthropic", "mcp") if importlib.util.find_spec(name) is None]
    if missing:  # their tests were skipped, not failed: say why
        print("  skipped the tests that need %s: pip install -e \".[claude,mcp]\"" % " and ".join(missing))
    run("compileall", [sys.executable, "-m", "compileall", "-q", "claudish", "platforms", "scripts", "tests",
                       "benchmarks"])
    run("git diff --check", ["git", "diff", "--check", "HEAD"])
    extension = ROOT / "platforms/linux/gnome-extension/cd-ai@claudish.io/extension.js"
    if shutil.which("node"):  # GNOME Shell loads it as a module
        run("GNOME extension", ["sh", "-c", 'node --input-type=module --check < "$0"', str(extension)])
    else:
        skip("GNOME extension", "needs node")
    system_python = Path("/usr/bin/python3")
    if not shutil.which("dbus-run-session") or not system_python.is_file():
        skip("IBus smoke", "needs dbus-run-session and /usr/bin/python3")
    elif subprocess.run([str(system_python), "-c", "import gi; gi.require_version('IBus', '1.0')"],
                        capture_output=True).returncode != 0:
        skip("IBus smoke", "system Python lacks PyGObject IBus bindings")
    else:
        run("IBus smoke", ["dbus-run-session", "--", str(system_python), "tests/ibus_smoke.py"])
    source, reason = pime_source()
    if source:
        patched = patched_pime_source(source)  # Claudish's PIME is the only one the adapter supports
        if patched:
            run("PIME smoke", [sys.executable, "tests/pime_smoke.py", "--pime-source", str(patched)])
        else:
            results.append(("PIME smoke", "FAIL", "platforms/windows/pime/pime.patch does not apply to the pinned PIME"))
    else:
        skip("PIME smoke", reason)
    browser = Path(args.browser_python) if args.browser_python else ROOT / ".tools/browser-venv/bin/python"
    if browser.is_file():  # its own service and config directory: no model, and never yours
        chromium = chromium_path(args)
        run("settings page", [str(browser), "tests/settings_page.py"] + (["--executable", chromium] if chromium else []))
    else:
        skip("settings page", "no Playwright Python (pass --browser-python)")
    print()
    for name, status, detail in results:
        print("%-16s %-4s  %s" % (name, status, detail))
    raise SystemExit(1 if any(status == "FAIL" for _, status, _ in results) else 0)


if __name__ == "__main__":
    main()
